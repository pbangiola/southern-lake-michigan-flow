"""Download observed daily minimum stage over the last 365 days for USGS sites.

USGS daily-values statistic 00003 is the daily minimum. Stations without
published daily minima remain unclassified; no synthetic minima are used.
Run: python -u scripts/fetch_stage_minima.py
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

URL = "https://waterservices.usgs.gov/nwis/dv/"
BBOX = "-88.7,40.9,-85.4,43.2"
OUT = Path("data/stage_minima.json")


def main():
    params = {"format": "json", "bBox": BBOX, "parameterCd": "00065",
              "statCd": "00003", "siteStatus": "active", "period": "P365D"}
    started = time.monotonic()
    for attempt in range(1, 4):
        print("Downloading USGS daily minimum stage, attempt {}/3...".format(attempt), flush=True)
        try:
            response = requests.get(URL, params=params, timeout=(15, 45))
            response.raise_for_status()
            print("Received {:.1f} KB after {:.1f}s".format(len(response.content)/1024,
                time.monotonic()-started), flush=True)
            break
        except requests.RequestException as exc:
            print("Attempt failed: {}".format(exc), flush=True)
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    series = response.json().get("value", {}).get("timeSeries", [])
    print("Processing {} daily-minimum series...".format(len(series)), flush=True)
    minima = {}
    for index, item in enumerate(series, 1):
        if index == 1 or index % 50 == 0 or index == len(series):
            print("Series {}/{}".format(index, len(series)), flush=True)
        site_codes = item.get("sourceInfo", {}).get("siteCode", [])
        if not site_codes:
            continue
        site = str(site_codes[0].get("value", ""))
        variable = item.get("variable", {})
        codes = [v.get("value") for v in variable.get("variableCode", [])]
        stats = [v.get("value") for v in variable.get("options", {}).get("option", [])
                 if v.get("name") == "Statistic"]
        if "00065" not in codes or "00003" not in stats:
            continue
        values = []
        for block in item.get("values", []):
            for point in block.get("value", []):
                try:
                    val = float(point["value"])
                    if val > -9999:
                        values.append(val)
                except (KeyError, TypeError, ValueError):
                    pass
        if values:
            minimum = min(values)
            minima[site] = min(minima.get(site, minimum), minimum)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"metadata": {"retrieved_at": datetime.now(timezone.utc).isoformat(),
        "method": "USGS NWIS daily minimum stage statistic 00003, trailing 365 days",
        "note": "Daily minimum stage is only available at reporting stations."},
        "minima": minima}, indent=2, sort_keys=True))
    print("Saved 12-month observed daily minima for {} stations to {}".format(len(minima), OUT), flush=True)


if __name__ == "__main__":
    main()
