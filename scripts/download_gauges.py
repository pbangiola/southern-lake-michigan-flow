#!/usr/bin/env python3
"""Resumable nationwide USGS stream-station inventory download.

Run: python3 scripts/download_gauges.py
Downloads USGS agency stream stations across the US and territories to
local/gauges_us.geojson. Large source inventory stays off GitHub.
"""
import argparse
import urllib.error
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import expand_atlas as atlas

DEST=Path("local/gauges_us.geojson")
CHECKPOINT=Path("local/gauge_download_us_progress.json")
METRICS=Path("local/gauge_api_metrics.json")
# Region envelopes include contiguous US, Alaska/Aleutians, Hawaii and US Pacific/
# Caribbean territories. Only agency_code=USGS, site_type_code=ST are retained.
REGIONS=[
    ("continental_alaska", -180, 15, -60, 75),
    ("pacific_territories", 120, -20, 180, 30),
]
STEP=5
# Conservative envelopes: only exclude tiles with no overlap with any US region.
# Deliberately retain border/coastal tiles. This is not a precise land mask.
US_ENVELOPES=[
    (-125,24,-66,50),      # contiguous US
    (-180,50,-129,72),     # Alaska and Aleutians
    (-179,18,-154,29),     # Hawaii and northwestern Hawaiian Islands
    (-68,17,-64,19),      # Puerto Rico / US Virgin Islands
    (143,12,147,22),     # Guam / Northern Mariana Islands
    (-172,-15,-168,-10), # American Samoa
    (165,18,168,21),     # Wake Island
    (-163,5,-161,7),     # Palmyra / Kingman
    (-177,27,-175,29),   # Midway Atoll
    (-170,-1,-168,1),    # Jarvis Island
    (-177,-1,-175,1),    # Howland / Baker Islands
    (-131,-1,-129,1),    # Johnston Atoll (retained conservatively)
]

def intersects(a,b):
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]

def skip_tile_ids(all_tiles):
    """1-based IDs matching the original 408-tile traversal/checkpoint."""
    return {i+1 for i,(_,w,s,e,n) in enumerate(all_tiles)
            if not any(intersects((w,s,e,n),bounds) for bounds in US_ENVELOPES)}

def tiles():
    for region,w,s,e,n in REGIONS:
        lat=s
        while lat<n:
            lon=w
            while lon<e:
                yield region,round(lon,4),round(lat,4),round(min(e,lon+STEP),4),round(min(n,lat+STEP),4)
                lon+=STEP
            lat+=STEP


class QuotaMonitor:
    def __init__(self,delay):
        self.delay=delay
        self.stats=json.loads(METRICS.read_text()) if METRICS.exists() else {"requests":0,"successes":0,"http_429":0,"errors":0}
        self.next_at=0.0

    def before(self):
        remaining=self.next_at-time.time()
        if remaining>0:
            if remaining>=5:print("Quota pacing: waiting %.0f seconds"%remaining,flush=True)
            time.sleep(remaining)

    def after(self,status,headers):
        stats=self.stats
        stats["requests"]+=1
        if 200<=status<300:stats["successes"]+=1
        elif status==429:stats["http_429"]+=1
        else:stats["errors"]+=1
        for header,key in (("X-RateLimit-Limit","limit"),("X-RateLimit-Remaining","remaining"),("X-RateLimit-Reset","reset")):
            value=headers.get(header) if headers else None
            if value is not None:stats[key]=value
        self.next_at=time.time()+self.delay
        try:
            remaining=int(stats.get("remaining"))
            limit=int(stats.get("limit"))
            if limit>0 and remaining/limit<=0.02:
                self.next_at=max(self.next_at,time.time()+60)
            elif limit>0 and remaining/limit<=0.10:
                self.next_at=max(self.next_at,time.time()+10)
        except (TypeError,ValueError):pass
        if status==429:
            retry=headers.get("Retry-After") if headers else None
            try:wait=max(60,float(retry))
            except (TypeError,ValueError):wait=60
            self.next_at=max(self.next_at,time.time()+wait)
        METRICS.write_text(json.dumps(stats,indent=2)+"\\n")
        if stats["requests"]%25==0 or status==429:
            print("USGS requests=%s, 429s=%s, remaining=%s, limit=%s"%(
                stats["requests"],stats["http_429"],stats.get("remaining"),stats.get("limit")),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--delay",type=float,default=2.0)
    p.add_argument("--retry",type=int,default=5)
    p.add_argument("--reset",action="store_true",help="Restart tile traversal, retaining downloaded records")
    a=p.parse_args()
    if a.delay<0 or a.retry<1:p.error("Invalid delay/retry")
    DEST.parent.mkdir(parents=True,exist_ok=True)
    state={"next_tile":0}
    if CHECKPOINT.exists() and not a.reset:state=json.loads(CHECKPOINT.read_text())
    monitor=QuotaMonitor(a.delay)
    atlas.USGS_REQUEST_BEFORE=monitor.before
    atlas.USGS_REQUEST_AFTER=monitor.after
    all_tiles=list(tiles())
    skipped=skip_tile_ids(all_tiles)
    print(f"Skipping {len(skipped)} of {len(all_tiles)} tiles outside conservative US region envelopes",flush=True)
    for idx in range(state["next_tile"],len(all_tiles)):
        region,w,s,e,n=all_tiles[idx]
        if idx+1 in skipped:
            state["next_tile"]=idx+1
            CHECKPOINT.write_text(json.dumps(state,indent=2)+"\n")
            print(f"{idx+1}/{len(all_tiles)} {region}: SKIP non-US tile",flush=True)
            continue
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
                if isinstance(exc,urllib.error.HTTPError) and exc.code==429:
                    retry_after=exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        wait=max(60,float(retry_after)) if retry_after else min(600,60*2**attempt)
                    except ValueError:
                        wait=min(600,60*2**attempt)
                else:
                    wait=min(90,3*(2**attempt))
                print(f"Retry tile {idx} in {wait}s: {exc}",flush=True)
                time.sleep(wait)
        # Per-request pacing is handled by the monitor, including paginated calls.
    print(f"Complete: {len(atlas.read_collection(DEST)['features'])} unique USGS stream stations in {DEST}")
    print("Next: python3 Watershed.py --offline")

if __name__=="__main__":main()
