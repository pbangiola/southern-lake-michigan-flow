#!/usr/bin/env python3
"""Attach stage-gauge associations to named authoritative rivers.

Nearest EDNA reach is used ONLY for stage color association, never river
identity or direction. Unmatched reaches remain gray. Distances are measured
in a local projected coordinate approximation and checked against a limit.
"""
import argparse
import json
import math
from pathlib import Path
from shapely.geometry import shape
from shapely.ops import transform
from shapely.strtree import STRtree


def attach(named, gauge_reaches, max_distance_m=100):
    if max_distance_m<=0:
        raise ValueError('max_distance_m must be positive')
    source=gauge_reaches['features']
    target=named['features']
    latitudes=[f['geometry']['coordinates'][0][1] for f in target if f['geometry']['type']=='LineString']
    latitude=sum(latitudes)/len(latitudes) if latitudes else 40
    scale_x=111200*math.cos(math.radians(latitude))
    def projected(feature):
        return transform(lambda x,y,z=None:(x*scale_x,y*111200),shape(feature['geometry']))
    source_geoms=[projected(f) for f in source]
    tree=STRtree(source_geoms)
    matched=0
    unmatched=0
    for f in target:
        p=f.setdefault('properties',{})
        # Clear potentially inherited gauge data from the authoritative input.
        for key in ('site','from_gauge','to_gauge','between_gauges','gauge_name'):
            p.pop(key,None)
        if not source_geoms:
            unmatched+=1
            continue
        g=projected(f)
        i=int(tree.nearest(g))
        distance=g.distance(source_geoms[i])
        if distance>max_distance_m:
            unmatched+=1
            continue
        old=source[i]['properties']
        for key in ('site','from_gauge','to_gauge','between_gauges','gauge_name'):
            if key in old:p[key]=old[key]
        p['stage_gauge_match_m']=round(distance,1)
        p['stage_gauge_method']='nearest EDNA reach; stage display only'
        matched+=1
    named.setdefault('metadata',{})['stage_gauge_association']={
        'matched':matched,'unmatched':unmatched,'max_distance_m':max_distance_m,
        'note':'Gauge associations are for display, not river identity or flow direction.'}
    return named


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('named',type=Path,help='Authoritative named GeoJSON')
    p.add_argument('--gauges-network',type=Path,default=Path('local/illinois_river_segments.geojson'))
    p.add_argument('--output',type=Path,default=Path('local/named_rivers_with_stage.geojson'))
    p.add_argument('--max-distance-m',type=float,default=100)
    a=p.parse_args()
    result=attach(json.loads(a.named.read_text()),json.loads(a.gauges_network.read_text()),a.max_distance_m)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,separators=(',',':')))
    print(json.dumps(result['metadata']['stage_gauge_association'],indent=2))


if __name__=='__main__':
    main()
