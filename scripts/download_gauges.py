#!/usr/bin/env python3
"""Resumable nationwide USGS stream-station inventory download.

Run: python3 scripts/download_gauges.py
Downloads USGS agency stream stations across the US and territories to
local/gauges_us.geojson. Large source inventory stays off GitHub.
"""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import expand_atlas as atlas

DEST=Path("local/gauges_us.geojson")
CHECKPOINT=Path("local/gauge_download_us_progress.json")
# Region envelopes include contiguous US, Alaska/Aleutians, Hawaii and US Pacific/
# Caribbean territories. Only agency_code=USGS, site_type_code=ST are retained.
REGIONS=[
    ("continental_alaska", -180, 15, -60, 75),
    ("pacific_territories", 120, -20, 180, 30),
]
STEP=5

def tiles():
    for region,w,s,e,n in REGIONS:
        lat=s
        while lat<n:
            lon=w
            while lon<e:
                yield region,round(lon,4),round(lat,4),round(min(e,lon+STEP),4),round(min(n,lat+STEP),4)
                lon+=STEP
            lat+=STEP

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--delay",type=float,default=0.2)
    p.add_argument("--retry",type=int,default=5)
    p.add_argument("--reset",action="store_true",help="Restart tile traversal, retaining downloaded records")
    a=p.parse_args()
    if a.delay<0 or a.retry<1:p.error("Invalid delay/retry")
    DEST.parent.mkdir(parents=True,exist_ok=True)
    state={"next_tile":0}
    if CHECKPOINT.exists() and not a.reset:state=json.loads(CHECKPOINT.read_text())
    all_tiles=list(tiles())
    for idx in range(state["next_tile"],len(all_tiles)):
        region,w,s,e,n=all_tiles[idx]
        for attempt in range(a.retry):
            try:
                features=atlas.usgs_tile(s,w,n,e)
                added=atlas.merge(DEST,features,lambda f:str(f["properties"]["site"]))
                state["next_tile"]=idx+1
                CHECKPOINT.write_text(json.dumps(state,indent=2)+"\n")
                print(f"{idx+1}/{len(all_tiles)} {region}: found {len(features)}, added {added}",flush=True)
                break
            except Exception as exc:
                if attempt==a.retry-1:
                    print(f"Stopped at tile {idx}: {exc}. Rerun to resume.",file=sys.stderr)
                    raise SystemExit(1)
                wait=min(90,3*(2**attempt))
                print(f"Retry tile {idx} in {wait}s: {exc}",flush=True)
                time.sleep(wait)
        time.sleep(a.delay)
    print(f"Complete: {len(atlas.read_collection(DEST)['features'])} unique USGS stream stations in {DEST}")
    print("Next: python3 Watershed.py --offline")

if __name__=="__main__":main()
