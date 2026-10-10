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
    xy=[p for f in features for p in (f.get("geometry",{}).get("coordinates") or []) if isinstance(p,list) and len(p)>1 and isinstance(p[0],(int,float))]
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
    args=a.parse_args()
    network=load(args.network);features=network.get("features",[])
    statepath=Path(args.state)
    state=json.loads(statepath.read_text()) if statepath.exists() else {"cursor":0}
    cursor=state.get("cursor",0);boxes=[]
    # Fixed-size bounded batches avoid broad Overpass/NWIS queries.
    for f in features[cursor:]:
        geom=f.get("geometry",{})
        if geom.get("type")!="LineString":continue
        bb=bounds([f],.01)
        if bb and bb[2]-bb[0]<.25 and bb[3]-bb[1]<.25:boxes.append(bb)
        if len(boxes)>=args.max_boxes:break
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    for name,fn in (("gauges",discover_gauges),("launches",discover_launches)):
        path=output/(name+"_candidates.geojson");existing=load(path);found=[]
        for bb in boxes:
            try:found.extend(fn(bb))
            except Exception as error:print(f"{name} discovery deferred for {bb}: {error}")
        save(path,merge(existing,found))
        print(name,len(found),"newly observed",len(load(path)["features"]),"total candidates")
    state["cursor"]=min(len(features),cursor+max(1,len(boxes)))
    if state["cursor"]>=len(features):state["cursor"]=0
    save(statepath,state)
if __name__=="__main__":main()
