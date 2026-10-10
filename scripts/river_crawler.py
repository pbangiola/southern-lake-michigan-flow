#!/usr/bin/env python3
"""Incremental, bounded river-adjacent discovery; writes candidate data, never publishes it."""
import argparse, json, math, urllib.parse, urllib.request
from pathlib import Path

def load(path):
    if not Path(path).exists(): return {"type":"FeatureCollection","features":[]}
    return json.loads(Path(path).read_text())
def save(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,separators=(',',':')))
def key(f):
    p=f.get("properties") or {}
    return str(p.get("site") or p.get("site_no") or p.get("id") or f.get("geometry",{}).get("coordinates"))
def request(url):
    req=urllib.request.Request(url,headers={"User-Agent":"southern-lake-michigan-flow/river-crawler (GitHub project)"})
    with urllib.request.urlopen(req,timeout=45) as response:return json.load(response)
def bounds(features,padding=.025):
    xy=[]
    for f in features:
        coords=f.get("geometry",{}).get("coordinates") or []
        if f.get("geometry",{}).get("type")=="Point": coords=[coords]
        for p in coords:
            if isinstance(p,(list,tuple)) and len(p)>1 and isinstance(p[0],(int,float)): xy.append(p)
    if not xy:return None
    return [min(p[0] for p in xy)-padding,min(p[1] for p in xy)-padding,max(p[0] for p in xy)+padding,max(p[1] for p in xy)+padding]
def discover_gauges(bbox):
    w,s,e,n=bbox
    url="https://waterservices.usgs.gov/nwis/site/?"+urllib.parse.urlencode({"format":"rdb","bBox":f"{w:.5f},{s:.5f},{e:.5f},{n:.5f}","siteType":"ST","siteStatus":"active"})
    req=urllib.request.Request(url,headers={"User-Agent":"southern-lake-michigan-flow/river-crawler"})
    with urllib.request.urlopen(req,timeout=45) as response: lines=response.read().decode().splitlines()
    records=[line.split("\t") for line in lines if line and not line.startswith("#")]
    if len(records)<3:return []
    header=records[0];result=[]
    for values in records[2:]:
        p=dict(zip(header,values))
        try:lat=float(p["dec_lat_va"]);lon=float(p["dec_long_va"])
        except (ValueError,KeyError):continue
        site=p.get("site_no","")
        if not site:continue
        result.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},"properties":{"site":site,"name":p.get("station_nm",""),"source":"USGS NWIS site inventory","stage":None,"stage_status":"not fetched"}})
    return result
def discover_launches(bbox):
    w,s,e,n=bbox
    query=f'[out:json][timeout:35];(nwr["leisure"="slipway"]({s},{w},{n},{e});nwr["waterway"="access_point"]({s},{w},{n},{e});nwr["canoe"="yes"]({s},{w},{n},{e}););out center 500;'
    req=urllib.request.Request("https://overpass.kumi.systems/api/interpreter",data=urllib.parse.urlencode({"data":query}).encode(),headers={"User-Agent":"southern-lake-michigan-flow/river-crawler"})
    with urllib.request.urlopen(req,timeout=50) as response:data=json.load(response)
    out=[]
    for x in data.get("elements",[]):
        lat=x.get("lat",x.get("center",{}).get("lat"));lon=x.get("lon",x.get("center",{}).get("lon"))
        if lat is None or lon is None:continue
        tags=x.get("tags",{})
        out.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},"properties":{"id":f'osm-{x["type"]}-{x["id"]}',"name":tags.get("name",""),"access":tags.get("access","unknown"),"source":"OpenStreetMap candidate","verified":False}})
    return out
def merge(original,additional):
    by={key(f):f for f in original.get("features",[])}
    for f in additional:by.setdefault(key(f),f)
    return {"type":"FeatureCollection","features":list(by.values())}
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--network",default="data/river_segments_3dhp_review.geojson")
    a.add_argument("--state",default="local/river_crawler_state.json")
    a.add_argument("--output",default="local/river_crawler")
    a.add_argument("--max-boxes",type=int,default=2)
    a.add_argument("--max-features",type=int,default=15000)
    a.add_argument("--nationwide",action="store_true",help="Scan CONUS in bounded geographic cells (discovery only)")
    a.add_argument("--illinois-basin",action="store_true",help="Prioritize Illinois River basin discovery grid; not a watershed boundary")
    args=a.parse_args()
    network=load(args.network);features=network.get("features",[])[:args.max_features]
    statepath=Path(args.state)
    state=json.loads(statepath.read_text()) if statepath.exists() else {"cursor":0}
    cursor=state.get("cursor",0);boxes=[]
    if args.illinois_basin:
        # Approximate Illinois River drainage search extent; features still need HUC validation.
        cells=[[-93+x*.5,37+y*.5,-92.5+x*.5,37.5+y*.5] for y in range(14) for x in range(14)]
        boxes=cells[cursor:cursor+args.max_boxes]
        consumed=len(boxes)
    elif args.nationwide:
        # Geographic coverage grid, not a connected river network. Includes lower 48 only.
        cells=[[-125+x,24+y,-124+x,25+y] for y in range(26) for x in range(59)]
        boxes=cells[cursor:cursor+args.max_boxes]
        consumed=len(boxes)
    # Fixed-size bounded batches avoid broad Overpass/NWIS queries.
    consumed=0 if not (args.nationwide or args.illinois_basin) else consumed
    for f in ([] if (args.nationwide or args.illinois_basin) else features[cursor:]):
        consumed+=1
        geom=f.get("geometry",{})
        if geom.get("type")!="LineString":continue
        bb=bounds([f],.01)
        if bb and bb[2]-bb[0]<.25 and bb[3]-bb[1]<.25:boxes.append(bb)
        if len(boxes)>=args.max_boxes:break
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    failures=[]
    for name,fn in (("gauges",discover_gauges),("launches",discover_launches)):
        path=output/(name+"_candidates.geojson");existing=load(path);found=[]
        for bb in boxes:
            try:found.extend(fn(bb))
            except Exception as error:
                failures.append({"source":name,"bbox":bb,"error":str(error)})
                print(f"{name} discovery deferred for {bb}: {error}")
        save(path,merge(existing,found))
        print(name,len(found),"newly observed",len(load(path)["features"]),"total candidates")
    total=len(cells) if (args.nationwide or args.illinois_basin) else len(features)
    if failures:
        save(output/"failed_requests.json",failures)
        raise SystemExit(f"{len(failures)} source requests failed; refusing to advance cursor")
    state["cursor"]=min(total,cursor+consumed)
    state["complete"]=state["cursor"]>=total
    state["scope"]="Illinois River basin approximate discovery grid" if args.illinois_basin else "CONUS discovery grid" if args.nationwide else "river network review"
    # Completed scans remain complete; reset only when explicitly requested.
    save(statepath,state)
if __name__=="__main__":main()
