#!/usr/bin/env python3
"""Tiny OSM API validation around the known Gowe Park canoe launch."""
import json,re,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
BBOX=(-87.923,42.364,-87.913,42.373)
KNOWN_ID='12396073908'
PATTERN=re.compile(r'\b(canoe|kayak|boat)\s+launch\b',re.I)
url='https://api.openstreetmap.org/api/0.6/map?bbox='+','.join(map(str,BBOX))
req=urllib.request.Request(url,headers={'User-Agent':'SouthernLakeMichiganFlowAtlas-validation/0.1'})
with urllib.request.urlopen(req,timeout=90) as response:
    xml=response.read()
print('Downloaded',len(xml),'bytes from OSM map API',flush=True)
root=ET.fromstring(xml)
matches=[]
known=None
for node in root.findall('node'):
    tags={t.attrib['k']:t.attrib['v'] for t in node.findall('tag')}
    name=tags.get('name','')
    if node.attrib['id']==KNOWN_ID:known={'name':name,'tags':tags}
    if PATTERN.search(name):
        matches.append({'id':node.attrib['id'],'name':name,'tags':tags,
                        'coordinates':[float(node.attrib['lon']),float(node.attrib['lat'])]})
report={'bbox':BBOX,'source_url':url,'download_bytes':len(xml),
        'known_osm_node_id':KNOWN_ID,'known_node_found':known is not None,
        'known_node':known,'matching_named_nodes':matches,
        'node_count':len(root.findall('node'))}
Path('data').mkdir(exist_ok=True)
Path('data/putins_validation_gowe.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
assert known is not None,'Known Gowe Park OSM node absent from downloaded map'
assert matches,'No canoe/kayak/boat launch name matches in validation area'
print('PASS: Known launch and name match found')
