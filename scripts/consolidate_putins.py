#!/usr/bin/env python3
"""Identify likely duplicate OSM put-ins without deleting source records.

Run: python3 scripts/consolidate_putins.py
Creates data/putins_duplicate_review.json with groups for human review.
"""
import json, math, re
from collections import defaultdict
from pathlib import Path

SOURCE=Path("data/putins_osm_candidates.geojson")
OUTPUT=Path("data/putins_duplicate_review.json")
MAX_METERS=100

def norm(name):
    name=re.sub(r"\\b(canoe|kayak|boat|launch|landing|access|ramp|put.in|site|point)\\b"," ",str(name or "").lower())
    return " ".join(re.findall(r"[a-z0-9]+",name))

def meters(a,b):
    lon1,lat1=a;lon2,lat2=b
    return math.hypot((lon1-lon2)*111320*math.cos(math.radians((lat1+lat2)/2)),(lat1-lat2)*111320)

def main():
    features=json.loads(SOURCE.read_text())["features"]
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
        cells[(int(math.floor(lon*1000)),int(math.floor(lat*1000)))].append(i)
    for (x,y),ids in cells.items():
        nearby=[j for dx in (-1,0,1) for dy in (-1,0,1) for j in cells.get((x+dx,y+dy),[])]
        for i in ids:
            p=features[i]["properties"];name=norm(p.get("name"))
            for j in nearby:
                if j<=i:continue
                q=features[j]["properties"];other=norm(q.get("name"))
                distance=meters(features[i]["geometry"]["coordinates"],features[j]["geometry"]["coordinates"])
                # Require a close match and meaningful shared name; never merge solely on proximity.
                if distance<=MAX_METERS and name and other and (name==other or (len(name)>=8 and len(other)>=8 and (name in other or other in name))):
                    union(i,j)
    groups=defaultdict(list)
    for i in range(len(features)):groups[find(i)].append(i)
    duplicates=[]
    for indices in groups.values():
        if len(indices)<2:continue
        entries=[]
        for i in indices:
            f=features[i];p=f["properties"]
            entries.append({"id":p.get("id"),"name":p.get("name"),"coordinates":f["geometry"]["coordinates"],"access":p.get("access"),"url":p.get("source_url")})
        duplicates.append({"count":len(entries),"candidates":entries})
    duplicates.sort(key=lambda g:(-g["count"],g["candidates"][0]["name"] or ""))
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps({"method":"100m proximity plus normalized shared name; review only, no automatic deletion","source_count":len(features),"duplicate_groups":len(duplicates),"possible_redundant_records":sum(g["count"]-1 for g in duplicates),"groups":duplicates},indent=2)+"\\n")
    print(f"{len(features)} candidates; {len(duplicates)} possible duplicate groups; report: {OUTPUT}")

if __name__=="__main__":main()
