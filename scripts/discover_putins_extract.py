#!/usr/bin/env python3
"""Stream state OSM extracts and find named/tagged paddling access points."""
import json
import os
import re
from pathlib import Path
import osmium

OUT = Path("data/putins_osm_candidates.geojson")
REPORT = Path("data/putins_extract_report.json")
PATTERN = re.compile(r"\\b(?:canoe|kayak|boat)\\s+(?:launch|landing|access|ramp)\\b", re.I)
STATES = ("illinois", "indiana", "michigan", "wisconsin")

def is_candidate(tags):
    name = tags.get("name", "")
    named = bool(PATTERN.search(name))
    tagged = tags.get("leisure") == "slipway" or tags.get("waterway") == "access_point"
    paddling = tags.get("canoe") == "yes" or tags.get("kayak") == "yes"
    return (named or tagged or paddling) and tags.get("access") not in ("no", "private") and not tags.get("shop")

def scan(state):
    path = Path("/tmp") / f"{state}-latest.osm.pbf"
    if not path.exists():
        raise FileNotFoundError(f"Missing extract: {path}")
    found = {}
    # with_locations() resolves way node coordinates without loading XML or GeoJSON.
    for obj in osmium.FileProcessor(str(path)).with_locations():
        if not isinstance(obj, (osmium.osm.Node, osmium.osm.Way)):
            continue
        tags = obj.tags
        if not is_candidate(tags):
            continue
        if isinstance(obj, osmium.osm.Node):
            if not obj.location.valid():
                continue
            coords = [obj.location.lon, obj.location.lat]
            kind = "node"
        else:
            locations = [n.location for n in obj.nodes if n.location.valid()]
            if not locations:
                continue
            coords = [sum(n.lon for n in locations)/len(locations), sum(n.lat for n in locations)/len(locations)]
            kind = "way"
        key = f"osm-{kind}-{obj.id}"
        found[key] = {"type":"Feature", "geometry":{"type":"Point","coordinates":coords},
            "properties":{"id":key,"name":tags.get("name",key),
                "source":"OpenStreetMap","source_url":f"https://www.openstreetmap.org/{kind}/{obj.id}",
                "verification":"candidate_review","access":tags.get("access","unknown"),
                "leisure":tags.get("leisure"),"waterway":tags.get("waterway"),
                "canoe":tags.get("canoe"),"kayak":tags.get("kayak"),
                "state_extract":state,
                "match_type":"launch_name" if PATTERN.search(tags.get("name","")) else "access_tag"}}
    return found

def main():
    previous = {}
    if OUT.exists():
        for feature in json.loads(OUT.read_text()).get("features",[]):
            previous[feature["properties"]["id"]] = feature
    report = {"method":"Geofabrik state PBF streamed with pyosmium", "states":{}, "new_candidates":0}
    for state in STATES:
        before = len(previous)
        matches = scan(state)
        previous.update(matches)
        report["states"][state] = {"matches":len(matches),"new_ids":len(previous)-before}
        print(f"{state}: {len(matches)} matching OSM features; {len(previous)} cumulative",flush=True)
    report["candidate_count"] = len(previous)
    report["warning"] = "Candidates are unverified; motorboat slipways and nonpublic access may be present."
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"type":"FeatureCollection","metadata":{"source":"Geofabrik OSM extracts","verification":"unverified"},"features":list(previous.values())},indent=2)+"\n")
    REPORT.write_text(json.dumps(report,indent=2)+"\n")
    print(f"Completed: {len(previous)} unique candidates",flush=True)

if __name__=="__main__":
    main()
