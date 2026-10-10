# Outlet-to-headwater traversal

The target algorithm is **graph traversal, not geographic grid crawling**.

1. Import the existing nationwide hydrography once, preserving stable reach IDs, directed downstream links, and watershed IDs. The source file is currently on an inaccessible local computer and **has not been imported into this repository**.
2. Identify verified outlets at oceans and Great Lakes, using source topology. Do not assume an arbitrary line endpoint or a river near a shoreline is an outlet.
3. Build a reverse adjacency index from each downstream reach to its immediately upstream reaches.
4. Traverse each connected network breadth-first, checkpointing processed reach IDs and the remaining queue. Handle inland terminal basins and disconnected components separately.
5. For each reached segment, look up NOAA forecast stations, then USGS observations as supplementary data, and launch candidates. Deduplicate by source IDs and attach evidence and network position.
6. Use two **verified** bounding gauges for reach coloring when available. Otherwise use the single associated gauge, explicitly marked as inferred. Gauge datum heights cannot be interpolated directly.
7. Publish only verified geometries and evidence; maintain provenance and confidence levels. Continue until every directed reach has been accounted for, including closed inland basins.

The initial implementation in `scripts/traverse_upstream.py` handles steps 2–4 **only when** `data/directed_reaches.geojson` exists and contains `reach_id`, `downstream_id`, and `terminal_type` on true terminal reaches. Its GitHub Action is intentionally a no-op until the authoritative network is available. It does **not** generate a nationwide network, discover NOAA stations, or publish traversed reaches to the map yet.

The separate scheduled geographic candidate crawler is not a substitute for this directed-network approach.
