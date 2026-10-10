#!/usr/bin/env python3
"""Root an undirected EDNA stream graph near the Illinois mouth and traverse upstream.

This treats connected stream lines as an undirected graph, oriented by distance
from a selected outlet. Cycles and ambiguous snapping are reported, not silently
declared true hydrological flow directions.
"""
import argparse, collections, hashlib, json, math
from pathlib import Path
from shapely.geometry import Point, box, LineString, mapping
from shapely.ops import nearest_points
from build_river_segments import streams

MOUTH=(-90.62,38.97)  # Approximate confluence; verify selected seed against map.
BBOX=(-93.0,37.0,-86.0,44.0)
def write(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_text(json.dumps(obj,separators=(",",":")));tmp.replace(p)
def node(pt,precision=5):
    return tuple(round(float(v),precision) for v in pt[:2])
def edge_key(coords):
    seq=tuple(node(p,7) for p in coords)
    return hashlib.sha256(repr(min(seq,seq[::-1])).encode()).hexdigest()[:24]
def graph_from_kmz(files,bbox):
    edges={};adj=collections.defaultdict(list)
    for file in files:
        for line in streams(file,box(*bbox)):
            coords=list(line.coords)
            if len(coords)<2:continue
            a,b=node(coords[0]),node(coords[-1])
            if a==b:continue
            eid=edge_key(coords)
            if eid in edges:continue
            edges[eid]={"a":a,"b":b,"coords":coords,"source":file.name}
            adj[a].append(eid);adj[b].append(eid)
    return edges,adj
def traverse(edges,adj,mouth,limit,state,existing):
    # Select an endpoint near the Illinois mouth, not an arbitrary interior
    # point; require human review of selected endpoint before declaring coverage.
    candidates=[(math.dist((p[0]*math.cos(math.radians(mouth[1])),p[1]),
                            (mouth[0]*math.cos(math.radians(mouth[1])),mouth[1])),p) for p in adj]
    if not candidates:raise ValueError("No connected stream LineStrings in EDNA source")
    distance,root=min(candidates)
    if distance>0.12:raise ValueError(f"No stream endpoint within ~12km of confluence; nearest distance {distance:.4f} degrees")
    checkpoint=Path(state)
    saved=json.loads(checkpoint.read_text()) if checkpoint.exists() else None
    if saved and tuple(saved["root"])!=root:raise ValueError("Root changed; reset checkpoint explicitly")
    queue=collections.deque(tuple(x) for x in saved["queue"]) if saved else collections.deque([root])
    seen_nodes={tuple(x) for x in saved["seen_nodes"]} if saved else set()
    seen_edges=set(saved["seen_edges"]) if saved else set()
    output=[];intersections=[];cycles=[]
    while queue and len(output)<limit:
        current=queue.popleft()
        if current in seen_nodes:continue
        seen_nodes.add(current)
        # Deterministic right-hand-first by polar angle of outgoing edge.
        neighbors=[]
        for eid in adj[current]:
            e=edges[eid];other=e["b"] if e["a"]==current else e["a"]
            angle=math.atan2(other[1]-current[1],other[0]-current[0])
            neighbors.append((angle,eid,other))
        for _,eid,other in sorted(neighbors,reverse=True):
            if eid in seen_edges:continue
            seen_edges.add(eid)
            if eid in existing:
                intersections.append(eid)
                continue
            if other in seen_nodes:cycles.append(eid)
            e=edges[eid]
            coords=e["coords"] if e["a"]==current else list(reversed(e["coords"]))
            output.append({"type":"Feature","geometry":mapping(LineString(coords)),
                           "properties":{"segment_id":eid,"course_origin":list(current),
                                         "orientation":"outlet-rooted graph traversal; not verified hydrologic flow",
                                         "source_kmz":e["source"]}})
            if other not in seen_nodes:queue.append(other)
            if len(output)>=limit:break
    result={"type":"FeatureCollection","features":output,"metadata":{
        "root":list(root),"root_distance_degrees":distance,
        "new_segments":len(output),"total_processed_edges":len(seen_edges),
        "total_source_edges":len(edges),"queue_remaining":len(queue),
        "existing_intersections":intersections,"cycle_edges":cycles,
        "root_verified":False}}
    write(state,{"root":list(root),"queue":list(queue),"seen_nodes":list(seen_nodes),
                 "seen_edges":sorted(seen_edges),"processed":len(seen_edges),
                 "total":len(edges),"complete":not queue})
    return result
def main():
    p=argparse.ArgumentParser()
    p.add_argument("kmz",nargs="+",type=Path)
    p.add_argument("--state",default="data/illinois_graph_state.json")
    p.add_argument("--output",default="local/illinois_graph_batch.geojson")
    p.add_argument("--existing-ids",default="data/existing_reach_ids.txt")
    p.add_argument("--limit",type=int,default=1000)
    p.add_argument("--mouth",nargs=2,type=float,default=MOUTH)
    p.add_argument("--bbox",nargs=4,type=float,default=BBOX)
    a=p.parse_args()
    if a.limit<1:p.error("limit must be positive")
    edges,adj=graph_from_kmz(a.kmz,a.bbox)
    existing=set(Path(a.existing_ids).read_text().split()) if Path(a.existing_ids).exists() else set()
    result=traverse(edges,adj,a.mouth,a.limit,a.state,existing)
    write(a.output,result)
    print(json.dumps(result["metadata"],indent=2))
if __name__=="__main__":main()
