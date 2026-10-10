#!/usr/bin/env python3
"""Incremental, bandwidth-bounded atlas discovery. Run from repository root.

One 0.20-degree tile per invocation; requests run in GitHub Actions, not visitors'
browsers. Existing records are preserved. No state-sized OSM downloads.
"""
import argparse
import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("data")
STATE = ROOT / "expansion_progress.json"
LAUNCHES = ROOT / "putins_expansion.geojson"
RIVERS = ROOT / "river_expansion.geojson"
GAUGES = ROOT / "gauges_expansion.geojson"
# Southern Lake Michigan atlas bounds; advance west-to-east, south-to-north.
WEST, SOUTH, EAST, NORTH, STEP = -88.7, 40.9, -85.4, 43.2, 0.2
NX = math.ceil((EAST-WEST)/STEP)
NY = math.ceil((NORTH-SOUTH)/STEP)
MAX_BYTES = 1_500_000
USER_AGENT = "southern-lake-michigan-flow-atlas/1.0 (incremental public-data discovery)"

def request(url, body=None):
    req = urllib.request.Request(url, data=body, headers={"User-Agent":USER_AGENT, "Accept-Encoding":"identity"})
    with urllib.request.urlopen(req, timeout=55) as response:
        size = response.headers.get("Content-Length")
        if size and int(size)>MAX_BYTES:
            raise ValueError("Remote response exceeds 1.5 MB limit")
        data = response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:
            raise ValueError("Remote response exceeded 1.5 MB limit")
        return data.decode("utf-8")

def read_collection(path):
    if not path.exists() or not path.stat().st_size:
        return {"type":"FeatureCollection","features":[]}
    obj=json.loads(path.read_text())
    if obj.get("type")!="FeatureCollection":
        raise ValueError(f"Unexpected GeoJSON in {path}")
    return obj

def merge(path, new, key):
    obj=read_collection(path)
    known={key(f) for f in obj["features"]}
    added=0
    for f in new:
        ident=key(f)
        if ident not in known:
            obj["features"].append(f)
            known.add(ident)
            added+=1
    if added:
        path.write_text(json.dumps(obj,separators=(",",":"))+"\n")
    return added

def osm_tile(s,w,n,e,layer='both'):
    query=f"""[out:json][timeout:35];(
node["leisure"="slipway"]({s},{w},{n},{e});
way["leisure"="slipway"]({s},{w},{n},{e});
node["waterway"="access_point"]({s},{w},{n},{e});
way["waterway"="access_point"]({s},{w},{n},{e});
node["canoe"="yes"]({s},{w},{n},{e});
way["canoe"="yes"]({s},{w},{n},{e});
way["waterway"~"^(river|stream|canal)$"]({s},{w},{n},{e});
);out center geom;"""
    if layer=='launches':
        query=query.replace(f'way["waterway"~"^(river|stream|canal)$"]({s},{w},{n},{e});','')
    elif layer=='rivers':
        query=f'[out:json][timeout:35];(way["waterway"~"^(river|stream|canal)$"]({s},{w},{n},{e}););out center geom;'
    raw=request("https://overpass-api.de/api/interpreter",urllib.parse.urlencode({"data":query}).encode())
    return json.loads(raw).get("elements",[])

def extract_osm(elements):
    launches,rivers=[],[]
    for el in elements:
        tags=el.get("tags",{})
        typ=el.get("type")
        ident=f"osm-{typ}-{el.get('id')}"
        if tags.get("waterway") in ("river","stream","canal") and typ=="way":
            coords=[[p["lon"],p["lat"]] for p in el.get("geometry",[]) if "lon" in p and "lat" in p]
            if len(coords)>1:
                rivers.append({"type":"Feature","geometry":{"type":"LineString","coordinates":coords},
                  "properties":{"id":ident,"river_name":tags.get("name") or "Unnamed waterway","source":"OpenStreetMap","verification":"unverified"}})
        if tags.get("leisure")=="slipway" or tags.get("waterway")=="access_point" or tags.get("canoe")=="yes":
            lon=el.get("lon",el.get("center",{}).get("lon"))
            lat=el.get("lat",el.get("center",{}).get("lat"))
            if lon is None or lat is None or tags.get("access") in ("no","private"):
                continue
            launches.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},
              "properties":{"id":ident,"name":tags.get("name") or ident,"source":"OpenStreetMap",
                "source_url":f"https://www.openstreetmap.org/{typ}/{el['id']}",
                "access":tags.get("access","unknown"),"canoe":tags.get("canoe"),
                "kayak":tags.get("kayak"),"verification":"candidate_review"}})
    return launches,rivers

def usgs_tile(s,w,n,e):
    params=urllib.parse.urlencode({"format":"rdb","bBox":f"{w},{s},{e},{n}","siteType":"ST","siteStatus":"active"})
    raw=request("https://waterservices.usgs.gov/nwis/site/?"+params)
    lines=[line for line in raw.splitlines() if line and not line.startswith("#")]
    if len(lines)<3:return []
    columns=lines[0].split("\t")
    result=[]
    for line in lines[2:]:
        values=line.split("\t")
        if len(values)!=len(columns):continue
        row=dict(zip(columns,values))
        try:
            lat,lon=float(row["dec_lat_va"]),float(row["dec_long_va"])
        except (KeyError,ValueError):continue
        site=row.get("site_no")
        if not site:continue
        result.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},
          "properties":{"site":site,"name":row.get("station_nm",site),"stage":None,
            "stage_time":None,"discharge":None,"verification":"station_discovery_only",
            "source":"USGS NWIS site inventory"}})
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--max-tiles",type=int,default=1)
    args=parser.parse_args()
    if not 1<=args.max_tiles<=2:parser.error("At most two tiles per run")
    ROOT.mkdir(exist_ok=True)
    state=json.loads(STATE.read_text()) if STATE.exists() else {"next_tile":0,"failed":[]}
    for _ in range(args.max_tiles):
        index=state["next_tile"]
        if index>=NX*NY:
            print("All atlas tiles visited; no more downloads.")
            break
        ix,iy=index%NX,index//NX
        w=round(WEST+ix*STEP,5);s=round(SOUTH+iy*STEP,5)
        e=min(round(w+STEP,5),EAST);n=min(round(s+STEP,5),NORTH)
        print(f"Tile {index+1}/{NX*NY}: {s},{w},{n},{e}",flush=True)
        # Failure never discards previously discovered records.
        try:
            osm=osm_tile(s,w,n,e)
            launches,rivers=extract_osm(osm)
            gauges=usgs_tile(s,w,n,e)
        except (OSError,ValueError,json.JSONDecodeError) as exc:
            print(f"Tile not advanced after error: {exc}",flush=True)
            raise
        counts={
            "launches":merge(LAUNCHES,launches,lambda f:f["properties"]["id"]),
            "rivers":merge(RIVERS,rivers,lambda f:f["properties"]["id"]),
            "gauges":merge(GAUGES,gauges,lambda f:f["properties"]["site"]),
        }
        state["next_tile"]=index+1
        state["last_tile"]={"index":index,"bounds":[w,s,e,n],"added":counts}
        STATE.write_text(json.dumps(state,indent=2)+"\n")
        print("Added",counts,flush=True)
        if args.max_tiles>1:time.sleep(5)

if __name__=="__main__":main()
