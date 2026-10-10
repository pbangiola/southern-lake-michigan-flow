#!/usr/bin/env python3
"""Validate discovered candidates and publish only conservative, deduplicated additions."""
import json, math
from pathlib import Path

def read(path):
    p=Path(path)
    return json.loads(p.read_text()) if p.exists() else {"type":"FeatureCollection","features":[]}
def write(path,data):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(data,separators=(",",":")))
def valid(f):
    if f.get("geometry",{}).get("type")!="Point":return False
    c=f["geometry"].get("coordinates",[])
    return len(c)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in c) and -180<=c[0]<=180 and -90<=c[1]<=90
def merge(target,source,id_field):
    original=read(target)
    features=[f for f in original.get("features",[]) if valid(f)]
    seen={str(f.get("properties",{}).get(id_field,"")) for f in features}
    added=0
    for f in read(source).get("features",[]):
        if not valid(f):continue
        p=f.get("properties",{})
        key=str(p.get(id_field,""))
        if not key or key in seen:continue
        if id_field=="site" and (not key.isdigit() or len(key)<7 or len(key)>15):continue
        if id_field=="id" and (not key.startswith("osm-") or p.get("access") in ("private","no")):continue
        p["candidate_unverified"]=True
        features.append(f);seen.add(key);added+=1
    if added:write(target,{"type":"FeatureCollection","features":features})
    print(target,":",added,"added; total",len(features))
if __name__=="__main__":
    merge("data/gauges_expansion.geojson","local/river_crawler/gauges_candidates.geojson","site")
    merge("data/putins_expansion.geojson","local/river_crawler/launches_candidates.geojson","id")
