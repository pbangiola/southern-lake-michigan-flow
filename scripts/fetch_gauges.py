"""Fetch current USGS stage/discharge for the southern Lake Michigan region.

Run: python -u scripts/fetch_gauges.py
Writes data/gauges.geojson. Flood thresholds are optional entries in
data/flood_stages.json keyed by USGS site ID, in feet relative to gauge datum.
No paddling safety determination is made.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = "https://waterservices.usgs.gov/nwis/iv/"
# USGS bounding-box order: west,south,east,north
BBOX = "-88.7,40.9,-85.4,43.2"
OUTPUT = Path("data/gauges.geojson")
THRESHOLDS = Path("data/flood_stages.json")


def main():
    thresholds = json.loads(THRESHOLDS.read_text()) if THRESHOLDS.exists() else {}
    params = {
        "format": "json",
        "bBox": BBOX,
        "parameterCd": "00065,00060",
        "siteStatus": "active",
        "period": "P1D",
    }
    print("Requesting USGS stage (00065) and discharge (00060)...", flush=True)
    response = requests.get(URL, params=params, timeout=(15, 60))
    response.raise_for_status()
    series = response.json().get("value", {}).get("timeSeries", [])
    stations = {}
    for item in series:
        info = item.get("sourceInfo", {})
        site_codes = info.get("siteCode", [])
        if not site_codes:
            continue
        site = site_codes[0].get("value")
        location = info.get("geoLocation", {}).get("geogLocation", {})
        lat, lon = location.get("latitude"), location.get("longitude")
        if not site or lat is None or lon is None:
            continue
        code = item.get("variable", {}).get("variableCode", [{}])[0].get("value")
        values = [v for block in item.get("values", []) for v in block.get("value", [])
                  if v.get("value") not in (None, "", "-999999")]
        if not values or code not in ("00065", "00060"):
            continue
        latest = max(values, key=lambda v: v.get("dateTime", ""))
        entry = stations.setdefault(site, {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"site": site, "name": info.get("siteName", site)},
        })
        prefix = "stage" if code == "00065" else "discharge"
        try:
            entry["properties"][prefix] = float(latest["value"])
        except (TypeError, ValueError):
            continue
        entry["properties"][prefix + "_time"] = latest.get("dateTime")
    for site, feature in stations.items():
        props = feature["properties"]
        config = thresholds.get(site, {})
        flood = config.get("flood_stage_ft")
        props["flood_stage_ft"] = flood
        props["flood_source"] = config.get("source")
        props["feet_below_flood"] = (
            round(float(flood) - props["stage"], 2)
            if flood is not None and "stage" in props else None
        )
        # Stage relative to flood stage is not a paddling-safety classification.
        props["status"] = "at_or_above_flood" if props["feet_below_flood"] is not None and props["feet_below_flood"] <= 0 else (
            "below_flood" if props["feet_below_flood"] is not None else "unknown"
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "type": "FeatureCollection",
        "metadata": {"retrieved_at": datetime.now(timezone.utc).isoformat(),
                     "source": "USGS NWIS instantaneous values",
                     "warning": "Flood stage is not a paddling safety threshold."},
        "features": list(stations.values()),
    }, indent=2))
    print("Saved {} gauge locations to {}".format(len(stations), OUTPUT), flush=True)
    print("Flood thresholds configured for {} gauges.".format(
        sum(1 for f in stations.values() if f["properties"]["flood_stage_ft"] is not None)
    ), flush=True)


if __name__ == "__main__":
    main()
