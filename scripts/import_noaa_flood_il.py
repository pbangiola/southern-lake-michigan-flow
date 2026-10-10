#!/usr/bin/env python3
"""Conservative NOAA NWPS flood-stage importer for Illinois; no USGS requests.

Pilot: python3 scripts/import_noaa_flood_il.py --limit 10
Full:  python3 scripts/import_noaa_flood_il.py
Resume: run the same command again. Raw cache/checkpoint remain in local/.
"""
import argparse
import datetime as dt
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.water.noaa.gov/nwps/v1/gauges"
CACHE = Path("local/noaa_il")
OUTPUT = Path("data/flood_stages_il.json")
# Bounding box covers Illinois; state metadata filters adjacent-state gauges.
BBOX = (-91.6, 36.9, -87.0, 42.6)
AGENT = "SouthernLakeMichiganAtlas/1.0 (NOAA flood-stage reference import)"

def fetch(url, delay):
    for attempt in range(6):
        time.sleep(delay)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENT}), timeout=45) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 5:
                raise
            wait = exc.headers.get("Retry-After", "")
            try:
                seconds = min(300, max(delay, float(wait)))
            except ValueError:
                seconds = min(300, 2 ** (attempt + 2))
            print("NOAA HTTP", exc.code, "waiting", seconds, "seconds", flush=True)
            time.sleep(seconds)
        except (TimeoutError, urllib.error.URLError):
            if attempt == 5:
                raise
            time.sleep(min(120, 2 ** (attempt + 2)))

def items(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("gauges", "items", "features", "data"):
            value = obj.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Unexpected NOAA list response structure; inspect local/noaa_il/list.json")

def lid(g):
    return str(g.get("lid") or g.get("identifier") or g.get("id") or "").strip().upper()

def state(g):
    value = g.get("state") or {}
    if isinstance(value, dict):
        value = value.get("abbreviation") or value.get("code") or ""
    return str(value).upper()

def number(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Only request N gauges; 10 for pilot")
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()
    if args.delay < 1 or args.limit < 0:
        parser.error("delay must be >=1 second and limit >=0")
    CACHE.mkdir(parents=True, exist_ok=True)
    list_path = CACHE / "list.json"
    if list_path.exists():
        listing = json.loads(list_path.read_text())
    else:
        params = {
            "bbox.xmin": BBOX[0], "bbox.ymin": BBOX[1],
            "bbox.xmax": BBOX[2], "bbox.ymax": BBOX[3], "srid": "EPSG_4326",
        }
        listing = fetch(BASE + "?" + urllib.parse.urlencode(params), args.delay)
        list_path.write_text(json.dumps(listing))
    all_gauges = items(listing)
    illinois = sorted((g for g in all_gauges if isinstance(g, dict) and state(g) == "IL" and lid(g)), key=lid)
    if not illinois:
        raise SystemExit("No Illinois NOAA gauges found; inspect cached list schema. No data overwritten.")
    print("NOAA list:", len(all_gauges), "records;", len(illinois), "Illinois gauges", flush=True)
    requested = illinois[:args.limit] if args.limit else illinois
    for index, gauge in enumerate(requested, 1):
        code = lid(gauge)
        path = CACHE / (code + ".json")
        if path.exists():
            continue
        try:
            detail = fetch(BASE + "/" + urllib.parse.quote(code), args.delay)
            path.write_text(json.dumps(detail))
        except Exception as exc:
            print("Failed", code, repr(exc), "— progress retained", flush=True)
            continue
        if index % 10 == 0:
            print("Processed", index, "of", len(requested), flush=True)
    # Never use guessed field names or flow values as a flood-stage threshold.
    # The NOAA flood category metadata has a 'minor' stage threshold.
    records = {}
    unresolved = []
    for gauge in illinois:
        code = lid(gauge)
        path = CACHE / (code + ".json")
        if not path.exists():
            continue
        detail = json.loads(path.read_text())
        if not isinstance(detail, dict):
            unresolved.append(code)
            continue
        usgs = str(detail.get("usgsId") or "").removeprefix("USGS-").strip()
        flood = detail.get("flood") or {}
        categories = flood.get("categories") if isinstance(flood, dict) else None
        if not isinstance(categories, dict):
            unresolved.append(code)
            continue
        minor = categories.get("minor")
        # Stage thresholds must be explicitly identified as feet; avoid treating cfs as feet.
        if isinstance(minor, dict):
            unit = str(minor.get("unit") or minor.get("units") or "").lower()
            minor = minor.get("stage") if unit in ("ft", "feet", "foot") else None
        else:
            # Scalar NOAA flood categories use stage units, but only accept when
            # the metadata explicitly specifies stage rather than flow.
            unit = str(flood.get("unit") or flood.get("units") or flood.get("primary") or "").lower()
            if unit not in ("ft", "feet", "foot", "stage"):
                minor = None
        value = number(minor)
        if not usgs or value is None:
            unresolved.append(code)
            continue
        records[usgs] = {"usgs_id": usgs, "noaa_id": code, "flood_stage_ft": value,
                         "source": "NOAA NWPS", "source_url": BASE + "/" + code}
    result = {"source": "NOAA NWPS", "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "illinois_noaa_gauges": len(illinois), "details_cached": sum((CACHE / (lid(g)+".json")).exists() for g in illinois),
              "flood_stage_records": len(records), "unresolved_count": len(unresolved),
              "stations": records}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print("Wrote", len(records), "verified stage records to", OUTPUT, "; unresolved:", len(unresolved))
    if not records:
        print("No thresholds extracted. Inspect local/noaa_il/<LID>.json before adjusting the parser; do not invent thresholds.")

if __name__ == "__main__":
    main()
