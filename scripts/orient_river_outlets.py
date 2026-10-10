#!/usr/bin/env python3
"""Orient undirected river segments toward *verified* outlet coordinates.

Conservative: only tree components with exactly one supplied outlet are oriented.
Cycles, missing outlets, multiple outlets, and ambiguous geometry remain untouched.
Outlet coordinates must come from independently checked hydrography, not gauge names.
"""
import argparse
import collections
import json
import math
from pathlib import Path


def key(xy, lat, snap_m):
    return (round(xy[0] * 111200 * math.cos(math.radians(lat)) / snap_m),
            round(xy[1] * 111200 / snap_m))


def orient(data, outlets):
    bounds = data.get('metadata', {}).get('bbox')
    if not bounds:
        raise ValueError('Missing bbox metadata; cannot reproduce snapping grid')
    lat = (bounds[1] + bounds[3]) / 2
    snap = float(data.get('metadata', {}).get('endpoint_snap_m', 15))
    features = data['features']
    adjacency = collections.defaultdict(list)
    endpoints = {}
    for i, feature in enumerate(features):
        coords = feature['geometry']['coordinates']
        if feature['geometry']['type'] != 'LineString' or len(coords) < 2:
            continue
        u, v = key(coords[0], lat, snap), key(coords[-1], lat, snap)
        endpoints[i] = (u, v)
        adjacency[u].append(i)
        adjacency[v].append(i)
    outlet_nodes = {key(x, lat, snap) for x in outlets}
    unknown = outlet_nodes - set(adjacency)
    if unknown:
        raise ValueError(f'{len(unknown)} outlet coordinates do not match any snapped endpoint')
    visited = set()
    oriented = 0
    summary = collections.Counter()
    for root in adjacency:
        if root in visited:
            continue
        stack = [root]
        nodes = set()
        edges = set()
        visited.add(root)
        while stack:
            u = stack.pop()
            nodes.add(u)
            for i in adjacency[u]:
                edges.add(i)
                for v in endpoints[i]:
                    if v not in visited:
                        visited.add(v)
                        stack.append(v)
        anchors = nodes & outlet_nodes
        if len(anchors) != 1:
            summary['missing_outlet' if not anchors else 'multiple_outlets'] += 1
            continue
        if len(edges) != len(nodes) - 1:
            summary['cycles_or_parallel_edges'] += 1
            continue
        outlet = next(iter(anchors))
        # BFS outward from outlet: every edge points toward its visited parent.
        queue = collections.deque([outlet])
        seen = {outlet}
        while queue:
            downstream = queue.popleft()
            for i in adjacency[downstream]:
                a, b = endpoints[i]
                upstream = b if a == downstream else a
                if upstream in seen:
                    continue
                seen.add(upstream)
                queue.append(upstream)
                p = features[i].setdefault('properties', {})
                p['from_node'] = f'{upstream[0]}:{upstream[1]}'
                p['to_node'] = f'{downstream[0]}:{downstream[1]}'
                p['direction_method'] = 'verified_outlet_tree'
                # Geometry coordinates are deliberately not reversed.
                oriented += 1
        summary['oriented_tree_components'] += 1
    summary['oriented_segments'] = oriented
    summary['unoriented_segments'] = len(features) - oriented
    data.setdefault('metadata', {})['direction_method'] = 'verified outlet propagation; cyclic or unanchored components withheld'
    return dict(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--outlets', type=Path, required=True,
                        help='JSON array of [longitude,latitude] verified stream endpoint coordinates')
    parser.add_argument('--output', type=Path, default=Path('local/river_segments_partially_directed.geojson'))
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    outlets = json.loads(args.outlets.read_text())
    result = orient(data, outlets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, separators=(',', ':')))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
