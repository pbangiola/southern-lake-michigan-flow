"""Match NOAA NWPS flood-stage thresholds to USGS gauges.

Run after fetch_gauges.py: python -u scripts/fetch_flood_stages.py
Queries a small regional NOAA directory, then fetches detail records sequentially.
Caches every successful detail response so reruns resume without re-downloading.
Only exact USGS site ID matches are accepted; no coordinate guessing.
"""
import json
import time
from pathlib import Path

import requests

API = "https://api.water.noaa.gov/nwps/v1/gauges"
BBOX = {"bbox.xmin": -88.7, "bbox.ymin": 40.9, "bbox.xmax": -85.4,
        "bbox.ymax": 43.2, "srid": "EPSG_4326"}
GAUGES = Path("data/gauges.geojson")
OUT = Path("data/flood_stages.json")
REVIEW = Path("data/flood_stage_review.json")
CACHE = Path("data/cache/noaa")
MISSING = {-9999, -999, -99999}


def fetch(session, url, params=None):
    for attempt in range(1, 4):
        start = time.monotonic()
        try:
            response = session.get(url, params=params, timeout=(10, 20))
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, (dict, list)):
                raise ValueError("Unexpected JSON response")
            return result
        except (requests.RequestException, ValueError) as exc:
            print("  Request {}/3 failed after {:.1f}s: {}".format(
                attempt, time.monotonic() - start, exc), flush=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def number(value):
    if isinstance(value, dict):
        value = value.get("stage")
    try:
        result = float(value)
        return None if result in MISSING else result
    except (TypeError, ValueError):
        return None


def extract_stages(gauge):
    flood = gauge.get("flood") or {}
    if not isinstance(flood, dict):
        return {}
    unit = str(flood.get("stageUnits") or "").lower()
    if unit not in ("ft", "feet"):
        return {}
    categories = flood.get("categories") or {}
    if not isinstance(categories, dict):
        return {}
    result = {}
    for key, field in (("action", "action_stage_ft"),
                       ("minor", "flood_stage_ft"),
                       ("moderate", "moderate_stage_ft"),
                       ("major", "major_stage_ft")):
        val = number(categories.get(key))
        if val is not None:
            result[field] = val
    return result


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, indent=2, sort_keys=True))
    temp.replace(path)


def main():
    if not GAUGES.exists():
        raise RuntimeError("Run python -u scripts/fetch_gauges.py first")
    usgs_ids = {str(f["properties"]["site"]).strip()
                for f in json.loads(GAUGES.read_text())["features"]}
    print("Loaded {} USGS station IDs".format(len(usgs_ids)), flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    review = json.loads(REVIEW.read_text()) if REVIEW.exists() else {}
    with requests.Session() as session:
        print("Requesting regional NOAA gauge directory...", flush=True)
        directory = fetch(session, API, BBOX)
        entries = directory if isinstance(directory, list) else directory.get("gauges", [])
        if not isinstance(entries, list):
            raise RuntimeError("Unexpected NOAA directory structure")
        lids = sorted({str(g["lid"]) for g in entries if isinstance(g, dict) and g.get("lid")})
        print("Found {} NOAA locations; fetching detail records one at a time.".format(len(lids)), flush=True)
        matched = 0
        failed = 0
        for index, lid in enumerate(lids, 1):
            path = CACHE / (lid + ".json")
            print("[{}/{}] {}: ".format(index, len(lids), lid), end="", flush=True)
            try:
                if path.exists():
                    detail = json.loads(path.read_text())
                    print("cached", end="; ", flush=True)
                else:
                    detail = fetch(session, API + "/" + lid)
                    save_json(path, detail)
                    print("downloaded", end="; ", flush=True)
                usgs_id = str(detail.get("usgsId") or "").strip()
                if not usgs_id or usgs_id not in usgs_ids:
                    print("no exact USGS match", flush=True)
                    continue
                matched += 1
                stages = extract_stages(detail)
                if stages and "flood_stage_ft" in stages:
                    existing[usgs_id] = dict(stages, noaa_lid=lid, source=API + "/" + lid)
                    review.pop(usgs_id, None)
                    print("matched USGS {}; thresholds {}".format(usgs_id, stages), flush=True)
                else:
                    review[usgs_id] = {"noaa_lid": lid, "reason": "Missing usable minor flood stage",
                                       "stage_units": (detail.get("flood") or {}).get("stageUnits")}
                    print("matched USGS {}, but no usable flood stage".format(usgs_id), flush=True)
            except (requests.RequestException, ValueError, KeyError) as exc:
                failed += 1
                print("FAILED: {}".format(exc), flush=True)
            save_json(OUT, existing)
            save_json(REVIEW, review)
        print("Finished: {} exact USGS matches; {} configured flood stages; {} request errors.".format(
            matched, sum(1 for site in usgs_ids if site in existing), failed), flush=True)
        print("Run python -u scripts/fetch_gauges.py to refresh map classifications.", flush=True)


if __name__ == "__main__":
    main()
