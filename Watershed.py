#!/usr/bin/env python3
"""One-command local EDNA watershed -> gauge-linked river network pipeline.

Run from the repository root:
    python3 Watershed.py --match great
    python3 Watershed.py --all              # download every EDNA archive (large!)
    python3 Watershed.py --offline          # use archives already in local/watersheds

Downloads occur ONLY on this computer, never in GitHub Actions.
Only the derived data/river_segments.geojson should be committed.
"""
import argparse
import html.parser
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INDEX="https://edna.usgs.gov/watersheds/kml_index.htm"
ARCHIVES=ROOT/"local"/"watersheds"
OUTPUT=ROOT/"data"/"river_segments.geojson"
AGENT="SouthernLakeMichiganAtlas/1.0 (local watershed download)"
class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":
            href=dict(attrs).get("href","")
            if re.search(r"\.(?:kmz|kml)(?:[?#]|$)",href,re.I):
                self.links.append(urllib.parse.urljoin(INDEX,href))

def fetch(url,destination,retries=3):
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists() and destination.stat().st_size:
        if destination.suffix.lower()!=".kmz" or zipfile.is_zipfile(destination):
            print("Reuse",destination.name,flush=True);return
        destination.unlink()
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":AGENT})
            with urllib.request.urlopen(req,timeout=90) as response, destination.with_suffix(destination.suffix+".part").open("wb") as out:
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    out.write(chunk)
            part=destination.with_suffix(destination.suffix+".part")
            if destination.suffix.lower()==".kmz" and not zipfile.is_zipfile(part):
                raise ValueError("Not a valid KMZ archive: "+url)
            part.replace(destination)
            print("Saved",destination.name,round(destination.stat().st_size/1048576,2),"MiB",flush=True)
            return
        except Exception as exc:
            destination.with_suffix(destination.suffix+".part").unlink(missing_ok=True)
            if attempt==retries-1:raise
            print("Retrying",url,str(exc),flush=True)
            time.sleep(2**attempt)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--match",default="great",help="Case-insensitive substring in EDNA download filename; default 'great'")
    ap.add_argument("--all",action="store_true",help="Download all linked watershed archives; potentially large")
    ap.add_argument("--offline",action="store_true",help="Do not contact USGS; use local KMZ files")
    ap.add_argument("--no-build",action="store_true",help="Download only, without processing")
    ap.add_argument("--max-distance-m",type=float,default=200)
    args=ap.parse_args()
    ARCHIVES.mkdir(parents=True,exist_ok=True)
    if not args.offline:
        request=urllib.request.Request(INDEX,headers={"User-Agent":AGENT})
        with urllib.request.urlopen(request,timeout=40) as response:
            page=response.read(3_000_000).decode("utf-8","replace")
        parser=Links();parser.feed(page)
        urls=list(dict.fromkeys(parser.links))
        if not args.all:
            urls=[url for url in urls if args.match.lower() in urllib.parse.unquote(url).lower()]
        if not urls:
            raise SystemExit("No matching EDNA KML/KMZ links found. Try --all or a different --match.")
        print("Selected",len(urls),"USGS source archives",flush=True)
        for url in urls:
            name=Path(urllib.parse.urlsplit(url).path).name
            if not name:continue
            fetch(url,ARCHIVES/urllib.parse.unquote(name))
            time.sleep(0.5)
    if args.no_build:return
    kmzs=sorted(ARCHIVES.glob("*.kmz"))
    if not kmzs:raise SystemExit("No KMZ files found; download first or copy KMZ files to local/watersheds/")
    try:
        import shapely
        import lxml
    except ImportError:
        raise SystemExit("Install local dependencies: python3 -m pip install -r requirements-watershed.txt")
    cmd=[sys.executable,str(ROOT/"scripts"/"build_river_segments.py"),*[str(p) for p in kmzs],
         "--gauges",str(ROOT/"data"/"gauges.geojson"),"--output",str(OUTPUT),
         "--max-distance-m",str(args.max_distance_m)]
    print("Building gauge-linked segments from",len(kmzs),"KMZ archives",flush=True)
    subprocess.run(cmd,cwd=ROOT,check=True)
    obj=json.loads(OUTPUT.read_text())
    print("Built",len(obj.get("features",[])),"river segments")
    print("Review data/river_segments.geojson, then commit only that derived file:")
    print("  git add data/river_segments.geojson && git commit -m 'Build gauge-linked river network' && git push")
    print("Raw source archives remain local; no downloads are duplicated in GitHub Actions.")

if __name__=="__main__":main()
