#!/usr/bin/env python3
"""Audit NOAA gauge proximity to EDNA lines; proximity is NOT hydrological validation."""
import csv, json, math, sqlite3
from decimal import Decimal
from pathlib import Path
import ijson
from shapely.geometry import shape, Point
from shapely.ops import nearest_points
from pyproj import Geod

ROOT=Path("data/edna_watersheds")
OUT=Path("data/gauge_match_audit")
GEOD=Geod(ellps="WGS84")
RADII=(25,50,100,250,500,1000,2000,5000,10000)
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/"manifest.json").read_text())
    assert manifest["complete"]
    db=sqlite3.connect(str(OUT/"spatial_index.sqlite"))
    db.execute("DROP TABLE IF EXISTS metadata"); db.execute("DROP TABLE IF EXISTS segments")
    db.execute("CREATE VIRTUAL TABLE segments USING rtree(id,minx,maxx,miny,maxy)")
    db.execute("CREATE TABLE metadata(id INTEGER PRIMARY KEY, segment_id TEXT, source TEXT, geometry TEXT)")
    index=0
    for src in manifest["sources"]:
        if not src.get("features"):continue
        with open(src["file"],"rb") as f:
            for feature in ijson.items(f,"features.item"):
                geom=shape(feature["geometry"])
                if geom.is_empty:continue
                index+=1
                minx,miny,maxx,maxy=geom.bounds
                db.execute("INSERT INTO segments VALUES (?,?,?,?,?)",(index,minx,maxx,miny,maxy))
                db.execute("INSERT INTO metadata VALUES (?,?,?,?)",(index,feature.get("properties",{}).get("segment_id",""),src["name"],json.dumps(feature["geometry"],separators=(",",":"),default=float)))
        db.commit()
        print("Indexed",src["name"],"total",index,flush=True)
    counts={str(x):0 for x in RADII}
    rows=[]
    with open("data/noaa_gauges.geojson","rb") as f:
        for feature in ijson.items(f,"features.item"):
            p=feature.get("properties") or {}
            coords=(feature.get("geometry") or {}).get("coordinates")
            lid=p.get("noaa_lid")
            if not coords or len(coords)<2:continue
            lon,lat=map(float,coords[:2])
            if not all(isinstance(v,(float,int)) and math.isfinite(v) for v in (lon,lat)):continue
            point=Point(lon,lat)
            # Expand until candidates are available; nearest is then selected geodesically.
            best=None
            for radius in (25,50,100,250,500,1000,2000,5000,10000):
                dy=radius/110574
                dx=radius/(111320*max(.1,abs(math.cos(math.radians(lat)))))
                candidates=db.execute("SELECT m.segment_id,m.source,m.geometry FROM segments s JOIN metadata m ON m.id=s.id WHERE s.minx<=? AND s.maxx>=? AND s.miny<=? AND s.maxy>=?",(lon+dx,lon-dx,lat+dy,lat-dy)).fetchall()
                for segment_id,source,geo in candidates:
                    near=nearest_points(point,shape(json.loads(geo)))[1]
                    distance=GEOD.inv(lon,lat,near.x,near.y)[2]
                    if best is None or distance<best[0]:best=(distance,segment_id,source,float(near.x),float(near.y))
                if best and best[0]<=radius:break
            dist=round(best[0],1) if best else None
            azimuth,_,_=GEOD.inv(lon,lat,best[3],best[4]) if best else (None,None,None)
            east_m=round(best[0]*math.sin(math.radians(azimuth)),1) if best else None
            north_m=round(best[0]*math.cos(math.radians(azimuth)),1) if best else None
            for threshold in RADII:
                if dist is not None and dist<=threshold:counts[str(threshold)]+=1
            rows.append({"noaa_lid":lid,"name":p.get("name"),"state":p.get("state"),"lon":lon,"lat":lat,"nearest_m":dist,"river_lon":best[3] if best else None,"river_lat":best[4] if best else None,"river_east_of_gauge_m":east_m,"river_north_of_gauge_m":north_m,"edna_segment_id":best[1] if best else "","edna_source":best[2] if best else "","has_stage":p.get("stage") is not None,"has_flood_stage":p.get("flood_stage_ft") is not None,"has_low_stage":p.get("low_water_stage_ft") is not None})
    db.close()
    (OUT/"spatial_index.sqlite").unlink(missing_ok=True)
    with (OUT/"matches.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    directional=[r for r in rows if r["nearest_m"] is not None and r["nearest_m"]<=1000]
    directional.sort(key=lambda r:r["river_east_of_gauge_m"])
    east=[r["river_east_of_gauge_m"] for r in directional]
    north=sorted(r["river_north_of_gauge_m"] for r in directional)
    directional_summary={"gauges_within_1km":len(directional),"mean_river_east_of_gauge_m":round(sum(east)/len(east),1) if east else None,"mean_river_north_of_gauge_m":round(sum(north)/len(north),1) if north else None,"median_river_east_of_gauge_m":east[len(east)//2] if east else None,"median_river_north_of_gauge_m":north[len(north)//2] if north else None,"river_east_of_gauge_count":sum(x>0 for x in east),"river_west_of_gauge_count":sum(x<0 for x in east)}
    summary={"directional_offsets":directional_summary,"total_edna_segments":index,"gauges_with_valid_coordinates":len(rows),"within_meters":counts,"with_current_stage":sum(r["has_stage"] for r in rows),"with_flood_stage":sum(r["has_flood_stage"] for r in rows),"with_low_stage":sum(r["has_low_stage"] for r in rows),"note":"50 m diameter gauge circle overlaps a river iff nearest distance <=25 m. This is exact continuous-geometry overlap (no bitmap aliasing). Nearest geometric feature only; no river-name or connectivity validation."}
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2),flush=True)
if __name__=="__main__":main()
