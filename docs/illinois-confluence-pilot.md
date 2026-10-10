# Illinois River confluence pilot

Start at the **Illinois River–Mississippi River confluence near Grafton, Illinois**. This is the downstream endpoint of the Illinois River basin, **not** the mouth of the Mississippi or an ocean outlet.

## Required source inputs
- Directed reaches with stable `reach_id` and `downstream_id` (GeoJSON).
- A verified reach ID on the Illinois River immediately upstream of its junction with the Mississippi.
- An exact-ID inventory of already published watershed reaches. Geographic proximity or overlapping bounding boxes do not establish that two reaches are identical.

## Execution
```bash
python scripts/traverse_upstream.py \
  --network data/directed_reaches.geojson \
  --start-reach VERIFIED_ILLINOIS_CONFLUENCE_REACH_ID \
  --stop-ids data/existing_reach_ids.txt \
  --state data/illinois_pilot_state.json \
  --output local/illinois_pilot_batch.geojson \
  --limit 1000
```

Each run expands upstream through verified directed links. At an existing mapped reach ID, it records the intersection and does not traverse further along that branch. Other branches continue. Review intersections for source/version compatibility before declaring that branch complete.

**Not yet executable in GitHub Actions:** neither the national directed network nor the verified confluence reach ID and existing-reach ID inventory is currently available in the repository. Do not substitute the nearest line or fabricate downstream direction.
