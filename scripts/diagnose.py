"""Diagnose USGS ArcGIS hydrography endpoint before bulk downloading.

Run: python -u scripts/diagnose.py
No large data downloads; writes a single-feature probe to data/diagnostics/.
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer"
LAYER = BASE + "/6"
OUT = Path("data/diagnostics")
TIMEOUT = (8, 15)


def probe(session, label, url, params):
    print("\nChecking {}: {}".format(label, url), flush=True)
    started = time.monotonic()
    try:
        r = session.get(url, params=params, timeout=TIMEOUT)
        print("  HTTP {} in {:.1f}s".format(r.status_code, time.monotonic() - started), flush=True)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError("ArcGIS error: {}".format(data["error"]))
        return data
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print("  FAILED: {}".format(exc), flush=True)
        return None


def main():
    print("Python:", sys.version.split()[0])
    print("requests:", requests.__version__)
    print("USGS host:", urlparse(BASE).hostname)
    OUT.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        service = probe(session, "service metadata", BASE, {"f": "json"})
        if service is None:
            print("\nSTOP: service metadata unavailable. No bulk query attempted.")
            return 1
        print("  Service version:", service.get("currentVersion"))
        layer = probe(session, "layer metadata", LAYER, {"f": "json"})
        if layer is None:
            print("\nSTOP: layer metadata unavailable.")
            return 1
        print("  Layer:", layer.get("name"))
        print("  Geometry:", layer.get("geometryType"))
        print("  Query capability:", layer.get("capabilities"))
        fields = {field.get("name") for field in layer.get("fields", [])}
        print("  Fields include:", ", ".join(sorted(fields)[:12]))
        if "Query" not in str(layer.get("capabilities", "")):
            print("\nSTOP: layer does not advertise Query support.")
            return 1
        oid = layer.get("objectIdField") or layer.get("objectIdFieldName")
        if not oid:
            oid = next((f.get("name") for f in layer.get("fields", []) if f.get("type") == "esriFieldTypeOID"), None)
        if not oid:
            print("\nSTOP: no object ID field found.")
            return 1
        params = {
            "f": "geojson",
            "where": "{} >= 0".format(oid),
            "outFields": "*",
            "returnGeometry": "true",
            "resultRecordCount": 1,
            "outSR": 4326,
        }
        sample = probe(session, "one-feature query", LAYER + "/query", params)
        if sample is None:
            print("\nSTOP: metadata works but feature queries fail. Try another source or a bulk download.")
            return 2
        features = sample.get("features", [])
        if not features:
            print("\nSTOP: query succeeded but returned no features.")
            return 2
        path = OUT / "one_feature.geojson"
        path.write_text(json.dumps(sample, indent=2))
        print("\nPASS: one feature saved to {}".format(path))
        print("Next: implement bounded incremental downloads using verified layer capabilities.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
