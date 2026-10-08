"""Calculate trailing-365-day gauge-height minima from USGS observations.

Continuous readings are primary; daily minimum (statistic 00002) is a fallback
for dates without continuous readings. Partial coverage is clearly marked.
Uses modern USGS OGC APIs, paginates responses and checkpoints per station.
Run: python -u scripts/fetch_stage_minima.py
"""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE = "https://api.waterdata.usgs.gov/ogcapi/v1/collections"
GAUGES = Path("data/gauges.geojson")
OUT = Path("data/stage_minima.json")
CACHE = Path("data/cache/stage_minima")
MAX_PAGES = 100
PAGE_SIZE = 10000


def request_json(session, url, params=None):
    for attempt in range(1, 4):
        start = time.monotonic()
        try:
            response = session.get(url, params=params, timeout=(12, 40))
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            print("    attempt {}/3 failed after {:.1f}s: {}".format(
                attempt, time.monotonic() - start, exc), flush=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def collect(session, kind, site, start, end, stat=None):
    url = BASE + "/" + kind + "/items"
    params = {"f": "json", "monitoring_location_id": "USGS-" + site,
              "parameter_code": "00065", "datetime": start + "/" + end,
              "limit": PAGE_SIZE}
    if stat:
        params["statistic_id"] = stat
    observations = []
    seen = set()
    for page in range(1, MAX_PAGES + 1):
        print("    {} page {}...".format(kind, page), flush=True)
        data = request_json(session, url, params)
        features = data.get("features", [])
        for feature in features:
            p = feature.get("properties") or {}
            if p.get("monitoring_location_id") != "USGS-" + site:
                continue
            if str(p.get("parameter_code")) != "00065":
                continue
            if stat and str(p.get("statistic_id")) != stat:
                continue
            try:
                value = float(p["value"])
                date = str(p["time"])[:10]
                if value > -9999 and start[:10] <= date <= end[:10]:
                    observations.append((date, value))
            except (ValueError, TypeError, KeyError):
                continue
        next_url = next((link.get("href") for link in data.get("links", [])
                         if link.get("rel") == "next"), None)
        if not next_url:
            return observations
        if next_url in seen or urlparse(next_url).netloc != "api.waterdata.usgs.gov":
            raise RuntimeError("Invalid/repeated pagination URL")
        seen.add(next_url)
        url, params = next_url, None
    raise RuntimeError("Exceeded {} pages for {}".format(MAX_PAGES, site))


def calculate(session, site, start, end):
    continuous = collect(session, "continuous", site, start, end)
    # Always consult daily minima to cover older gaps and short IV histories.
    daily = collect(session, "daily", site, start, end, stat="00002")
    # Daily values are daily minima, NOT daily means (00003).
    combined = continuous + daily
    if not combined:
        return {"minimum_ft": None, "coverage_days": 0, "coverage_fraction": 0,
                "complete_year": False, "continuous_count": 0, "daily_count": 0}
    dates = {date for date, _ in combined}
    minimum = min(v for _, v in combined)
    coverage = len(dates)
    # One daily observation per day is sufficient to establish an observed minimum,
    # but a full-year label requires coverage on at least 95% of days.
    days = (datetime.fromisoformat(end[:10]) - datetime.fromisoformat(start[:10])).days + 1
    return {"minimum_ft": minimum, "coverage_days": coverage,
            "coverage_fraction": round(coverage / days, 3),
            "complete_year": coverage / days >= .95,
            "continuous_count": len(continuous), "daily_count": len(daily),
            "first_observation": min(dates), "last_observation": max(dates)}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True))
    tmp.replace(path)


def main():
    if not GAUGES.exists():
        raise RuntimeError("Run fetch_gauges.py first")
    sites = sorted({str(f["properties"]["site"]) for f in
                    json.loads(GAUGES.read_text())["features"]})
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=364)
    start_s, end_s = start.isoformat(), end.isoformat()
    print("USGS continuous + daily minima for {} stations, {} to {}".format(
        len(sites), start_s, end_s), flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    records = {}
    failures = {}
    with requests.Session() as session:
        for index, site in enumerate(sites, 1):
            path = CACHE / ("{}_{}_{}.json".format(site, start_s, end_s))
            print("[{}/{}] USGS {} {}".format(index, len(sites), site,
                  "(cached)" if path.exists() else ""), flush=True)
            try:
                if path.exists():
                    record = json.loads(path.read_text())
                else:
                    record = calculate(session, site, start_s, end_s)
                    save(path, record)
                records[site] = record
                print("    minimum={} ft; {} observed days; full-year={}".format(
                    record["minimum_ft"], record["coverage_days"],
                    record["complete_year"]), flush=True)
            except (requests.RequestException, ValueError, RuntimeError, KeyError) as exc:
                failures[site] = str(exc)
                print("    FAILED: {}".format(exc), flush=True)
            save(OUT, {"metadata": {"retrieved_at": datetime.now(timezone.utc).isoformat(),
                "start_date": start_s, "end_date": end_s,
                "method": "USGS continuous readings + daily minimum statistic 00002",
                "coverage_note": "Full year means >=95% calendar-day coverage, not continuous sampling."},
                "stations": records, "failures": failures})
    print("Saved {} station minima ({} full-year); {} errors to {}".format(
        len(records), sum(r["complete_year"] for r in records.values()),
        len(failures), OUT), flush=True)


if __name__ == "__main__":
    main()
