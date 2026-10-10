#!/usr/bin/env python3
"""Build gauge-linked stream segments from USGS EDNA watershed KMZ files.

Run from repository root:
 python3 -m pip install lxml shapely
 python3 scripts/build_river_segments.py greatlakes.kmz mississippi.kmz

This intentionally does NOT infer paddling safety or hydraulic conditions.
"""
import argparse, heapq, json, math, re, zipfile
from pathlib import Path
from lxml import etree
from shapely.geometry import LineString, Point, box, mapping
from shapely.ops import substring
from shapely.strtree import STRtree

BBOX=(-88.7,40.9,-85.4,43.2)
MAX_DISTANCE_M=200
KM_PER_DEG_LAT=111.2

def metric(xy,latitude):
    return (xy[0]*KM_PER_DEG_LAT*math.cos(math.radians(latitude)),xy[1]*KM_PER_DEG_LAT)

def streams(kmz,bbox):
    with zipfile.ZipFile(kmz) as z:
        kml=next(n for n in z.namelist() if n.lower().endswith('.kml'))
        with z.open(kml) as handle:
            # USGS EDNA exports contain some malformed markup; recover when possible.
            for _,elem in etree.iterparse(handle,events=('end',),tag='{*}LineString',recover=True,huge_tree=True):
                node=elem.find('{*}coordinates')
                if node is not None and node.text:
                    coords=[]
                    for token in node.text.split():
                        try:
                            lon,lat=map(float,token.split(',')[:2])
                            coords.append((lon,lat))
                        except (ValueError,IndexError):pass
                    if len(coords)>1:
                        line=LineString(coords)
                        if line.intersects(bbox):
                            clipped=line.intersection(bbox)
                            if clipped.geom_type=='LineString' and clipped.length:yield clipped
                            elif clipped.geom_type=='MultiLineString':
                                yield from (p for p in clipped.geoms if p.length)
                elem.clear()
                while elem.getprevious() is not None:del elem.getparent()[0]

def river_name(description):
    """Best-effort waterway name from a USGS station title; never assert for tributaries."""
    text=str(description or '').upper()
    m=re.match(r"^(.+?\\b(?:RIVER|CREEK|BROOK|CANAL|DITCH|BRANCH|FORK|RUN))\\b",text)
    return m.group(1).title() if m else "Unidentified waterway"

