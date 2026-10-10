#!/usr/bin/env python3
"""Stream a compact, gauge-associated candidate layer from a huge 3DHP GeoJSON.

Preserves authoritative river identity and stage fields. Simplifies geometry
in meters, quantizes coordinates, and drops unneeded source attributes.
This is a REVIEW layer: it omits reaches without matched gauges.
"""
import argparse
import collections
import json
import math
from pathlib import Path

import ijson
from shapely.geometry import LineString


KEEP=('river_id','river_name','filter_river','site','from_gauge','to_gauge',
      'between_gauges','gauge_name','stage_gauge_match_m','direction_method')


def compact_feature(f, tolerance_m=15, digits=5):
    p=f.get('properties') or {}
    if not any(p.get(k) for k in ('site','from_gauge','to_gauge')):
        return None
    geom=f.get('geometry') or {}
    if geom.get('type')!='LineString':
        return None
    coords=geom.get('coordinates') or []
    if len(coords)<2:return None
    latitude=(float(coords[0][1])+float(coords[-1][1]))/2
    xscale=111200*math.cos(math.radians(latitude))
    if xscale<=0:return None
    pts=[(float(x)*xscale,float(y)*111200) for x,y,*_ in coords]
    simplified=LineString(pts).simplify(tolerance_m,preserve_topology=False)
    coordinates=[[round(x/xscale,digits),round(y/111200,digits)] for x,y in simplified.coords]
    dedup=[]
    for xy in coordinates:
        if not dedup or xy!=dedup[-1]:dedup.append(xy)
    if len(dedup)<2:return None
    return {'type':'Feature','geometry':{'type':'LineString','coordinates':dedup},
            'properties':{k:p[k] for k in KEEP if k in p}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path,default=Path('local/stage_matched_review.geojson'))
    parser.add_argument('--tolerance-m',type=float,default=15)
    parser.add_argument('--digits',type=int,default=5)
    args=parser.parse_args()
    if args.tolerance_m<0 or not 3<=args.digits<=7:parser.error('Invalid simplification/precision')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    stats=collections.Counter()
    with args.input.open('rb') as inp,args.output.open('w') as out:
        out.write('{"type":"FeatureCollection","metadata":{"layer_type":"stage_matched_review","not_full_river_coverage":true,"direction_source":"USGS 3DHP"},"features":[')
        first=True
        for f in ijson.items(inp,'features.item',use_float=True):
            stats['input']+=1
            reduced=compact_feature(f,args.tolerance_m,args.digits)
            if reduced is None:continue
            if not first:out.write(',')
            out.write(json.dumps(reduced,separators=(',',':')))
            first=False
            stats['output']+=1
        out.write(']}')
    print(json.dumps({**stats,'bytes':args.output.stat().st_size},indent=2))


if __name__=='__main__':
    main()
