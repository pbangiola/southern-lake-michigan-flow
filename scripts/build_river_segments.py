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
    output=[];raw_count=0;matched=0
    for kmz in a.kmz:
        for line in streams(kmz,bbox):
            raw_count+=1
            projected=LineString([metric(c,lat) for c in line.coords])
            candidates=tree.query(projected.buffer(a.max_distance_m/1000))
            hits=[]
            for i in candidates:
                station_id,point,name=stations[int(i)]
                gauge=gauge_points[int(i)]
                distance=projected.distance(gauge)*1000
                if distance<=a.max_distance_m:
                    along=projected.project(gauge)
                    hits.append((along,station_id,round(distance,1),name))
            if not hits:continue
            matched+=1
            hits.sort()
            # Split at projected gauge positions, preserving the original geometry.
            cuts=[0]+sorted(set(h[0] for h in hits if 0<h[0]<projected.length))+[projected.length]
            for k,(start,end) in enumerate(zip(cuts,cuts[1:])):
                if end-start<0.001:continue
                # Associate each piece with its closest on-line gauge. This is a
                # geographic attribution, not a verified hydrologic connection.
                center=(start+end)/2
                nearest=min(hits,key=lambda h:abs(h[0]-center))
                part=substring(line,start/projected.length*line.length,end/projected.length*line.length)
                if part.geom_type!='LineString':continue
                output.append({'type':'Feature','geometry':mapping(part),'properties':{
                    'site':nearest[1],'gauge_name':nearest[3],
                    'gauge_distance_m':nearest[2],
                    'association':'nearest gauge on source stream line (unverified)',
                    'condition':'unclassified','source_kmz':kmz.name,
                    'segment_id':f'{kmz.stem}-{raw_count}-{k}'}})
        print(f'{kmz.name}: scanned {raw_count} lines, matched {matched}',flush=True)
    result={'type':'FeatureCollection','metadata':{'note':'Gauge proximity only; not a navigation or safety rating','max_distance_m':a.max_distance_m,'source_files':[p.name for p in a.kmz]},'features':output}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,separators=(',',':')))
    print(f'Wrote {len(output)} gauge-associated segments to {a.output}')

if __name__=='__main__':main()