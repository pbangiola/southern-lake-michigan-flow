# River crawler — draft implementation
This is a nonpublishing discovery pipeline. Run the workflow manually on the draft branch; inspect its candidate artifact before merging into data/. Scheduled execution, persisted queue state, provenance review and validation gates are still required.

## Geographic coverage
Use the existing USGS 3DHP network, including Illinois and neighboring states. State boundaries are not river boundaries. Keep imported non-Illinois reaches and gauge metadata with original provenance. The current script walks the *published review sample*; it is not yet a complete statewide or cross-state graph traversal.

## Coloring
Two distinct network-bounding gauges should be preferred. Interpolate normalized stage colors by along-network fraction. If a boundary lacks a usable reading, use the other; if neither does, gray. A nearest associated gauge is a fallback, not evidence of a bounded reach. Do not interpolate raw gauge-height feet between different local datums.

## Low-water thresholds
Observed 12-month minima, official low-water navigation guidance, and crowdsourced navigability reports are separate fields. Flood stage alone does not establish navigable depth. Reject insufficient historical coverage.

## Candidate validation
Check geometry validity, deduplication, gauge-to-reach snapping, network connectivity, station freshness, OSM access tags, private land, and cross-state topology before publishing. No new live map layer is created by this draft.
