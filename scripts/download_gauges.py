#!/usr/bin/env python3
"""Download the complete USGS stream-station inventory for the atlas bbox.

Run from repository root: python3 scripts/download_gauges.py
Resume safely: completed tiles are checkpointed after each request.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import expand_atlas as atlas

CHECKPOINT=Path("local/gauge_download_progress.json")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--delay",type=float,default=0.15,help="Seconds between successful tiles")
    p.add_argument("--retry",type=int,default=4)
    p.add_argument("--reset",action="store_true",help="Restart tile traversal (preserves existing gauge inventory)")
    a=p.parse_args()
    if a.delay<0 or a.retry<1:p.error("delay must be >=0 and retry >=1")
    atlas.GAUGES.parent.mkdir(parents=True,exist_ok=True)
    CHECKPOINT.parent.mkdir(parents=True,exist_ok=True)
    state={"next_tile":0,"failed":[]}
    if CHECKPOINT.exists() and not a.reset:
        state=json.loads(CHECKPOINT.read_text())
    total=atlas.NX*atlas.NY
    for idx in range(state["next_tile"],total):
        ix,iy=idx%atlas.NX,idx//atlas.NX
        w=round(atlas.WEST+ix*atlas.STEP,5)
        s=round(atlas.SOUTH+iy*atlas.STEP,5)
        e=min(round(w+atlas.STEP,5),atlas.EAST)
        n=min(round(s+atlas.STEP,5),atlas.NORTH)
        for attempt in range(a.retry):
            try:
                features=atlas.usgs_tile(s,w,n,e)
                added=atlas.merge(atlas.GAUGES,features,lambda f:str(f["properties"]["site"]))
                state["next_tile"]=idx+1
                CHECKPOINT.write_text(json.dumps(state,indent=2)+"\n")
                print(f"{idx+1}/{total}: found {len(features)}, added {added}",flush=True)
                break
            except Exception as exc:
                if attempt==a.retry-1:
                    print(f"Stopped at tile {idx}: {exc}. Rerun to resume.",file=sys.stderr)
                    raise SystemExit(1)
                wait=min(60,2**attempt*3)
                print(f"Tile {idx} attempt {attempt+1} failed: {exc}; retry in {wait}s",flush=True)
                time.sleep(wait)
        time.sleep(a.delay)
    count=len(atlas.read_collection(atlas.GAUGES)["features"])
    print(f"Complete: {count} unique discovered stations in {atlas.GAUGES}")
    print("Next: python3 Watershed.py --offline")

if __name__=="__main__":
    main()
