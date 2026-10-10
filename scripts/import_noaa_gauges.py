#!/usr/bin/env python3
"""Build a national NOAA NWPS gauge inventory with observed stage and thresholds.

Run on demand: python scripts/import_noaa_gauges.py
Never treat a historical low-water event as a regulatory low-water threshold.
"""
import concurrent.futures
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://api.water.noaa.gov/nwps/v1"
OUT = Path("data/noaa_gauges.geojson")
WORKERS = int(os.getenv("NOAA_WORKERS", "6"))
USER_AGENT = "SouthernLakeMichiganFlowAtlas/1.0 (public NOAA data)"
def get(path):
    url = BASE + path
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=70) as response:
                return json.load(response)
        except Exception:
            if attempt == 3: raise
            time.sleep(2 ** attempt)
def first(obj, *names):
    if not isinstance(obj, dict): return None
    for name in names:
        val = obj.get(name)
        if val is not None and val != "": return val
    return None
def number(value):
    if isinstance(value, dict): value = first(value, "value", "stage", "height")
    try: return float(value)
    except (ValueError, TypeError): return None
def coordinates(g):
    loc = first(g, "location", "geometry") or {}
    if not isinstance(loc, dict): loc = {}
    c = first(loc, "coordinates")
    if isinstance(c, list) and len(c) >= 2: return [number(c[0]), number(c[1])]
    lon = first(g, "longitude", "lon", "lng")
    lat = first(g, "latitude", "lat")
    if lon is None: lon = first(loc, "longitude", "lon", "lng")
    if lat is None: lat = first(loc, "latitude", "lat")
    return [number(lon), number(lat)]
def threshold(g, *keys):
    flood = first(g, "flood", "floodCategories") or {}
    categories = first(flood, "categories", "stage") or flood
    for obj in (g, flood, categories):
        val = first(obj, *keys)
        result = number(val)
        if result is not None: return result
    return None
def observation(stageflow):
    obs = first(stageflow, "observed") or {}
    series = first(obs, "data", "values", "points") or []
    if isinstance(series, dict): series = first(series, "data", "values") or []
    if not isinstance(series, list): series = []
    entries = [x for x in series if isinstance(x, dict) and number(first(x, "primary", "value", "stage")) is not None]
    if not entries: return None, None
    entries.sort(key=lambda x: str(first(x, "validTime", "time", "timestamp", "dateTime") or ""))
    item = entries[-1]
    return number(first(item, "primary", "value", "stage")), first(item, "validTime", "time", "timestamp", "dateTime")
def fetch_one(item):
    lid = first(item, "lid", "identifier", "id")
    if not lid: return None
    key = urllib.parse.quote(str(lid), safe="")
    detail = get("/gauges/" + key)
    if not isinstance(detail, dict): detail = item
    combined = dict(item, **detail)
    coords = coordinates(combined)
    if any(x is None for x in coords) or not (-180 <= coords[0] <= 180 and -90 <= coords[1] <= 90): return None
    try: stage, stage_time = observation(get("/gauges/" + key + "/stageflow"))
    except Exception: stage, stage_time = None, None
    low = first(combined, "lowWater", "lowWaterThreshold", "lowThreshold")
    low_stage = number(low)
    if low_stage is None: low_stage = threshold(combined, "lowWaterStage", "lowStage")
    flood = threshold(combined, "minor", "minorFloodStage", "floodStage", "flood")
    props = {
        "noaa_lid": str(lid), "site": str(first(combined, "usgsId") or lid),
        "name": first(combined, "name", "description") or str(lid),
        "state": first(first(combined, "state") or {}, "abbreviation") if isinstance(first(combined, "state"), dict) else first(combined, "state"),
        "source": "NOAA NWPS", "stage": stage, "stage_time": stage_time,
        "flood_stage_ft": flood, "low_water_stage_ft": low_stage,
        "action_stage_ft": threshold(combined, "action", "actionStage"),
        "moderate_flood_stage_ft": threshold(combined, "moderate", "moderateFloodStage"),
        "major_flood_stage_ft": threshold(combined, "major", "majorFloodStage"),
        "reach_id": first(combined, "reachId")
    }
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": coords}, "properties": props}
def main():
    listing = get("/gauges")
    items = listing if isinstance(listing, list) else first(listing, "gauges", "data", "items")
    if not isinstance(items, list) or not items: raise RuntimeError("NOAA gauge list has unexpected shape; refusing publication")
    print("NOAA gauges listed:", len(items), flush=True)
    features = []
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_one, item): first(item, "lid", "identifier", "id") for item in items}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                feature = future.result()
                if feature: features.append(feature)
            except Exception as exc: errors.append((futures[future], str(exc)))
            if i % 500 == 0: print("Processed", i, "of", len(items), "errors", len(errors), flush=True)
    if errors:
        print("First errors:", errors[:15], flush=True)
        raise RuntimeError(f"{len(errors)} NOAA gauge requests failed; refusing incomplete publication")
    if not features: raise RuntimeError("No geolocated NOAA gauges; refusing publication")
    features.sort(key=lambda f: f["properties"]["noaa_lid"])
    output = {"type": "FeatureCollection", "metadata": {
        "source": "NOAA National Water Prediction Service", "updated_utc": datetime.now(timezone.utc).isoformat(),
        "listed": len(items), "mapped": len(features),
        "note": "Low-water thresholds are not available at all stations; null means undefined."
    }, "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, separators=(",", ":")))
    tmp.replace(OUT)
    print("Published", len(features), "NOAA gauges to", OUT, flush=True)
if __name__ == "__main__": main()
