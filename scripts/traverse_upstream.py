#!/usr/bin/env python3
"""Deterministic, resumable upstream traversal of an authoritative directed river graph.

Input: GeoJSON LineString reaches with stable id and downstream_id properties.
downstream_id=null means an ocean/Great Lakes terminal ONLY if source data confirms it.
No flow direction is inferred from coordinate order or nearest distance.
"""
import argparse, collections, json
from pathlib import Path

def read(path):
    return json.loads(Path(path).read_text())
def save(path, obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+".tmp")
    temp.write_text(json.dumps(obj,separators=(",",":")))
    temp.replace(p)
def build(features):
    reaches={}; upstream=collections.defaultdict(list); roots=[]
    for f in features:
        p=f.get("properties") or {}
        rid=str(p.get("reach_id") or p.get("id") or "")
        if not rid or rid in reaches: raise ValueError("missing or duplicate reach_id: "+rid)
        reaches[rid]=f
    for rid,f in reaches.items():
        p=f["properties"];down=p.get("downstream_id")
        if down is None:
            if p.get("terminal_type") in ("ocean","great_lake"):
                roots.append(rid)
            continue
        down=str(down)
        if down in reaches:upstream[down].append(rid)
    return reaches,upstream,sorted(roots)
def run(network,state_path,output_path,limit):
    reaches,upstream,roots=build(read(network)["features"])
    state=read(state_path) if Path(state_path).exists() else {"queue":roots,"seen":[],"network":str(network)}
    if state.get("network")!=str(network):raise ValueError("checkpoint belongs to another network")
    queue=collections.deque(state["queue"]);seen=set(state["seen"]);batch=[]
    while queue and len(batch)<limit:
        rid=queue.popleft()
        if rid in seen:continue
        seen.add(rid);batch.append(reaches[rid])
        queue.extend(child for child in upstream[rid] if child not in seen)
    save(output_path,{"type":"FeatureCollection","features":batch,"metadata":{"processed":len(seen),"remaining_queue":len(queue),"total_reaches":len(reaches)}})
    save(state_path,{"network":str(network),"queue":list(queue),"seen":sorted(seen),"complete":not queue,"total_reaches":len(reaches),"processed":len(seen)})
    print(f"Processed {len(batch)} reaches; {len(seen)}/{len(reaches)} total; queued {len(queue)}")
    if not roots:print("WARNING: no verified ocean/Great Lakes terminal reaches in source")
    if not queue and len(seen)<len(reaches):print(f"WARNING: {len(reaches)-len(seen)} unreachable reaches; inspect inland sinks/disconnected basins")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--network",required=True)
    p.add_argument("--state",default="data/upstream_traversal_state.json")
    p.add_argument("--output",default="local/upstream_batch.geojson")
    p.add_argument("--limit",type=int,default=1000)
    a=p.parse_args()
    if a.limit<1: p.error("--limit must be positive")
    run(a.network,a.state,a.output,a.limit)
if __name__=="__main__":main()