def geometry_key(coords):
    """Canonicalize both directions to remove exact overlapping EDNA lines."""
    points=tuple((round(x,7),round(y,7)) for x,y in coords)
    return min(points,points[::-1])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('kmz',nargs='+',type=Path)
    p.add_argument('--gauges',type=Path,default=Path('data/gauges.geojson'))
    p.add_argument('--output',type=Path,default=Path('data/river_segments.geojson'))
    p.add_argument('--max-distance-m',type=float,default=MAX_DISTANCE_M)
    a=p.parse_args()
    gauges=json.loads(a.gauges.read_text())['features']
    stations=[]
    for f in gauges:
        pt=f.get('geometry',{}).get('coordinates')
        props=f.get('properties',{})
        if pt and props.get('site') and props.get('stage') is not None:
            stations.append((str(props['site']),pt[:2],props.get('name','')))
    lat=(BBOX[1]+BBOX[3])/2
    gauge_points=[Point(metric(pt,lat)) for _,pt,_ in stations]
    tree=STRtree(gauge_points)
    bbox=box(*BBOX)
    # Every source line is an edge. Gauge projections become additional nodes.
    # Dijkstra propagates gauge ownership through intervening, ungauged edges.
    # This is a network attribution, not a claim about paddling conditions.
    snap_m=15.0
    def node(xy):
        x,y=metric(xy,lat)
        return ('n',round(x*1000/snap_m),round(y*1000/snap_m))
    lines=[];projected=[];ends=[];seen_lines=set();duplicates_skipped=0
    for kmz in a.kmz:
        count=0
        for line in streams(kmz,bbox):
            if line.length==0:continue
            key=geometry_key(line.coords)
            if key in seen_lines:
                duplicates_skipped+=1
                continue
            seen_lines.add(key)
            u,v=node(line.coords[0]),node(line.coords[-1])
            if u==v:continue
            lines.append((line,kmz.name))
            projected.append(LineString([metric(c,lat) for c in line.coords]))
            ends.append((u,v));count+=1
        print(f'{kmz.name}: loaded {count} stream lines',flush=True)
    print(f'Building graph from {len(lines)} stream lines',flush=True)
    stream_tree=STRtree(projected)
    # Match each gauge to its closest eligible line, not every nearby line.
    assigned={}
    for i,gauge in enumerate(gauge_points):
        candidates=stream_tree.query(gauge.buffer(a.max_distance_m/1000))
        if len(candidates)==0:continue
        best=min((int(j) for j in candidates),key=lambda j:projected[j].distance(gauge))
        distance=projected[best].distance(gauge)*1000
        if distance>a.max_distance_m:continue
        along=projected[best].project(gauge)
        assigned.setdefault(best,[]).append((along,i,round(distance,1)))
    # Build a weighted graph split exactly at projected gauge positions.
    graph={};edges=[];seed={}
    def link(u,v,length):
        graph.setdefault(u,[]).append((v,length))
        graph.setdefault(v,[]).append((u,length))
    for i,((line,source),p,(u,v)) in enumerate(zip(lines,projected,ends)):
        hits=sorted(assigned.get(i,[]))
        cuts=[(0.0,u,None)]
        for along,gidx,distance in hits:
            key=('g',gidx)
            cuts.append((along,key,(gidx,distance)))
            seed[key]=gidx
        cuts.append((p.length,v,None))
        cuts.sort(key=lambda x:x[0])
        for k,(left,right) in enumerate(zip(cuts,cuts[1:])):
            begin,from_node,_=left;finish,to_node,_=right
            if finish-begin<1e-9:
                link(from_node,to_node,0.0)
                continue
            link(from_node,to_node,finish-begin)
            part=substring(p,begin,finish)
            if part.geom_type!='LineString':continue
            coords=[(x/(KM_PER_DEG_LAT*math.cos(math.radians(lat))),y/KM_PER_DEG_LAT) for x,y in part.coords]
            edges.append((i,k,from_node,to_node,coords))
    # Multisource shortest paths label the entire connected network.
    # A component without any gauge remains unclassified and is excluded.
    dist={};owner={};queue=[]
    for node_id,gidx in seed.items():
        dist[node_id]=0.0;owner[node_id]=gidx
        heapq.heappush(queue,(0.0,gidx,node_id))
    while queue:
        d,gidx,u=heapq.heappop(queue)
        if d>dist.get(u,float('inf'))+1e-9 or owner.get(u)!=gidx:continue
        for v,length in graph.get(u,[]):
            nd=d+length
            if nd<dist.get(v,float('inf'))-1e-9:
                dist[v]=nd;owner[v]=gidx
                heapq.heappush(queue,(nd,gidx,v))
    output=[];between=0;seen_segments=set();duplicate_segments=0
    for i,k,u,v,coords in edges:
        if u not in owner and v not in owner:continue
        left=owner.get(u);right=owner.get(v)
        if left is None:left=right
        if right is None:right=left
        if left!=right:between+=1
        chosen=left if dist.get(u,float('inf'))<=dist.get(v,float('inf')) else right
        sid,_,name=stations[chosen]
        key=geometry_key(coords)
        if key in seen_segments:
            duplicate_segments+=1
            continue
        seen_segments.add(key)
        output.append({'type':'Feature','geometry':mapping(LineString(coords)),'properties':{
            'site':sid,'gauge_name':name,'river_name':river_name(name),
            'from_gauge':stations[left][0],
            'to_gauge':stations[right][0],
            'between_gauges':left!=right,
            'association':'shortest connected stream-network distance to gauge',
            'condition':'unclassified','source_kmz':lines[i][1],
            'segment_id':f'network-{i}-{k}'}})
    result={'type':'FeatureCollection','metadata':{
        'note':'Gauge-connected network including intervening ungauged edges; no navigability classification',
        'max_distance_m':a.max_distance_m,'endpoint_snap_m':snap_m,
        'source_files':[p.name for p in a.kmz],
        'source_lines':len(lines),'matched_gauges':len(seed),
        'between_gauge_edges':between,'duplicate_source_lines_skipped':duplicates_skipped,'duplicate_output_segments_skipped':duplicate_segments,'river_name_method':'inferred from controlling USGS station; may not name tributaries','flow_direction_verified':False},'features':output}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,separators=(',',':')))
    print(f'Skipped {duplicates_skipped} duplicate source lines and {duplicate_segments} duplicate output segments',flush=True)
    print(f'Wrote {len(output)} connected stream segments; {between} between-gauge edges; {len(seed)} matched gauges to {a.output}')

if __name__=='__main__':main()