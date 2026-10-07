"""Fetch a pilot hydrography network from the USGS National Map ArcGIS service.

This first pass exports geographic stream lines, NOT estimated discharge.
Run: pip install requests; python scripts/build.py
"""
import json
from pathlib import Path
import requests

ENDPOINT = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/6/query"
# Chicago–Calumet pilot extent (lon/lat).
BBOX = (-87.95, 41.45, -87.45, 42.05)
OUT = Path("data/streams.geojson")


def fetch():
    features = []
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "geometry": ",".join(map(str, BBOX)),
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "outSR": 4326,
            "returnGeometry": "true",
            "resultOffset": offset,
            "resultRecordCount": 1000,
            "f": "geojson",
        }
        r = requests.get(ENDPOINT, params=params, timeout=90)
        r.raise_for_status()
        payload = r.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        batch = payload.get("features", [])
        features.extend(batch)
        if len(batch) < 1000:
            break
        offset += len(batch)
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    data = fetch()
    if not data["features"]:
        raise RuntimeError("No features returned; verify USGS layer ID and service availability")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data))
    print(f"Wrote {len(data['features'])} stream features to {OUT}")
