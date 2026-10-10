#!/usr/bin/env python3
"""Consolidate regional and OSM launch candidates for map display.

Preserve source datasets; merge only strong name matches within 100 meters.
Run: python3 scripts/consolidate_putins.py
"""
import json, math, re
from collections import defaultdict
from pathlib import Path

OSM=Path("data/putins_osm_candidates.geojson")
REGIONAL=Path("data/regional_launches.geojson")
OUTPUT=Path("data/putins_consolidated.geojson")
REPORT=Path("data/putins_duplicate_review.json")
MAX_METERS=100

def norm(name):
    name=re.sub(r"\b(canoe|kayak|boat|launch|landing|access|ramp|put.in|site|point)\b"," ",str(name or "").lower())
    return " ".join(re.findall(r"[a-z0-9]+",name))

def meters(a,b):
    lon1,lat1=a[:2];lon2,lat2=b[:2]
    return math.hypot((lon1-lon2)*111320*math.cos(math.radians((lat1+lat2)/2)),(lat1-lat2)*111320)

def main():
    osm=json.loads(OSM.read_text())["features"]
    regional=json.loads(REGIONAL.read_text())["features"]
    features=[f for f in regional+osm if f.get("geometry",{}).get("type")=="Point" and len(f["geometry"].get("coordinates",[]))>=2]
    parent=list(range(len(features)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(i,j):
        a,b=find(i),find(j)
        if a!=b:parent[max(a,b)]=min(a,b)
    cells=defaultdict(list)
    for i,f in enumerate(features):
        lon,lat=f["geometry"]["coordinates"][:2]
        cells[(math.floor(lon*1000),math.floor(lat*1000))].append(i)
    for (x,y),ids in cells.items():
        nearby=[j for dx in (-1,0,1) for dy in (-1,0,1) for j in cells.get((x+dx,y+dy),[])]
        for i in ids:
            p=features[i]["properties"];name=norm(p.get("name"))
            if not name or name.startswith("osm node") or name.startswith("osm way"):continue
            for j in nearby:
                if j<=i:continue
                q=features[j]["properties"];other=norm(q.get("name"))
                if not other or other.startswith("osm node") or other.startswith("osm way"):continue
                if meters(features[i]["geometry"]["coordinates"],features[j]["geometry"]["coordinates"])>MAX_METERS:continue
                if name==other or (len(name)>=8 and len(other)>=8 and (name in other or other in name)):
                    union(i,j)
    groups=defaultdict(list)
    for i in range(len(features)):groups[find(i)].append(i)
    consolidated=[];duplicates=[]
    for indices in groups.values():
        # Prefer regional attributes and coordinates; retain provenance of every matching OSM record.
        indices.sort(key=lambda i:(features[i]["properties"].get("source")!="master_regional_watercraft_launches_v2.csv",i))
        primary=features[indices[0]]
        p=dict(primary["properties"])
        p["source_ids"]=[features[i]["properties"].get("id") for i in indices]
        p["source_urls"]=[features[i]["properties"].get("source_url") for i in indices if features[i]["properties"].get("source_url")]
        p["merged_records"]=len(indices)
        p["verification"]="unverified"
        consolidated.append({"type":"Feature","geometry":primary["geometry"],"properties":p})
        if len(indices)>1:
            duplicates.append({"name":p.get("name"),"source_ids":p["source_ids"],"coordinates":[features[i]["geometry"]["coordinates"] for i in indices]})
    OUTPUT.write_text(json.dumps({"type":"FeatureCollection","metadata":{"verification":"unverified","method":"Strong name match within 100m; source records preserved"},"features":consolidated},indent=2)+"\n")
    REPORT.write_text(json.dumps({"osm_count":len(osm),"regional_count":len(regional),"consolidated_count":len(consolidated),"merged_groups":len(duplicates),"possible_duplicate_groups":duplicates},indent=2)+"\n")
    print(f"{len(osm)} OSM + {len(regional)} regional -> {len(consolidated)} displayed; {len(duplicates)} merged groups")

if __name__=="__main__":main()
