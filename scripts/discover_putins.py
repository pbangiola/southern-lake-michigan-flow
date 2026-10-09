#!/usr/bin/env python3
"""Discover candidate paddling launches in the gauge region via bounded OSM queries.

Results are unverified and may include non-paddling facilities. Query failures are
recorded in a coverage report, never silently treated as a complete inventory.
"""
import json, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

BBOX=(-88.7,40.9,-85.4,43.2)
SERVERS=('https://overpass-api.de/api/interpreter',
         'https://overpass.private.coffee/api/interpreter',
         'https://overpass.kumi.systems/api/interpreter')
# Small, indexed tag searches; avoid a broad name regex across all OSM objects.
FILTERS={
    'slipway':'["leisure"="slipway"]',
    'water_access':'["waterway"="access_point"]',
    'canoe':'["canoe"="yes"]',
    'kayak':'["kayak"="yes"]',
    'canoe_sport':'["sport"="canoe"]',
    'kayak_sport':'["sport"="kayak"]',
}
OUT=Path('data/putins_osm_candidates.geojson')
REPORT=Path('data/putins_discovery_coverage.json')
def request(tag,south,west,north,east):
    # Only one indexed filter per query; no regex and no cross-filter union.
    query=f'[out:json][timeout:45];nwr{tag}({south},{west},{north},{east});out center tags;'
    body=urllib.parse.urlencode({'data':query}).encode()
    errors=[]
    for server in SERVERS:
        req=urllib.request.Request(server,data=body,headers={
            'User-Agent':'SouthernLakeMichiganFlowAtlas/0.3 (GitHub Actions)',
            'Accept':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=65) as response:
                data=json.load(response)
            if not isinstance(data.get('elements'),list):
                raise ValueError('Missing elements array')
            return data['elements'],None
        except (urllib.error.URLError,ValueError,TimeoutError) as exc:
            errors.append(f'{server}: {exc}')
            time.sleep(1)
    return None,'; '.join(errors)
def main():
    west,south,east,north=BBOX
    found={}
    failures=[]
    succeeded=0
    # Twelve modest tiles; each tag searched independently.
    for y in range(3):
        for x in range(4):
            s=south+(north-south)*y/3;n=south+(north-south)*(y+1)/3
            w=west+(east-west)*x/4;e=west+(east-west)*(x+1)/4
            for label,tag in FILTERS.items():
                elements,error=request(tag,s,w,n,e)
                if elements is None:
                    failures.append({'tile':[s,w,n,e],'filter':label,'error':error})
                    print(f'FAILED tile {y*4+x+1}/12 filter {label}: {error}',flush=True)
                else:
                    succeeded+=1
                    for item in elements:
                        found[(item['type'],item['id'])]=item
                    print(f'OK tile {y*4+x+1}/12 filter {label}: {len(elements)} objects',flush=True)
                time.sleep(1)
    features=[]
    for (kind,osm_id),item in sorted(found.items()):
        tags=item.get('tags',{})
        center=item.get('center',item)
        if 'lon' not in center or 'lat' not in center:continue
        if tags.get('access') in ('private','no') or tags.get('shop'):continue
        name=tags.get('name') or f'OSM {kind} {osm_id}'
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[center['lon'],center['lat']]},
            'properties':{'id':f'osm-{kind}-{osm_id}','name':name,'source':'OpenStreetMap',
                'source_url':f'https://www.openstreetmap.org/{kind}/{osm_id}',
                'verification':'candidate_review','access':tags.get('access','unknown'),
                'waterway':tags.get('waterway'),'leisure':tags.get('leisure'),
                'canoe':tags.get('canoe'),'kayak':tags.get('kayak'),
                'sport':tags.get('sport'),'description':tags.get('description')}})
    complete=not failures
    report={'complete':complete,'successful_queries':succeeded,
            'total_queries':12*len(FILTERS),'failed_queries':failures,
            'candidate_count':len(features),
            'warning':'Results are candidate locations, not verified public kayak access.'}
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    # Never replace an existing more complete dataset with partial or empty results.
    if complete and features:
        OUT.write_text(json.dumps({'type':'FeatureCollection','metadata':{
            'bbox':BBOX,'complete_query_coverage':True,
            'note':'OSM access candidates; legal and physical access unverified'},
            'features':features},indent=2)+'\n')
        print(f'Wrote {len(features)} candidates',flush=True)
    else:
        print(f'Discovery incomplete: {len(failures)} failed queries; kept existing candidate dataset.',flush=True)
        if not complete:
            raise SystemExit('Incomplete OSM discovery; see data/putins_discovery_coverage.json')
        raise SystemExit('No candidates found; existing data preserved')
if __name__=='__main__':main()
