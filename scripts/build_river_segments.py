#!/usr/bin/env python3
"""Build gauge-linked stream segments from USGS EDNA watershed KMZ files.

Run from repository root:
 python3 -m pip install lxml shapely
 python3 scripts/build_river_segments.py greatlakes.kmz mississippi.kmz

This intentionally does NOT infer paddling safety or hydraulic conditions.
"""
import argparse, json, math, zipfile
from pathlib import Path
from lxml import etree
from shapely.geometry import LineString, Point, box, mapping
from shapely.ops import substring, linemerge
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
    # Build a topological graph of source lines. Shared endpoints are snapped to a
    # small tolerance; branch junctions (degree != 2) remain explicit boundaries.
    # Only lines near at least one gauge are retained, then their connected
    # components are expanded through all source lines in the atlas bounds.
    snap_m=15.0
    def node(xy):
        x,y=metric(xy,lat)
        return (round(x*1000/snap_m),round(y*1000/snap_m))
    lines=[];ends=[];incidence={}
    for kmz in a.kmz:
        count=0
        for line in streams(kmz,bbox):
            if line.length==0:continue
            i=len(lines);lines.append((line,kmz.name))
            u,v=node(line.coords[0]),node(line.coords[-1])
            ends.append((u,v))
            incidence.setdefault(u,[]).append(i)
            incidence.setdefault(v,[]).append(i)
            count+=1
        print(f'{kmz.name}: loaded {count} clipped stream lines',flush=True)
    print(f'Building connected components from {len(lines)} source lines',flush=True)
    # Union-find groups lines sharing endpoints, without crossing tributary junctions
    # when building individual chains.
    parent=list(range(len(lines)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i
    def union(i,j):
        a,b=find(i),find(j)
        if a!=b:parent[b]=a
    for members in incidence.values():
        for i in members[1:]:union(members[0],i)
    # Locate gauges by perpendicular distance to complete source lines.
    projected_lines=[LineString([metric(c,lat) for c in line.coords]) for line,_ in lines]
    stream_tree=STRtree(projected_lines)
    components_with_gauges=set()
    for gauge in gauge_points:
        for index in stream_tree.query(gauge.buffer(a.max_distance_m/1000)):
            i=int(index)
            if projected_lines[i].distance(gauge)*1000<=a.max_distance_m:
                components_with_gauges.add(find(i))
    # Trace maximal unbranched chains; each chain stops at an endpoint or junction.
    visited=set();chains=[]
    def walk(start,entry):
        chain=[];current=start;incoming=entry
        while current not in visited:
            visited.add(current)
            u,v=ends[current]
            forward=(incoming==u)
            chain.append((current,forward))
            exit_node=v if forward else u
            if len(incidence[exit_node])!=2:break
            next_candidates=[j for j in incidence[exit_node] if j!=current]
            if not next_candidates or next_candidates[0] in visited:break
            current=next_candidates[0];incoming=exit_node
        return chain
    # Begin at endpoints and junctions, then handle closed loops.
    for i in range(len(lines)):
        if i in visited or find(i) not in components_with_gauges:continue
        u,v=ends[i]
        if len(incidence[u])!=2:chains.append(walk(i,u))
        elif len(incidence[v])!=2:chains.append(walk(i,v))
    for i in range(len(lines)):
        if i not in visited and find(i) in components_with_gauges:
            chains.append(walk(i,ends[i][0]))
    output=[];matched_chains=0
    for chain_number,indices in enumerate(chains):
        # Merge only chains whose adjacent coordinates really connect.
        coordinates=[]
        for i,forward in indices:
            pts=list(lines[i][0].coords)
            if not forward:pts.reverse()
            if coordinates:
                # Endpoints may be slightly offset due to source precision.
                # Snap to the previous end rather than inserting an artificial gap.
                pts[0]=coordinates[-1]
                coordinates.extend(pts[1:])
            else:coordinates.extend(pts)
        if len(coordinates)<2:continue
        segments=[LineString(coordinates)]
        for line in segments:
            projected=LineString([metric(c,lat) for c in line.coords])
            if projected.length==0:continue
            hits=[]
            for index in tree.query(projected.buffer(a.max_distance_m/1000)):
                i=int(index);gauge=gauge_points[i]
                distance=projected.distance(gauge)*1000
                if distance<=a.max_distance_m:
                    sid,_,name=stations[i]
                    hits.append((projected.project(gauge),sid,round(distance,1),name))
            if not hits:continue
            matched_chains+=1
            hits.sort()
            cuts=[0]+sorted(set(h[0] for h in hits if 0<h[0]<projected.length))+[projected.length]
            for k,(begin,finish) in enumerate(zip(cuts,cuts[1:])):
                if finish-begin<0.001:continue
                part=substring(projected,begin,finish)
                if part.geom_type!='LineString':continue
                # Convert the cut coordinates back from projected kilometers to lon/lat.
                coords=[(x/(KM_PER_DEG_LAT*math.cos(math.radians(lat))),y/KM_PER_DEG_LAT) for x,y in part.coords]
                center=(begin+finish)/2
                closest=min(hits,key=lambda h:abs(h[0]-center))
                before=[h for h in hits if h[0]<=begin+1e-9]
                after=[h for h in hits if h[0]>=finish-1e-9]
                upstream=before[-1] if before else None
                downstream=after[0] if after else None
                output.append({'type':'Feature','geometry':mapping(LineString(coords)),'properties':{
                    'site':closest[1],'gauge_name':closest[3],
                    'gauge_distance_m':closest[2],
                    'from_gauge':upstream[1] if upstream else None,
                    'to_gauge':downstream[1] if downstream else None,
                    'association':'projected onto connected unbranched stream chain',
                    'condition':'unclassified','source_kmz':lines[indices[0][0]][1],
                    'segment_id':f'network-{chain_number}-{k}'}})
    result={'type':'FeatureCollection','metadata':{
        'note':'Connected endpoint topology; unverified navigability and hydraulic conditions',
        'max_distance_m':a.max_distance_m,'endpoint_snap_m':snap_m,
        'source_files':[p.name for p in a.kmz],
        'source_lines':len(lines),'matched_chains':matched_chains},'features':output}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,separators=(',',':')))
    print(f'Wrote {len(output)} segments across {matched_chains} gauge-linked chains to {a.output}')

if __name__=='__main__':main()