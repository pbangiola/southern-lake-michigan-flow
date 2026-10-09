#!/usr/bin/env python3
"""Resolve catalog put-ins using Nominatim; cached, sequential, review-required."""
import argparse, difflib, json, os, time, urllib.parse, urllib.request
from pathlib import Path
BBOX=(-88.7,40.9,-85.4,43.2)
def inside(xy):
    return BBOX[0]<=xy[0]<=BBOX[2] and BBOX[1]<=xy[1]<=BBOX[3]
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--contact',default=os.getenv('NOMINATIM_CONTACT'))
    p.add_argument('--catalog',type=Path,default=Path('data/putins_catalog.json'))
    p.add_argument('--cache',type=Path,default=Path('data/putins_geocode_cache.json'))
    p.add_argument('--overrides',type=Path,default=Path('data/putins_overrides.json'))
    a=p.parse_args()
    if not a.contact: p.error('Set NOMINATIM_CONTACT secret or --contact')
    catalog=json.loads(a.catalog.read_text())
    cache=json.loads(a.cache.read_text()) if a.cache.exists() else {}
    overrides=json.loads(a.overrides.read_text()) if a.overrides.exists() else {}
    features=[];review=[];requests=0
    for item in catalog:
        name=item['name'];key=item['id'];override=overrides.get(key,{})
        xy=override.get('coordinates') or item.get('coordinates')
        candidates=[];status='verified_manual' if override.get('coordinates') else 'kml_coordinates'
        if not xy:
            if name not in cache:
                params=urllib.parse.urlencode({'q':name,'format':'jsonv2','limit':5,'addressdetails':1,
                    'viewbox':f'{BBOX[0]},{BBOX[3]},{BBOX[2]},{BBOX[1]}','bounded':0})
                req=urllib.request.Request('https://nominatim.openstreetmap.org/search?'+params,
                    headers={'User-Agent':f'SouthernLakeMichiganFlowAtlas/0.1 ({a.contact})'})
                if requests:time.sleep(1.2)
                try:
                    with urllib.request.urlopen(req,timeout=30) as response:cache[name]=json.load(response)
                except Exception as exc:
                    print(f'Lookup failed for {name}: {exc}')
                    cache[name]=[]
                requests+=1
            matches=[]
            for result in cache[name]:
                try:point=[float(result['lon']),float(result['lat'])]
                except (ValueError,KeyError):continue
                if not inside(point):continue
                title=result.get('name') or result.get('display_name','').split(',')[0]
                score=difflib.SequenceMatcher(None,name.casefold(),title.casefold()).ratio()
                matches.append((score,result,point))
            matches.sort(key=lambda x:x[0],reverse=True)
            candidates=[{'name':r.get('display_name'),'score':round(score,3),'osm_type':r.get('osm_type'),'osm_id':r.get('osm_id')} for score,r,_ in matches[:3]]
            if matches:
                score,_,xy=matches[0]
                second=matches[1][0] if len(matches)>1 else 0
                status='candidate_high' if score>=.88 and score-second>=.12 else 'candidate_review'
            else:status='not_found'
        if not xy or not inside(xy):
            review.append({'id':key,'name':name,'status':status if not xy else 'outside_atlas_bbox','candidates':candidates})
            continue
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':xy},
            'properties':{'id':key,'name':name,'source_url':item.get('source_url'),
                'verification':status,'access':'unknown','candidate_matches':candidates}})
        if status!='verified_manual':
            review.append({'id':key,'name':name,'status':status,'coordinates':xy,'candidates':candidates})
    a.cache.parent.mkdir(parents=True,exist_ok=True)
    a.cache.write_text(json.dumps(cache,indent=2)+'\n')
    Path('data/putins.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},indent=2)+'\n')
    Path('data/putins_review.json').write_text(json.dumps(review,indent=2)+'\n')
    print(f'{len(features)} candidate put-ins; {len(review)} need review; {requests} new lookups')
if __name__=='__main__':main()
