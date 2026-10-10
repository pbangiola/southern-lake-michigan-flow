#!/usr/bin/env python3
"""Cached, rate-limited NOAA NWPS flood-stage import for Great Lakes states.

Examples:
  python3 scripts/import_noaa_flood.py --states IL --limit 10
  python3 scripts/import_noaa_flood.py --states WI IN MI --limit 10
  python3 scripts/import_noaa_flood.py --states IL WI IN MI

Only NOAA is queried. Existing Illinois cache in local/noaa_il is reused.
Output is a combined file, data/flood_stages_great_lakes.json.
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
ROOT = Path(__file__).resolve().parent.parent
BOUNDS = {
    "IL": (-91.6, 36.9, -87.0, 42.6),
    "WI": (-93.0, 42.4, -86.2, 47.4),
    "IN": (-88.2, 37.7, -84.6, 41.9),
    "MI": (-90.5, 41.6, -82.1, 48.4),
}
AGENT = "SouthernLakeMichiganAtlas/1.0 (NOAA NWPS flood-stage reference import)"

def fetch(url, delay):
    for attempt in range(6):
        time.sleep(delay)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 5:
                raise
            try:
                wait = min(300, max(delay, float(exc.headers.get("Retry-After", ""))))
            except ValueError:
                wait = min(300, 2 ** (attempt + 2))
            print("NOAA HTTP", exc.code, "backoff", wait, "seconds", flush=True)
            time.sleep(wait)
        except (TimeoutError, urllib.error.URLError):
            if attempt == 5:
                raise
            time.sleep(min(120, 2 ** (attempt + 2)))

def items(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("gauges", "items", "features", "data"):
            if isinstance(obj.get(key), list):
                return obj[key]
    raise ValueError("Unrecognized NOAA gauge-list response")

def lid(g):
    return str(g.get("lid") or g.get("identifier") or g.get("id") or "").strip().upper()

def state(g):
    value = g.get("state") or {}
    if isinstance(value, dict):
        value = value.get("abbreviation") or value.get("code") or ""
    return str(value).strip().upper()

def number(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) and n >= 0 and n != -9999 else None
    except (ValueError, TypeError):
        return None

def read_or_fetch(path, url, delay):
    if path.exists():
        return json.loads(path.read_text())
    data = fetch(url, delay)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data

def extract(detail, code, region):
    if not isinstance(detail, dict):
        return None
    usgs = str(detail.get("usgsId") or "").replace("USGS-", "").strip()
    flood = detail.get("flood") or {}
    categories = flood.get("categories") if isinstance(flood, dict) else None
    if not usgs or not isinstance(categories, dict) or str(flood.get("stageUnits") or "").lower() not in ("ft", "feet", "foot"):
        return None
    levels = {}
    for name in ("action", "minor", "moderate", "major"):
        category = categories.get(name)
        levels[name] = number(category.get("stage")) if isinstance(category, dict) else None
    if levels["minor"] is None:
        return None
    return {"usgs_id": usgs, "noaa_id": code, "state": region,
            "flood_stage_ft": levels["minor"], "action_stage_ft": levels["action"],
            "moderate_flood_stage_ft": levels["moderate"], "major_flood_stage_ft": levels["major"],
            "source": "NOAA NWPS", "source_url": BASE + "/" + code}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", nargs="+", choices=sorted(BOUNDS), default=["IL", "WI", "IN", "MI"])
    parser.add_argument("--limit", type=int, default=0, help="Maximum NOAA gauge details per state (0 = all)")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds before each HTTP request")
    args = parser.parse_args()
    if args.limit < 0 or args.delay < 1:
        parser.error("--limit must be >= 0 and --delay >= 1")
    stations = {}
    stats = {}
    for region in dict.fromkeys(args.states):
        cache = ROOT / "local" / ("noaa_" + region.lower())
        cache.mkdir(parents=True, exist_ok=True)
        west, south, east, north = BOUNDS[region]
        params = {"bbox.xmin": west, "bbox.ymin": south, "bbox.xmax": east,
                  "bbox.ymax": north, "srid": "EPSG_4326"}
        listing = read_or_fetch(cache / "list.json", BASE + "?" + urllib.parse.urlencode(params), args.delay)
        gauges = sorted((g for g in items(listing) if isinstance(g, dict) and state(g) == region and lid(g)), key=lid)
        if not gauges:
            raise SystemExit("No NOAA gauges identified for " + region + "; inspect " + str(cache / "list.json"))
        selected = gauges[:args.limit] if args.limit else gauges
        failures = 0
        for index, gauge in enumerate(selected, 1):
            code = lid(gauge)
            try:
                read_or_fetch(cache / (code + ".json"), BASE + "/" + urllib.parse.quote(code), args.delay)
            except Exception as exc:
                failures += 1
                print(region, code, "request failed:", repr(exc), flush=True)
            if index % 25 == 0:
                print(region, "processed", index, "of", len(selected), flush=True)
        resolved = 0
        unresolved = 0
        for gauge in gauges:
            code = lid(gauge)
            path = cache / (code + ".json")
            if not path.exists():
                continue
            try:
                record = extract(json.loads(path.read_text()), code, region)
            except (ValueError, TypeError):
                record = None
            if record:
                resolved += 1
                # Keep first record for a USGS ID; report collisions separately.
                stations.setdefault(record["usgs_id"], record)
            else:
                unresolved += 1
        stats[region] = {"noaa_gauges": len(gauges), "selected": len(selected),
                         "cached_details": sum((cache / (lid(g) + ".json")).exists() for g in gauges),
                         "resolved": resolved, "unresolved_cached": unresolved, "failed_requests": failures}
        print(region, stats[region], flush=True)
    output = ROOT / "data" / "flood_stages_great_lakes.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": "NOAA NWPS", "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "states": stats, "stations": stations}
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print("Wrote", len(stations), "unique USGS flood-stage records to", output, flush=True)
    print("Uncached gauges were not classified. Validate stage datums before coloring the map.", flush=True)

if __name__ == "__main__":
    main()
