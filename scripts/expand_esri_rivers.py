#!/usr/bin/env python3
"""Adaptive Esri river ingestion: learn page size and delay from measured responses."""
import argparse,json,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path
from expand_atlas import merge,RIVERS,request
BASE="https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_Rivers_and_Streams/FeatureServer/0/query"
STATE=Path("data/esri_river_progress.json")
BBOX="-88.7,40.9,-85.4,43.2"
def query(params):
    url=BASE+"?"+urllib.parse.urlencode(params)
    obj=json.loads(request(url))
    if "error" in obj:raise RuntimeError(str(obj["error"]))
    return obj
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seconds",type=int,default=180)
    p.add_argument("--mb",type=float,default=20)
    p.add_argument("--max-requests",type=int,default=30)
    args=p.parse_args()
    state=json.loads(STATE.read_text()) if STATE.exists() else {"offset":0,"batch":100,"delay":2.0,"success_streak":0,"done":False,"history":[]}
    if state["done"]:print("Esri river collection complete");return
    start=time.monotonic();bytes_used=0
    for attempt in range(args.max_requests):
        if time.monotonic()-start>args.seconds-35 or bytes_used>=args.mb*1e6:break
        batch=min(1000,max(10,int(state["batch"])))
        params={"where":"1=1","geometry":BBOX,"geometryType":"esriGeometryEnvelope","inSR":4326,
          "spatialRel":"esriSpatialRelIntersects","outSR":4326,"outFields":"OBJECTID,Name,Feature,State",
          "returnGeometry":"true","f":"geojson","resultOffset":state["offset"],"resultRecordCount":batch,
          "orderByFields":"OBJECTID"}
        t=time.monotonic()
        try:
            obj=query(params)
            if obj.get("type")!="FeatureCollection":raise ValueError("Expected GeoJSON FeatureCollection")
            raw_size=len(json.dumps(obj,separators=(",",":")).encode())
            bytes_used+=raw_size
            features=[]
            for feature in obj.get("features",[]):
                props=feature.get("properties") or {}
                ident=props.get("OBJECTID") or feature.get("id")
                if ident is None:continue
                props.update({"id":"esri-river-"+str(ident),"river_name":props.get("Name") or "Unnamed waterway",
                  "source":"Esri USA Rivers and Streams","verification":"regional_reference_only"})
                feature["properties"]=props
                if feature.get("geometry",{}).get("type") in ("LineString","MultiLineString"):
                    features.append(feature)
            added=merge(RIVERS,features,lambda f:f["properties"]["id"])
            state["offset"]+=len(obj["features"])
            elapsed=time.monotonic()-t
            state["success_streak"]+=1
            # AIMD: additive growth, multiplicative reduction; both learned from the service.
            if elapsed<8 and raw_size<600000 and state["success_streak"]>=2:
                state["batch"]=min(1000,batch+100)
                state["delay"]=max(0.5,state["delay"]*0.85)
            elif elapsed>25 or raw_size>1100000:
                state["batch"]=max(10,batch//2)
                state["delay"]=min(60,state["delay"]*1.5)
            if len(obj["features"])<batch and not obj.get("properties",{}).get("exceededTransferLimit"):
                state["done"]=True
            result={"status":"ok","batch":batch,"features":len(features),"added":added,
                    "bytes":raw_size,"seconds":round(elapsed,2)}
        except Exception as exc:
            state["success_streak"]=0
            state["batch"]=max(10,batch//2)
            state["delay"]=min(120,state["delay"]*2+2)
            result={"status":"error","batch":batch,"seconds":round(time.monotonic()-t,2),"message":str(exc)[:180]}
            state["history"]=(state["history"]+[result])[-60:]
            STATE.parent.mkdir(exist_ok=True)
            STATE.write_text(json.dumps(state,indent=2)+"\n")
            print(json.dumps(result),flush=True)
            break
        state["history"]=(state["history"]+[result])[-60:]
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(state,indent=2)+"\n")
        print(json.dumps(result),flush=True)
        if state["done"]:break
        time.sleep(min(state["delay"],max(0,args.seconds-(time.monotonic()-start)-30)))
if __name__=="__main__":main()
