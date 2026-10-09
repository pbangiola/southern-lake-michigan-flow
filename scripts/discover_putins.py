#!/usr/bin/env python3
"""Discover put-in candidates using small OSM map rectangles intersecting river lines."""
import json, math, os, re, time, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

RIVERS=Path('data/river_segments.geojson')
OUT=Path('data/putins_osm_candidates.geojson')
REPORT=Path('data/putins_discovery_coverage.json')
PROGRESS=Path('data/putins_discovery_progress.json')
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
    # Start near the validated Des Plaines launch, then expand outward.
    return sorted(selected,key=lambda p:((p[0]*CELL-GOWE_COORD[0])**2+(p[1]*CELL-GOWE_COORD[1])**2,p[1],p[0]))
def query(cell, bounds=None):
    x,y=cell
    # Small padding includes nearby launches without requesting a whole county.
    w,s,e,n=bounds if bounds is not None else (x*CELL-.004,y*CELL-.004,(x+1)*CELL+.004,(y+1)*CELL+.004)
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
def query_adaptive(cell, bounds=None, depth=0):
    try:
        return query(cell,bounds)
    except urllib.error.HTTPError as exc:
        if exc.code not in (400,413,429) or depth>=3:
            raise
        if exc.code==429:
            raise  # Respect server rate limiting rather than multiplying requests.
        x,y=cell
        w,s,e,n=bounds if bounds is not None else (x*CELL-.004,y*CELL-.004,(x+1)*CELL+.004,(y+1)*CELL+.004)
        mx,my=(w+e)/2,(s+n)/2
        print(f\'Splitting rejected rectangle {cell} at depth {depth+1}\',flush=True)
        combined={};total=0
        for b in ((w,s,mx,my),(mx,s,e,my),(w,my,mx,n),(mx,my,e,n)):
            features,size=query_adaptive(cell,b,depth+1)
            combined.update(features);total+=size
            time.sleep(1)
        return combined,total

def main():
    tiles=cells()
    progress=json.loads(PROGRESS.read_text()) if PROGRESS.exists() else {'completed':[],'failures':{}}
    completed={tuple(c) for c in progress.get('completed',[])}
    failures=dict(progress.get('failures',{}))
    previous={}
    if OUT.exists():
        for f in json.loads(OUT.read_text()).get('features',[]):
            previous[f['properties']['id']]=f
    gowe_cell=(math.floor(GOWE_COORD[0]/CELL),math.floor(GOWE_COORD[1]/CELL))
    # Revalidate the known launch at the start of every run.
    pending=[gowe_cell]+[c for c in tiles if c not in completed and c!=gowe_cell]
    subset=pending[:BATCH_SIZE+1]
    if not subset:
        print('All stream rectangles already completed',flush=True)
        return
    attempted=[];failed_now=[];bytes_downloaded=0;gowe_found=False
    for cell in subset:
        key=f'{cell[0]},{cell[1]}'
        attempted.append(cell)
        try:
            found,size=query_adaptive(cell)
            if cell==gowe_cell and GOWE_ID not in found:
                raise ValueError('Known Gowe Park launch not found')
            if GOWE_ID in found:gowe_found=True
            previous.update(found)
            completed.add(cell)
            failures.pop(key,None)
            bytes_downloaded+=size
            print(f'OK rectangle {cell}: {len(found)} candidates, {size} bytes',flush=True)
        except (urllib.error.URLError,ValueError,ET.ParseError,TimeoutError) as exc:
            failures[key]=str(exc)
            failed_now.append({'rectangle':cell,'error':str(exc)})
            print(f'FAILED rectangle {cell}: {exc}',flush=True)
        time.sleep(1)
    PROGRESS.parent.mkdir(exist_ok=True)
    PROGRESS.write_text(json.dumps({'completed':[list(c) for c in sorted(completed)],
        'failures':failures,'total_rectangles':len(tiles)},indent=2)+'\\n')
    REPORT.write_text(json.dumps({'method':'OSM map API stream corridor rectangles',
        'total_rectangles':len(tiles),'completed_rectangles':len(completed),
        'remaining_rectangles':len(set(tiles)-completed),
        'attempted_this_run':len(attempted),'failed_this_run':failed_now,
        'unresolved_failures':len(failures),'gowe_found_in_current_run':gowe_found,
        'bytes_downloaded':bytes_downloaded,'candidate_count':len(previous),
        'complete_region':set(tiles)<=completed,
        'warning':'Unverified OSM access candidates; river navigability and public access not established'},indent=2)+'\\n')
    OUT.write_text(json.dumps({'type':'FeatureCollection','metadata':{
        'source':'OSM map API stream corridor rectangles',
        'note':'Incremental unverified candidates'},
        'features':list(previous.values())},indent=2)+'\\n')
    if failed_now:raise SystemExit(f'{len(failed_now)} rectangle(s) failed; progress preserved for retry')
    print(f'Progress: {len(completed)}/{len(tiles)} rectangles, {len(previous)} candidates',flush=True)
if __name__=='__main__':main()
