#!/usr/bin/env python3
"""Download and inspect official USGS EDNA watershed KMZ source archives."""
import argparse, json, urllib.request, zipfile
from pathlib import Path
SOURCES={
    "mississippi":"https://edna.usgs.gov/watersheds/sheds/mississippi/mississippi.kmz",
    "greatlakes":"https://edna.usgs.gov/watersheds/sheds/greatlakes/greatlakes.kmz",
}
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",default="local/edna")
    args=parser.parse_args()
    output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=True)
    manifest={}
    for name,url in SOURCES.items():
        path=output/(name+".kmz")
        req=urllib.request.Request(url,headers={"User-Agent":"Illinois-River-Atlas/1.0 (public hydrography research)"})
        with urllib.request.urlopen(req,timeout=180) as response, path.open("wb") as dest:
            while True:
                block=response.read(1024*1024)
                if not block:break
                dest.write(block)
        with zipfile.ZipFile(path) as archive:
            bad=archive.testzip()
            if bad:raise ValueError("Corrupt archive entry: "+bad)
            names=archive.namelist()
            manifest[name]={"source_url":url,"bytes":path.stat().st_size,"entries":len(names),
                            "kml_entries":[n for n in names if n.lower().endswith(".kml")][:20]}
        print(name,manifest[name])
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
if __name__=="__main__":main()
