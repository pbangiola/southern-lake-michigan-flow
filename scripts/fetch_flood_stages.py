"""Fetch NOAA NWPS flood-stage thresholds matched by exact USGS site ID.

Run: python -u scripts/fetch_flood_stages.py
Requires data/gauges.geojson from fetch_gauges.py.
Writes data/flood_stages.json and data/flood_stage_review.json.
Only accepts explicit stage units (feet) and exact USGS ID matches.
"""
import json
import time
from pathlib import Path

import requests

API = "https://api.water.noaa.gov/nwps/v1/gauges"
BBOX = {"bbox.xmin": -88.7, "bbox.ymin": 40.9, "bbox.xmax": -85.4, "bbox.ymax": 43.2, "srid": "EPSG_4326"}
GAUGES = Path("data/gauges.geojson")
OUT = Path("data/flood_stages.json")
REVIEW = Path("data/flood_stage_review.json")


def get_json(session, url, params=None):
    for attempt in range(1, 4):
        try:
            response = session.get(url, params=params, timeout=(12, 35))
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, (dict, list)):
                raise ValueError("Unexpected JSON response")
            return data
        except (requests.RequestException, ValueError) as exc:
            print("  Attempt {}/3 failed: {}".format(attempt, exc), flush=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def as_number(value):
    if isinstance(value, dict):
        value = value.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def stage_categories(gauge):
    # NOAA publishes separate stage and flow flood-category sets.
    flood = gauge.get("flood") or {}
    if not isinstance(flood, dict):
        return None
    categories = flood.get("categories") or {}
    if not isinstance(categories, dict):
        return None
    stage = categories.get("stage") or {}
    if not isinstance(stage, dict):
        return None
    units = str(stage.get("units") or stage.get("unit") or "ft").lower()
    if units not in ("ft", "feet"):
        return None
    values = {}
    for field, names in {
        "action_stage_ft": ("action",),
        "flood_stage_ft": ("minor", "flood"),
        "moderate_stage_ft": ("moderate",),
        "major_stage_ft": ("major",),
    }.items():
        for name in names:
            number = as_number(stage.get(name))
            if number is not None:
                values[field] = number
                break
    return values or None


def main():
    if not GAUGES.exists():
        raise RuntimeError("Run python -u scripts/fetch_gauges.py first")
    features = json.loads(GAUGES.read_text())["features"]
    usgs_ids = {str(f["properties"]["site"]).strip() for f in features}
    print("Loaded {} USGS gauge IDs".format(len(usgs_ids)), flush=True)
    print("Requesting NOAA gauges within regional bounding box (not nationwide)...", flush=True)
    with requests.Session() as session:
        directory = get_json(session, API, params=BBOX)
        if isinstance(directory, list):
            entries = directory
        elif isinstance(directory, dict):
            entries = directory.get("gauges", directory.get("features", []))
        else:
            entries = []
        if not isinstance(entries, list):
            raise RuntimeError("Unexpected NOAA gauge directory structure")
        print("NOAA directory returned {} entries".format(len(entries)), flush=True)
        matched = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            usgs_id = str(item.get("usgsId") or "").strip()
            identifier = item.get("lid") or item.get("identifier")
            if usgs_id in usgs_ids and identifier:
                matched[usgs_id] = identifier
        print("Matched {} gauges by exact USGS ID".format(len(matched)), flush=True)
        if not matched:
            print("Sample NOAA record keys: {}".format(list(entries[0]) if entries else []), flush=True)
            print("No exact matches. STOP: inspect response schema before proceeding.", flush=True)
            return
        existing = json.loads(OUT.read_text()) if OUT.exists() else {}
        review = {}
        for index, (usgs_id, lid) in enumerate(sorted(matched.items()), 1):
            print("[{}/{}] NOAA {} / USGS {}".format(index, len(matched), lid, usgs_id), flush=True)
            try:
                record = get_json(session, API + "/" + str(lid))
                stages = stage_categories(record)
                if stages:
                    existing[usgs_id] = dict(stages, source=API + "/" + str(lid),
                                             noaa_lid=lid)
                    print("  Thresholds: {}".format(stages), flush=True)
                else:
                    review[usgs_id] = {"lid": lid, "reason": "No recognized stage thresholds",
                                       "flood": record.get("flood")}
                    print("  No usable stage thresholds", flush=True)
            except (requests.RequestException, ValueError) as exc:
                review[usgs_id] = {"lid": lid, "reason": str(exc)}
            # Save after every station to support interruption and resumption.
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(existing, indent=2, sort_keys=True))
            REVIEW.write_text(json.dumps(review, indent=2, sort_keys=True))
        print("Done. {} threshold records; {} need review.".format(len(existing), len(review)), flush=True)
        print("Run python -u scripts/fetch_gauges.py to apply thresholds.", flush=True)


if __name__ == "__main__":
    main()
