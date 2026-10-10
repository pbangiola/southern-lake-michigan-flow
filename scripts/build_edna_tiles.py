#!/usr/bin/env python3
"""Build zoom-dependent XYZ vector tiles from published EDNA watershed GeoJSON.

tippecanoe drops redundant detail at low zoom, preserving full geometry at high zoom.
"""
import json
import gzip
import subprocess
from pathlib import Path

ROOT=Path("data/edna_watersheds")
OUT=Path("data/edna_tiles")
def main():
    manifest=json.loads((ROOT/"manifest.json").read_text())
    if manifest.get("complete") is not True:
        raise RuntimeError("EDNA import incomplete; refusing tile publication")
    files=[Path(entry["file"]) for entry in manifest["sources"] if entry.get("features",0)>0]
    if not files: raise RuntimeError("No EDNA features to tile")
    OUT.mkdir(parents=True,exist_ok=True)
    cmd=["tippecanoe","-e",str(OUT),"-f","-Z","0","-z","12","-l","edna",
         "--drop-densest-as-needed","--extend-zooms-if-still-dropping",
         "--simplification=8","--no-feature-limit","--no-tile-size-limit",
         "--read-parallel"]+[str(p) for p in files]
    subprocess.run(cmd,check=True)
    # GitHub Pages serves .pbf without Content-Encoding: gzip. Tippecanoe
    # emits gzipped PBFs; decompress them for MapLibre's static-file loader.
    count=0
    for tile in OUT.rglob("*.pbf"):
        raw=tile.read_bytes()
        if raw.startswith(b"\\x1f\\x8b"):
            tile.write_bytes(gzip.decompress(raw))
            count+=1
    print("Decompressed",count,"PBF tiles for GitHub Pages",flush=True)
    (OUT/"manifest.json").write_text(json.dumps({
        "complete":True,"source_bbox":manifest.get("bbox"),"source_features":manifest.get("total_features"),
        "tiles":"{z}/{x}/{y}.pbf","maxzoom":12,"layer":"edna"
    },indent=2))
    print("Finished EDNA XYZ tiles",flush=True)
if __name__=="__main__":main()
