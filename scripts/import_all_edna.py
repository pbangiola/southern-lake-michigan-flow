#!/usr/bin/env python3
"""Import every KMZ listed by USGS EDNA, clipping to the atlas region.
Publish only after all source downloads and parses succeed.
"""
import json, re, urllib.request, urllib.parse, tempfile, time
from html.parser import HTMLParser
from pathlib import Path
from traverse_edna_graph import streams, edge_key
from shapely.geometry import box, mapping

INDEX="https://edna.usgs.gov/watersheds/kml_index.htm"
BBOX=(-180.0, 18.0, -65.0, 72.0)
OUT=Path("data/edna_watersheds")
def main():
    html=urllib.request.urlopen(INDEX,timeout=90).read().decode("utf-8","replace")
    class Links(HTMLParser):
        def __init__(self):
            super().__init__();self.hrefs=[]
        def handle_starttag(self,tag,attrs):
            if tag.lower()=='a':
                for key,value in attrs:
                    if key.lower()=='href' and value:self.hrefs.append(value)
    parser=Links();parser.feed(html)
    urls=sorted(set(urllib.parse.urljoin(INDEX,href) for href in parser.hrefs
                    if '.kmz' in urllib.parse.urlsplit(href).path.lower()))
    print('Index links:',len(parser.hrefs),'KMZ sources:',len(urls),flush=True)
    if not urls:
        print('Sample links:',parser.hrefs[:12],flush=True)
        raise RuntimeError('No EDNA KMZ links found; refusing to publish')
    OUT.mkdir(parents=True,exist_ok=True)
    manifest={"type":"edna-watershed-import-v1","source_index":INDEX,"bbox":BBOX,"sources":[],"complete":False}
    seen=set()
    for n,url in enumerate(urls,1):
        name=Path(urllib.parse.urlparse(url).path).stem.lower()
        dest=OUT/(name+".geojson")
        print(f"[{n}/{len(urls)}] {name}",flush=True)
        with tempfile.TemporaryDirectory() as td:
            kmz=Path(td)/(name+".kmz")
            for attempt in range(3):
                try:
                    urllib.request.urlretrieve(url,kmz)
                    break
                except Exception:
                    if attempt==2:raise
                    time.sleep(5*(attempt+1))
            features=[]
            for line in streams(kmz,box(*BBOX)):
                coords=list(line.coords)
                key=edge_key(coords)
                if key in seen:continue
                seen.add(key)
                features.append({"type":"Feature","geometry":mapping(line),"properties":{"segment_id":key,"source_kmz":name,"orientation":"unverified"}})
        payload={"type":"FeatureCollection","features":features}
        tmp=dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload,separators=(",",":")))
        tmp.replace(dest)
        manifest["sources"].append({"name":name,"url":url,"file":str(dest),"features":len(features)})
        print("  clipped unique segments:",len(features),flush=True)
    manifest["complete"]=True
    manifest["total_features"]=sum(s["features"] for s in manifest["sources"])
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print("COMPLETE",len(urls),"KMZs",manifest["total_features"],"segments",flush=True)
if __name__=="__main__":main()
