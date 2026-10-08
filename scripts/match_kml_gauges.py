#!/usr/bin/env python3
"""Snap USGS GeoJSON gauges to KML paths and identify connected river components.

Usage: python scripts/match_kml_gauges.py rivers.kml data/gauges.geojson
       python scripts/match_kml_gauges.py rivers.kml data/gauges.geojson --overrides data/gauge_path_overrides.json --output data/gauge_matches.geojson

Overrides format: {"USGS_SITE_ID": "path_id"}; path IDs are placemark IDs when
present, otherwise stable generated IDs (path-0, path-1, ...).
This models *undirected* connectivity; it does not infer downstream direction.
"""
import argparse
import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict

EARTH_M = 6371008.8

def distance(a, b):
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    dlat = lat2-lat1
    dlon = math.radians(b[0]-a[0])
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2*EARTH_M*math.asin(min(1, math.sqrt(h)))

def project(point, a, b):
    """Closest point on a segment in a local metric projection."""
    lat = math.radians((point[1]+a[1]+b[1])/3)
    scale_x = 111195*math.cos(lat)
    scale_y = 111195
    vx, vy = (b[0]-a[0])*scale_x, (b[1]-a[1])*scale_y
    wx, wy = (point[0]-a[0])*scale_x, (point[1]-a[1])*scale_y
    t = max(0, min(1, (wx*vx+wy*vy)/(vx*vx+vy*vy))) if vx*vx+vy*vy else 0
    snapped = [a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])]
    return distance(point, snapped), snapped, t

def read_paths(filename):
    root = ET.parse(filename).getroot()
    paths = []
    for placemark in root.iter():
        if placemark.tag.split('}')[-1] != 'Placemark':
            continue
        name = next((x.text for x in placemark if x.tag.split('}')[-1]=='name'), None)
        for line in placemark.iter():
            if line.tag.split('}')[-1] != 'LineString':
                continue
            coords = next((x.text for x in line if x.tag.split('}')[-1]=='coordinates'), '')
            points = []
            for token in (coords or '').split():
                values = token.split(',')
                if len(values)>=2:
                    points.append([float(values[0]), float(values[1])])
            if len(points)>=2:
                paths.append({'id': (placemark.get('id') or 'path-'+str(len(paths))) + ('-'+str(len(paths)) if placemark.get('id') and any(p['id']==placemark.get('id') for p in paths) else ''), 'name':name, 'points':points})
    return paths

def components(paths, tolerance_m):
    """Join endpoints to endpoints OR interior segments within tolerance."""
    parent = list(range(len(paths)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i
    def union(i,j):
        parent[find(i)] = find(j)
    for i, p in enumerate(paths):
        for j in range(i):
            q=paths[j]
            # Include endpoint-to-interior junctions (tributaries).
            if any(min(project(endpoint, a,b)[0] for a,b in zip(q['points'],q['points'][1:]))<=tolerance_m for endpoint in (p['points'][0],p['points'][-1])) or any(min(project(endpoint,a,b)[0] for a,b in zip(p['points'],p['points'][1:]))<=tolerance_m for endpoint in (q['points'][0],q['points'][-1])):
                union(i,j)
    return [find(i) for i in range(len(paths))]

def match(paths, gauges, overrides, max_snap_m, connect_m):
    if not paths:
        raise ValueError('No KML LineString paths found')
    ids={p['id']:i for i,p in enumerate(paths)}
    for gauge_id,path_id in overrides.items():
        if path_id not in ids:
            raise ValueError('Override for %s references unknown path %s' % (gauge_id,path_id))
    groups=components(paths,connect_m)
    output=[]
    for feature in gauges['features']:
        if feature.get('geometry',{}).get('type')!='Point':
            continue
        pt=feature['geometry']['coordinates'][:2]
        props=feature.get('properties') or {}
        gauge_id=str(props.get('site_no') or props.get('site_id') or props.get('id') or feature.get('id') or '')
        candidates=[ids[overrides[gauge_id]]] if gauge_id in overrides else range(len(paths))
        best=None
        for i in candidates:
            for segment,(a,b) in enumerate(zip(paths[i]['points'],paths[i]['points'][1:])):
                d,s,t=project(pt,a,b)
                if best is None or d<best[0]:
                    best=(d,i,segment,s,t)
        d,i,segment,s,t=best
        properties=dict(props)
        properties.update({'kml_path_id':paths[i]['id'] if d<=max_snap_m or gauge_id in overrides else None,
                           'kml_path_name':paths[i]['name'] if d<=max_snap_m or gauge_id in overrides else None,
                           'river_component':groups[i] if d<=max_snap_m or gauge_id in overrides else None,
                           'snap_distance_m':round(d,2), 'snap_segment':segment,
                           'snap_fraction':round(t,8), 'snap_override':gauge_id in overrides,
                           'match_status':'override' if gauge_id in overrides else ('matched' if d<=max_snap_m else 'review'),
                           'snapped_coordinates':s if d<=max_snap_m or gauge_id in overrides else None})
        output.append({'type':'Feature','geometry':feature['geometry'],'properties':properties})
    return {'type':'FeatureCollection','features':output}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kml')
    parser.add_argument('gauges')
    parser.add_argument('--overrides',default=None)
    parser.add_argument('--output',default='data/gauge_matches.geojson')
    parser.add_argument('--max-snap-m',type=float,default=1000)
    parser.add_argument('--connect-m',type=float,default=30)
    args=parser.parse_args()
    with open(args.gauges) as f: gauges=json.load(f)
    with open(args.overrides) as f: overrides=json.load(f) if args.overrides else {}
    paths=read_paths(args.kml)
    result=match(paths,gauges,overrides,args.max_snap_m,args.connect_m)
    with open(args.output,'w') as f: json.dump(result,f,indent=2)
    counts=defaultdict(int)
    for feature in result['features']: counts[feature['properties']['match_status']]+=1
    print('Parsed %d KML paths; matched %d gauges; overrides %d; review %d; output %s' %
          (len(paths),counts['matched'],counts['override'],counts['review'],args.output))

if __name__=='__main__':
    main()
