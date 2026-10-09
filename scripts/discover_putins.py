#!/usr/bin/env python3
"""Discover put-in candidates using small OSM map rectangles intersecting river lines."""
import json, math, os, re, time, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

RIVERS=Path('data/river_segments.geojson')
OUT=Path('data/putins_osm_candidates.geojson')
REPORT=Path('data/putins_discovery_coverage.json')
CELL=0.04
BATCH=int(os.environ.get('DISCOVERY_BATCH','0'))
BATCH_SIZE=int(os.environ.get('DISCOVERY_BATCH_SIZE','20'))
VALIDATE_GOWE=os.environ.get('DISCOVERY_VALIDATE_GOWE','1')=='1'
GOWE_ID='osm-node-12396073908'
GOWE_COORD=(-87.9177405,42.3686995)
PATTERN=re.compile(r'\b(canoe|kayak|boat)\s+launch\b',re.I)
def lines(geom):
    if geom['type']=='LineString':return [geom['coordinates']]
    if geom['type']=='MultiLineString':return geom['coordinates']
    return []
def cells():
    river=json.loads(RIVERS.read_text())
    selected=set()
    for feature in river['features']:
        for line in lines(feature['geometry']):
            for a,b in zip(line,line[1:]):
                # Sample every ~0.02 degrees to avoid skipping grid cells.
                steps=max(1,math.ceil(max(abs(a[0]-b[0]),abs(a[1]-b[1]))/(CELL/2)))
                for i in range(steps+1):
                    x=a[0]+(b[0]-a[0])*i/steps
                    y=a[1]+(b[1]-a[1])*i/steps
                    selected.add((math.floor(x/CELL),math.floor(y/CELL)))
    return sorted(selected,key=lambda p:(p[1],p[0]))
def query(cell):
    x,y=cell
    # Small padding includes nearby launches without requesting a whole county.
    w,s=x*CELL-.004,y*CELL-.004
    e,n=(x+1)*CELL+.004,(y+1)*CELL+.004
    url='https://api.openstreetmap.org/api/0.6/map?bbox='+','.join(f'{v:.5f}' for v in (w,s,e,n))
    req=urllib.request.Request(url,headers={'User-Agent':'SouthernLakeMichiganFlowAtlas/0.5 (GitHub Actions)'})
    with urllib.request.urlopen(req,timeout=90) as response:
        payload=response.read()
    if len(payload)>40_000_000:raise ValueError('Oversized OSM map response')
    root=ET.fromstring(payload)
    nodes={n.get('id'):(float(n.get('lon')),float(n.get('lat'))) for n in root.findall('node')}
    found={}
    for kind in ('node','way'):
        for item in root.findall(kind):
            tags={t.get('k'):t.get('v') for t in item.findall('tag')}
            name=tags.get('name','')
            # Names and indexed access tags are both useful; retain for review.
            named=bool(PATTERN.search(name))
            tagged=tags.get('leisure')=='slipway' or tags.get('waterway')=='access_point'
            if not (named or tagged):continue
            if tags.get('access') in ('private','no') or tags.get('shop'):continue
            if kind=='node':coord=nodes.get(item.get('id'))
            else:
                coords=[nodes[nd.get('ref')] for nd in item.findall('nd') if nd.get('ref') in nodes]
                coord=(sum(p[0] for p in coords)/len(coords),sum(p[1] for p in coords)/len(coords)) if coords else None
            if coord is None:continue
            key=f'osm-{kind}-{item.get("id")}'
            found[key]={'type':'Feature','geometry':{'type':'Point','coordinates':list(coord)},
                'properties':{'id':key,'name':name or key,'source':'OpenStreetMap',
                'source_url':f'https://www.openstreetmap.org/{kind}/{item.get("id")}',
                'verification':'candidate_review','access':tags.get('access','unknown'),
                'waterway':tags.get('waterway'),'leisure':tags.get('leisure'),
                'canoe':tags.get('canoe'),'kayak':tags.get('kayak'),
                'sport':tags.get('sport'),'description':tags.get('description'),
                'match_type':'launch_name' if named else 'access_tag'}}
    return found,len(payload)
def main():
    tiles=cells()
    start=BATCH*BATCH_SIZE
    subset=tiles[start:start+BATCH_SIZE]
    if VALIDATE_GOWE:
        gowe_cell=(math.floor(GOWE_COORD[0]/CELL),math.floor(GOWE_COORD[1]/CELL))
        if gowe_cell not in subset:subset=[gowe_cell]+subset
        print('Validating known Gowe Park launch in rectangle',gowe_cell,flush=True)
    if not subset:raise SystemExit(f'Batch {BATCH} beyond {len(tiles)} stream rectangles')
    previous={}
    if OUT.exists():
        for f in json.loads(OUT.read_text()).get('features',[]):
            previous[f['properties']['id']]=f
    failures=[];bytes_downloaded=0
    gowe_found=False
    for idx,cell in enumerate(subset,start+1):
        try:
            found,size=query(cell)
            previous.update(found);bytes_downloaded+=size
            if GOWE_ID in found:gowe_found=True
            print(f'OK rectangle {idx}/{len(tiles)}: {len(found)} candidates, {size} bytes',flush=True)
        except (urllib.error.URLError,ValueError,ET.ParseError,TimeoutError) as exc:
            failures.append({'rectangle':cell,'error':str(exc)})
            print(f'FAILED rectangle {idx}/{len(tiles)}: {exc}',flush=True)
        time.sleep(1)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps({'method':'OSM map API stream corridor rectangles',
        'batch':BATCH,'batch_size':BATCH_SIZE,'total_rectangles':len(tiles),
        'attempted_rectangles':len(subset),'failed_rectangles':failures,
        'complete_batch':not failures and (not VALIDATE_GOWE or gowe_found),
        'gowe_validation_enabled':VALIDATE_GOWE,'gowe_found_in_current_run':gowe_found,
        'bytes_downloaded':bytes_downloaded,
        'candidate_count':len(previous),
        'warning':'Candidates are not verified public or navigable access. Entire region is not complete until all batches are run.'},indent=2)+'\n')
    if failures:raise SystemExit('Some rectangles failed; existing candidates preserved; see coverage report')
    if VALIDATE_GOWE and not gowe_found:
        raise SystemExit('VALIDATION FAILED: Gowe Park canoe launch not discovered; existing candidates preserved')
    if VALIDATE_GOWE:print('PASS: Gowe Park launch discovered by production rectangle parser',flush=True)
    OUT.write_text(json.dumps({'type':'FeatureCollection','metadata':{
        'source':'OSM map API stream corridor rectangles',
        'note':'Incremental unverified launch candidates; regional coverage incomplete'},
        'features':list(previous.values())},indent=2)+'\n')
    print(f'Batch {BATCH} complete: {len(previous)} cumulative candidates',flush=True)
if __name__=='__main__':main()
