"""Download Chicago–Calumet pilot hydrography with resumable batches.

Usage: python -u scripts/build.py
Requires: requests
Output: data/streams.geojson
"""
import json
import time
from pathlib import Path

import requests

ENDPOINT = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/6/query"
BBOX = (-87.95, 41.45, -87.45, 42.05)
OUT = Path("data/streams.geojson")
CACHE = Path("data/cache")
BATCH_SIZE = 100
MAX_ATTEMPTS = 4


def request_json(session, params):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(ENDPOINT, params=params, timeout=(15, 35))
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(str(payload["error"]))
            return payload
        except (requests.RequestException, ValueError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError("USGS request failed after retries: {}".format(exc))
            delay = min(2 ** attempt, 15)
            print("Request failed (attempt {}/{}): {}. Retrying in {}s...".format(
                attempt, MAX_ATTEMPTS, exc, delay), flush=True)
            time.sleep(delay)


def base_params():
    return {
        "where": "1=1",
        "geometry": ",".join(map(str, BBOX)),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outSR": 4326,
        "f": "geojson",
    }


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    print("Connecting to USGS and counting stream features...", flush=True)
    params = base_params()
    params.update({"returnCountOnly": "true", "f": "json"})
    count = request_json(session, params).get("count")
    if not isinstance(count, int) or count <= 0:
        raise RuntimeError("No stream features found. Check the USGS layer and bounding box.")
    print("{} features reported. Downloading in batches of {}.".format(count, BATCH_SIZE), flush=True)
    features = []
    for offset in range(0, count, BATCH_SIZE):
        cache_file = CACHE / "streams_{:07d}.json".format(offset)
        if cache_file.exists():
            batch = json.loads(cache_file.read_text())["features"]
            print("Using cached batch {} ({} features)".format(offset // BATCH_SIZE + 1, len(batch)), flush=True)
        else:
            params = base_params()
            params.update({
                "outFields": "GNIS_NAME,COMID",
                "returnGeometry": "true",
                "resultOffset": offset,
                "resultRecordCount": BATCH_SIZE,
                "f": "geojson",
            })
            print("Downloading batch {} (offset {})...".format(offset // BATCH_SIZE + 1, offset), flush=True)
            payload = request_json(session, params)
            batch = payload.get("features", [])
            if not batch:
                raise RuntimeError("Empty batch at offset {}; service pagination may be unsupported".format(offset))
            cache_file.write_text(json.dumps({"features": batch}))
        features.extend(batch)
        print("Progress: {}/{} features".format(len(features), count), flush=True)
    collection = {"type": "FeatureCollection", "features": features}
    OUT.write_text(json.dumps(collection))
    print("Complete: {} features saved to {}".format(len(features), OUT), flush=True)


if __name__ == "__main__":
    main()
