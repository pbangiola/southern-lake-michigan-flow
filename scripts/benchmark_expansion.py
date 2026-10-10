#!/usr/bin/env python3
"""Benchmark and adapt the atlas discovery pace, without unbounded downloads.

Runs in GitHub Actions, never in visitors' browsers. Tracks three layers
independently and persists a compact performance report.
"""
import argparse
import json
import math
import time
import urllib.error
from pathlib import Path
import expand_atlas as atlas

LAYERS=("launches","rivers","gauges")
PROGRESS=Path("data/expansion_pace.json")
TOTAL=atlas.NX*atlas.NY

def run():
    p=argparse.ArgumentParser()
    p.add_argument("--budget-seconds",type=int,default=240)
    p.add_argument("--budget-mb",type=float,default=25)
    p.add_argument("--max-requests",type=int,default=24)
    p.add_argument("--probe",action="store_true",help="Measure without publishing or advancing tiles")
    args=p.parse_args()
    if not 30<=args.budget_seconds<=600 or not 1<=args.budget_mb<=100 or not 1<=args.max_requests<=100:
        p.error("Budgets out of allowed range")
    state=json.loads(PROGRESS.read_text()) if PROGRESS.exists() else {"layers":{},"history":[]}
    for layer in LAYERS:
        state["layers"].setdefault(layer,{"next_tile":0,"delay_seconds":3,"successes":0,"failures":0})
    start=time.monotonic()
    used=0
    requests=0
    blocked=set()
    while requests<args.max_requests and time.monotonic()-start<args.budget_seconds-60 and used<args.budget_mb*1e6:
        active=False
        for layer in LAYERS:
            if layer in blocked:continue
            info=state["layers"][layer]
            idx=info["next_tile"]
            if idx>=TOTAL:continue
            if requests>=args.max_requests or used>=args.budget_mb*1e6 or time.monotonic()-start>=args.budget_seconds-60:break
            ix,iy=idx%atlas.NX,idx//atlas.NX
            w=round(atlas.WEST+ix*atlas.STEP,5);s=round(atlas.SOUTH+iy*atlas.STEP,5)
            e=min(round(w+atlas.STEP,5),atlas.EAST);n=min(round(s+atlas.STEP,5),atlas.NORTH)
            before=time.monotonic()
            sizes=[]
            original=atlas.request
            def measured(url,body=None):
                nonlocal used
                raw=original(url,body)
                size=len(raw.encode("utf-8"))
                sizes.append(size)
                used+=size
                return raw
            atlas.request=measured
            try:
                if layer=="gauges":
                    features=atlas.usgs_tile(s,w,n,e)
                    dest=atlas.GAUGES
                    key=lambda f:f["properties"]["site"]
                else:
                    elements=atlas.osm_tile(s,w,n,e)
                    launches,rivers=atlas.extract_osm(elements)
                    features=launches if layer=="launches" else rivers
                    dest=atlas.LAUNCHES if layer=="launches" else atlas.RIVERS
                    key=lambda f:f["properties"]["id"]
                added=0 if args.probe else atlas.merge(dest,features,key)
                if not args.probe:info["next_tile"]+=1
                info["successes"]+=1
                if info["successes"]%3==0:info["delay_seconds"]=max(2,round(info["delay_seconds"]*0.8,2))
                outcome="ok"
            except Exception as exc:
                info["failures"]+=1
                info["delay_seconds"]=min(120,info["delay_seconds"]*2+5)
                blocked.add(layer)
                outcome=str(exc)[:160]
                features=[];added=0
            finally:
                atlas.request=original
            elapsed=round(time.monotonic()-before,2)
            entry={"layer":layer,"tile":idx,"seconds":elapsed,"bytes":sum(sizes),"features":len(features),"added":added,"result":outcome}
            state["history"]=(state["history"]+[entry])[-120:]
            print(json.dumps(entry),flush=True)
            requests+=1
            active=True
            if not args.probe:
                PROGRESS.parent.mkdir(exist_ok=True)
                PROGRESS.write_text(json.dumps(state,indent=2)+"\n")
            if time.monotonic()-start<args.budget_seconds-60:
                time.sleep(min(info["delay_seconds"],5))
        if not active:break
    state["last_run"]={"requests":requests,"bytes":used,"elapsed_seconds":round(time.monotonic()-start,1),"probe":args.probe}
    if not args.probe:
        PROGRESS.write_text(json.dumps(state,indent=2)+"\n")
    print(json.dumps(state["last_run"]),flush=True)

if __name__=="__main__":run()
