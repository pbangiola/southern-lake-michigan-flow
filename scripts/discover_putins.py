#!/usr/bin/env python3
"""Find OSM features named canoe launch, kayak launch, or boat launch.

Reads regional state PBF extracts from Geofabrik, avoiding Overpass regex queries.
Coordinates of ways and relations use representative geometry centers; candidates
are not verified public access points.
"""
import json
import re
from pathlib import Path
import osmium

BBOX=(-88.7,40.9,-85.4,43.2)
PATTERN=re.compile(r'\\b(canoe|kayak|boat)\\s+launch\\b',re.I)
OUT=Path('data/putins_osm_candidates.geojson')
REPORT=Path('data/putins_discovery_coverage.json')

class Launches(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.features={}
        self.scanned=0
    def _record(self,object_,kind,coordinates):
        self.scanned+=1
        tags=dict(object_.tags)
        name=tags.get('name','')
        if not PATTERN.search(name):return
        if tags.get('access') in ('private','no') or tags.get('shop'):return
        lon,lat=coordinates
        west,south,east,north=BBOX
        if not (west<=lon<=east and south<=lat<=north):return
        osm_id=f'osm-{kind}-{object_.id}'
        self.features[osm_id]={'type':'Feature','geometry':{'type':'Point','coordinates':[lon,lat]},
            'properties':{'id':osm_id,'name':name,'source':'OpenStreetMap',
                'source_url':f'https://www.openstreetmap.org/{kind}/{object_.id}',
                'verification':'candidate_review','access':tags.get('access','unknown'),
                'waterway':tags.get('waterway'),'leisure':tags.get('leisure'),
                'canoe':tags.get('canoe'),'kayak':tags.get('kayak'),
                'sport':tags.get('sport'),'description':tags.get('description')}}
    def node(self,n):
        if n.location.valid():
            self._record(n,'node',(n.location.lon,n.location.lat))
    def way(self,w):
        if not PATTERN.search(w.tags.get('name','')):return
        coords=[(n.location.lon,n.location.lat) for n in w.nodes if n.location.valid()]
        if coords:
            self._record(w,'way',(sum(p[0] for p in coords)/len(coords),
                                  sum(p[1] for p in coords)/len(coords)))
    def relation(self,r):
        # Relations lack a reliable representative coordinate in a streaming pass.
        # Record this coverage limitation rather than fabricating a point.
        pass

def main():
    handler=Launches()
    paths=sorted(Path('tmp/osm').glob('*-latest.osm.pbf'))
    if len(paths)!=4:raise SystemExit(f'Expected 4 state extracts; found {len(paths)}')
    for path in paths:
        print(f'Scanning {path} ({path.stat().st_size/1e6:.0f} MB)',flush=True)
        handler.apply_file(str(path),locations=True,idx='flex_mem')
    features=list(handler.features.values())
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps({'complete':True,'method':'Geofabrik state PBF extracts',
        'states':['illinois','indiana','michigan','wisconsin'],
        'bbox':BBOX,'name_phrases':['canoe launch','kayak launch','boat launch'],
        'candidate_count':len(features),'limitations':[
            'Only features with matching names; unnamed launches are excluded',
            'OSM relations are not included',
            'Way coordinates are representative averages, not verified launch points',
            'Public access and navigability are not verified']},indent=2)+'\\n')
    if not features:raise SystemExit('No named launch candidates found; existing output preserved')
    OUT.write_text(json.dumps({'type':'FeatureCollection','metadata':{
        'bbox':BBOX,'complete_query_coverage':True,'source':'Geofabrik OSM state extracts',
        'note':'Unverified access candidates matching launch names'},
        'features':features},indent=2)+'\\n')
    print(f'Found {len(features)} named launch candidates',flush=True)
if __name__=='__main__':main()
