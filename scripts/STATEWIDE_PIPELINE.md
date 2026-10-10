# Statewide directed-river pipeline (experimental)

**Do not publish EDNA as directed hydrography.** The current statewide EDNA
export has 31,325 gauge-associated segments, but no verified direction or
reliable river identity. Its large connected component also contains cycles.
The existing map continues to use `data/river_segments.geojson`.

## Data provenance and prerequisites

Use **authoritative directed flowlines** from USGS 3DHP or NHDPlus HR.
Confirm the exact downloaded layer's **geometry coordinate order** is
upstream-to-downstream in the source documentation or from its network
attributes. Some NHD layers contain digitized geometries that are not
downstream-oriented; do **not** simply rename an EDNA file or blindly set
`--confirm-downstream-geometry`.

USGS access:
- https://www.usgs.gov/3d-hydrography-program/access-3dhp-data-products
- https://www.usgs.gov/national-hydrography/access-national-hydrography-products
- https://www.usgs.gov/data/network-attributes-high-resolution-national-hydrography-dataset-nhd-based-initial-3d

Acquire the full connected drainage basins crossing Illinois; a state boundary
clip alone can create false outlets. Include Lake Michigan tributaries and
Mississippi drainage, and review engineered Chicago diversions separately.

## Scripts

1. `scripts/audit_river_topology.py`: undirected EDNA connectivity audit.
2. `scripts/orient_river_outlets.py`: orient *acyclic* EDNA components only
   when an exact verified outlet endpoint is supplied. It does **not** orient
   the giant cyclic component, and its partial output is **not** publishable.
3. `scripts/prepare_authoritative_rivers.py`: given verified downstream-
   oriented authoritative GeoJSON, derive directed junctions, apply
   established names, and run the one-river-per-segment identity algorithm.
   Reject cycles and divergences component by component.
4. `scripts/attach_stage_gauges.py`: transfer EDNA gauge associations for
   coloring only, using a 100-meter maximum separation. This does not change
   names or directions.

## Processing commands

Run from repository root after obtaining and validating an authoritative
GeoJSON file:

```bash
python3 -m pip install shapely
python3 -m unittest discover -s scripts -p 'test_*.py' -v

python3 scripts/audit_river_topology.py \
  local/illinois_river_segments.geojson

python3 scripts/prepare_authoritative_rivers.py \
  local/authoritative_downstream_flowlines.geojson \
  --confirm-downstream-geometry \
  --output local/authoritative_named_rivers.geojson

python3 scripts/attach_stage_gauges.py \
  local/authoritative_named_rivers.geojson \
  --gauges-network local/illinois_river_segments.geojson \
  --output local/named_rivers_with_stage.geojson
```

Inspect `metadata.rejected_components`, coverage and names before publishing.
The scripts deliberately do **not** overwrite `data/river_segments.geojson`.

## Release gates

- Flowline direction corroborated against USGS connectivity attributes.
- No rejected critical river components; all exceptions accounted for.
- Des Plaines/Salt Creek, Fox/Illinois, Chicago River engineered diversions,
  and Lake Michigan tributaries manually checked against trusted references.
- Published coverage, river labels, and gauge stage colors reviewed on map.
- Only then replace the live GeoJSON in a separate reviewed commit.

**Known limitation:** The present source files alone cannot establish true
flow direction. No script can reliably recover engineered reversals from
undirected EDNA geometry and gauge proximity alone.
