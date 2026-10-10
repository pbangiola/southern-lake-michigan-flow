#!/usr/bin/env python3
"""Infer ONE continuous river identity per segment from a directed tree of reaches.

Input reaches MUST carry from_node/to_node in upstream->downstream order,
and optional established_name. At confluences, the longest cumulative
upstream path continues, unless established_name changes downstream.
No assumption is made that gauge proximity establishes a river name.

This deliberately refuses undirected EDNA geometry: an endpoint's degree
cannot establish flow direction, and guessed direction would corrupt names.
"""
import argparse
import collections
import json
import math
from pathlib import Path

def length_km(coords):
    total = 0.0
    for (x,y), (xx,yy) in zip(coords,coords[1:]):
        total += math.hypot((xx-x)*111.2*math.cos(math.radians((y+yy)/2)),(yy-y)*111.2)
    return total

def assign(features):
    incoming=collections.defaultdict(list)
    outgoing=collections.defaultdict(list)
    for i,f in enumerate(features):
        p=f.get('properties') or {}
        u,v=p.get('from_node'),p.get('to_node')
        if u is None or v is None or u==v:
            raise ValueError(f'Reach {i}: requires distinct directed from_node/to_node')
        incoming[v].append(i)
        outgoing[u].append(i)
    if any(len(v)>1 for v in outgoing.values()):
        raise ValueError('Divergences found: resolve directed branches before naming')
    indegree={n:len(incoming[n]) for n in set(incoming)|set(outgoing)}
    q=collections.deque(n for n in indegree if indegree[n]==0)
    processed=0
    best_length={}
    identity={}
    names={}
    counter=0
    while q:
        node=q.popleft()
        parents=incoming[node]
        # Continue the longest upstream river, not the longest individual reach.
        winner=max(parents,key=lambda i:(best_length[i],-i)) if parents else None
        for i in outgoing[node]:
            f=features[i];p=f['properties']
            explicit=str(p.get('established_name') or '').strip()
            inherited=identity.get(winner)
            parent_name=names.get(inherited,'') if inherited else ''
            if explicit and explicit.casefold()!=parent_name.casefold():
                # A new established downstream name begins a new river.
                inherited=None
            if inherited is None:
                counter+=1
                inherited=f'river-{counter:06d}'
            identity[i]=inherited
            if explicit:names[inherited]=explicit
            names.setdefault(inherited,'')
            best_length[i]=(best_length[winner] if winner is not None else 0)+length_km(f['geometry']['coordinates'])
            p['river_id']=inherited
            p['river_name']=names[inherited] or 'Unidentified waterway'
            p['filter_river']=p['river_name'] if names[inherited] else inherited
        processed+=1
        for i in outgoing[node]:
            downstream=features[i]['properties']['to_node']
            indegree[downstream]-=1
            if indegree[downstream]==0:q.append(downstream)
    if processed!=len(indegree):
        raise ValueError('Cycle in directed network; resolve it before naming')
    # Propagate an established name upstream within the same river identity.
    for f in features:
        p=f['properties']
        p['river_name']=names[p['river_id']] or 'Unidentified waterway'
        p['filter_river']=p['river_name'] if names[p['river_id']] else p['river_id']
    return len(names)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path,help='Directed GeoJSON with from_node/to_node and optional established_name')
    parser.add_argument('--output',type=Path,default=Path('data/river_segments_named.geojson'))
    args=parser.parse_args()
    data=json.loads(args.input.read_text())
    if data.get('type')!='FeatureCollection':parser.error('Expected FeatureCollection')
    count=assign(data['features'])
    data.setdefault('metadata',{})['identity_method']='directed longest-upstream-path continuity with established-name overrides'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,separators=(',',':')))
    print(f'Assigned {count} river identities to {len(data["features"])} directed reaches: {args.output}')

if __name__=='__main__':main()
