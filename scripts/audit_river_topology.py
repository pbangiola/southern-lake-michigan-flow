#!/usr/bin/env python3
"""Audit undirected GeoJSON stream topology without inventing flow direction.

Only line endpoints are junctions. Interior crossings are not assumed connected.
The EDNA builder snaps endpoints on a grid at the bbox midpoint latitude.
"""
import argparse
import collections
import json
import math
from pathlib import Path


def audit(data, snap_m=15.0):
    features = data['features']
    bbox = data.get('metadata', {}).get('bbox')
    if not bbox:
        raise ValueError('Input metadata must contain bbox to reproduce the builder projection')
    latitude = (bbox[1] + bbox[3]) / 2
    scale_x = 111.2 * math.cos(math.radians(latitude)) * 1000 / snap_m
    scale_y = 111.2 * 1000 / snap_m

    def node(xy):
        return (round(xy[0] * scale_x), round(xy[1] * scale_y))

    adjacency = collections.defaultdict(list)
    invalid = []
    loops = 0
    for index, feature in enumerate(features):
        geom = feature.get('geometry') or {}
        coords = geom.get('coordinates') or []
        if geom.get('type') != 'LineString' or len(coords) < 2:
            invalid.append(index)
            continue
        a, b = node(coords[0]), node(coords[-1])
        if a == b:
            loops += 1
        adjacency[a].append(index)
        adjacency[b].append(index)

    degree_counts = collections.Counter(len(edges) for edges in adjacency.values())
    visited = set()
    components = []
    for root in adjacency:
        if root in visited:
            continue
        stack = [root]
        visited.add(root)
        nodes = 0
        edges = set()
        while stack:
            u = stack.pop()
            nodes += 1
            edges.update(adjacency[u])
            for edge in adjacency[u]:
                geom = features[edge]['geometry']['coordinates']
                for endpoint in (node(geom[0]), node(geom[-1])):
                    if endpoint not in visited:
                        visited.add(endpoint)
                        stack.append(endpoint)
        components.append({'nodes': nodes, 'segments': len(edges)})
    components.sort(key=lambda x: x['segments'], reverse=True)
    return {
        'input_segments': len(features),
        'valid_segments': len(features)-len(invalid),
        'invalid_feature_indices': invalid[:100],
        'self_loop_segments': loops,
        'snapped_nodes': len(adjacency),
        'degree_distribution': {str(k): v for k, v in sorted(degree_counts.items())},
        'degree_one_nodes_potential_headwaters_or_outlets': degree_counts[1],
        'degree_three_plus_nodes_potential_junctions': sum(v for k, v in degree_counts.items() if k >= 3),
        'connected_components': len(components),
        'largest_components': components[:20],
        'note': 'Undirected endpoint topology only. Degree-one nodes may be headwaters, outlets, clipping artifacts or missing links. Neither direction nor established river names are inferred.'
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--output', type=Path, default=Path('local/river_topology_audit.json'))
    args = p.parse_args()
    data = json.loads(args.input.read_text())
    result = audit(data, float(data.get('metadata', {}).get('endpoint_snap_m', 15)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
