#!/usr/bin/env python3
"""Discover OSM paddling access candidates across the gauge-region bounding box.

Candidates are NOT verified public or legal access. Output is a separate review
dataset; existing curated KML locations are preserved by the resolver.
"""
import json, time, urllib.parse, urllib.request
from pathlib import Path

BBOX=(-88.7,40.9,-85.4,43.2)  # same coverage as fetch_gauges.py
URLS=('https://overpass-api.de/api/interpreter',
      'https://overpass.private.coffee/api/interpreter',
      'https://overpass.kumi.systems/api/interpreter')
# Explicit launches, ramps, canoe/kayak access, and named water-access features.
FILTERS='''["leisure"="slipway"];
["waterway"="access_point"];
["canoe"="yes"];
["kayak"="yes"];
["sport"~"^(canoe|kayak|canoeing|kayaking)$"];
["name"~"(canoe|kayak|paddle|boat launch|boat ramp|landing)",i]'''
def query(south,west,north,east,depth=0):
    clauses=''.join(f'nwr{tag}({south},{west},{north},{east});' for tag in FILTERS.split(';') if tag.strip())
    q='[out:json][timeout:60];('+clauses+');out center tags;'
    data=urllib.parse.urlencode({'data':q}).encode()
    errors=[]
    for url in URLS:
        req=urllib.request.Request(url,data=data,headers={
            'User-Agent':'SouthernLakeMichiganFlowAtlas/0.2 (GitHub Actions)',
            'Accept':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=85) as response:
                payload=json.load(response)
                if 'elements' not in payload:raise ValueError('No elements in Overpass response')
                return payload['elements']
        except Exception as exc:
            errors.append(f'{url}: {exc}')
            print(f'Overpass attempt failed: {errors[-1]}',flush=True)
            time.sleep(2)
    if depth<2:
        mid_lat=(south+north)/2;mid_lon=(west+east)/2
        print(f'Splitting failed tile at depth {depth+1}',flush=True)
        return (query(south,west,mid_lat,mid_lon,depth+1)
                +query(south,mid_lon,mid_lat,east,depth+1)
                +query(mid_lat,west,north,mid_lon,depth+1)
                +query(mid_lat,mid_lon,north,east,depth+1))
    raise RuntimeError(f'Overpass failed for tile {south},{west},{north},{east}: '+'; '.join(errors))
def main():
    west,south,east,north=BBOX
    found={}
    # Tiles reduce the risk of one expensive regional query timing out.
    for y in range(3):
        for x in range(4):
            s=south+(north-south)*y/3;n=south+(north-south)*(y+1)/3
            w=west+(east-west)*x/4;e=west+(east-west)*(x+1)/4
            results=query(s,w,n,e)
            for item in results:found[(item['type'],item['id'])]=item
            print(f'Tile {y*4+x+1}/12: {len(results)} OSM features',flush=True)
            time.sleep(2)
    features=[]
    for (kind,osm_id),item in sorted(found.items()):
        tags=item.get('tags',{})
        center=item.get('center',item)
        if 'lon' not in center or 'lat' not in center:continue
        # Broad name/sport matches can be clubs or stores, not actual launches.
        strong=tags.get('leisure')=='slipway' or tags.get('waterway')=='access_point'
        if (not strong and tags.get('shop')) or tags.get('access') in ('private','no'):
            continue
        name=tags.get('name') or f'OSM {kind} {osm_id}'
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[center['lon'],center['lat']]},
            'properties':{'id':f'osm-{kind}-{osm_id}','name':name,'source':'OpenStreetMap',
                'source_url':f'https://www.openstreetmap.org/{kind}/{osm_id}',
                'verification':'candidate_review','access':tags.get('access','unknown'),
                'waterway':tags.get('waterway'),'leisure':tags.get('leisure'),
                'canoe':tags.get('canoe'),'kayak':tags.get('kayak'),
                'sport':tags.get('sport'),'description':tags.get('description')}})
    out=Path('data/putins_osm_candidates.geojson');out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({'type':'FeatureCollection','metadata':{
        'note':'Unverified candidates; OSM coverage is incomplete; lake and river access mixed',
        'bbox':BBOX},'features':features},indent=2)+'\n')
    print(f'Wrote {len(features)} OSM access candidates to {out}')
if __name__=='__main__':main()
