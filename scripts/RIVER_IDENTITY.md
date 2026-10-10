# River identity algorithm

This implements the requested **one river identity per segment** convention, without conflating river identity and gauge proximity.

## Algorithm

A directed stream graph has nodes (junctions) and reaches (edges). At a headwater, a new river identity starts. At degree-two nodes, the identity continues. At a confluence, the incoming river with the longest cumulative upstream course continues, unless the downstream reach has an established name. If an established downstream name matches an incoming river, that incoming river continues; if the name is new (e.g. Ohio River), a new identity begins. The other incoming river identities end at the junction. An unnamed reach inherits its winning upstream identity. Names are propagated to all reaches sharing the same identity.

The script writes exactly one `river_id` and `river_name` per segment, plus `filter_river` for the existing map UI. Gauge fields are not modified.

## Required input

`scripts/assign_river_identity.py` accepts a GeoJSON FeatureCollection of **directed reaches** with properties:
- `from_node`: upstream junction identifier
- `to_node`: downstream junction identifier
- `established_name`: optional known human river name

The existing `data/river_segments.geojson` **does not meet this requirement**. Its `from_gauge`/`to_gauge` fields represent nearest-gauge ownership, NOT upstream/downstream topology, and must not be used as directed nodes. The existing EDNA builder explicitly states `flow_direction_verified: false`.

Obtain directed flowlines and junctions from a hydrographic network with known flow direction (e.g. NHDPlus HR / 3DHP). Map established waterway names onto those reaches. Where the source is bidirectional or has an engineered reversal, resolve direction before running this algorithm. Branching/divergent reaches and cycles are rejected rather than silently misidentified. No stage or navigability information is inferred.

## Commands

From repository root:

```bash
git pull origin main
python3 -m unittest discover -s scripts -p 'test_assign_river_identity.py' -v
# AFTER producing a directed network with from_node/to_node and established_name:
python3 scripts/assign_river_identity.py local/directed_reaches.geojson --output data/river_segments.geojson
git add data/river_segments.geojson
git commit -m "Publish river identities from directed network"
git push origin main
```

**Do not run the third command against the current river_segments.geojson**: it will reject it, by design. This commit implements and tests the naming algorithm, not the missing directed hydrography data acquisition and topology conversion. The live map will remain unchanged until that input pipeline exists and the resulting GeoJSON is published.

### Caveat
Longest cumulative *single upstream course* is a proxy for perceived river size. Drainage area or discharge may be a better tie-breaker; explicit established downstream names override it. Waterway names and channel flow direction in the Chicago engineered system require special attention.
