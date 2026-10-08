"""Fetch trailing-year daily USGS stage statistics, without retaining raw observations.

Run after fetch_gauges.py: python -u scripts/fetch_stage_stats.py
Uses USGS OGC daily statistics: mean (00003), minimum (00002), maximum (00001).
Only compact per-station statistics are stored. Resumable and rate-limit aware.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

BASE = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/items"
GAUGES = Path("data/gauges.geojson")
OUTPUT = Path("data/stage_stats.json")
CACHE = Path("data/cache/stage_stats")
DELAY = 2.0
last_request = 0.0


class RateLimited(Exception):
    pass


def fetch(session, site, stat, start, end):
    global last_request
    url = BASE
    params = {"f": "json", "monitoring_location_id": "USGS-" + site,
              "parameter_code": "00065", "statistic_id": stat,
              "datetime": start + "/" + end, "limit": 10000}
    observations = {}
    seen = set()
    for _ in range(30):
        for attempt in range(5):
            time.sleep(max(0, DELAY - (time.monotonic() - last_request)))
            try:
                response = session.get(url, params=params, timeout=(15, 45))
                last_request = time.monotonic()
                if response.status_code == 429:
                    wait = response.headers.get("Retry-After")
                    try:
                        seconds = min(600, max(60, int(wait)))
                    except (TypeError, ValueError):
                        seconds = min(600, 60 * (attempt + 1))
                    print("    Rate limited; waiting {} seconds".format(seconds), flush=True)
                    time.sleep(seconds)
                    continue
                response.raise_for_status()
                data = response.json()
                break
            except (requests.RequestException, ValueError):
                if attempt == 4:
                    raise
                time.sleep(min(90, 10 * (attempt + 1)))
        else:
            raise RateLimited("USGS rate limit persisted; resume later")
        for feature in data.get("features", []):
            p = feature.get("properties") or {}
            if p.get("monitoring_location_id") != "USGS-" + site:
                continue
            if str(p.get("parameter_code")) != "00065" or str(p.get("statistic_id")) != stat:
                continue
            try:
                value = float(p["value"])
                day = str(p["time"])[:10]
            except (ValueError, TypeError, KeyError):
                continue
            if value > -9999 and start <= day <= end:
                observations[day] = value
        next_url = next((x.get("href") for x in data.get("links", [])
                        if x.get("rel") == "next"), None)
        if not next_url:
            return observations
        if next_url in seen or urlparse(next_url).netloc != "api.waterdata.usgs.gov":
            raise RuntimeError("Invalid pagination")
        seen.add(next_url)
        url, params = next_url, None
    raise RuntimeError("Too many pages")


def main():
    sites = sorted({str(f["properties"]["site"]) for f in
                    json.loads(GAUGES.read_text())["features"]})
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=364)
    first, last = start.isoformat(), end.isoformat()
    CACHE.mkdir(parents=True, exist_ok=True)
    records, failures = {}, {}
    with requests.Session() as session:
        for index, site in enumerate(sites, 1):
            path = CACHE / ("{}_{}_{}.json".format(site, first, last))
            print("[{}/{}] {}".format(index, len(sites), site), flush=True)
            try:
                if path.exists():
                    record = json.loads(path.read_text())
                else:
                    means = fetch(session, site, "00003", first, last)
                    lows = fetch(session, site, "00002", first, last)
                    highs = fetch(session, site, "00001", first, last)
                    coverage = len(means)
                    record = {
                        "mean_ft": round(sum(means.values()) / coverage, 3) if coverage else None,
                        "minimum_ft": min(lows.values()) if lows else None,
                        "maximum_ft": max(highs.values()) if highs else None,
                        "mean_coverage_days": coverage,
                        "minimum_coverage_days": len(lows),
                        "maximum_coverage_days": len(highs),
                        "coverage_fraction": round(coverage / 365, 3),
                        "complete_year": coverage >= 347,
                    }
                    path.write_text(json.dumps(record, indent=2))
                records[site] = record
            except RateLimited as exc:
                failures[site] = str(exc)
                print("Stopping on rate limit; rerun to resume.", flush=True)
                break
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                failures[site] = str(exc)
                print("Failed: {}".format(exc), flush=True)
            OUTPUT.write_text(json.dumps({
                "metadata": {"start_date": first, "end_date": last,
                             "calculated_at": datetime.now(timezone.utc).isoformat(),
                             "method": "USGS daily mean (00003), daily minimum (00002), daily maximum (00001); averages equally weighted by day",
                             "coverage_note": "complete_year means at least 347 of 365 daily means; no raw observations retained"},
                "stations": records, "failures": failures}, indent=2))
    print("Saved {} station summaries to {}".format(len(records), OUTPUT), flush=True)


if __name__ == "__main__":
    main()
