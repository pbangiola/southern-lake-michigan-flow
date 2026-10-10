#!/usr/bin/env python3
"""Test radial scale error in NOAA-to-EDNA nearest-point offsets."""
import csv,json,math
from pathlib import Path
import numpy as np
from pyproj import Geod,Transformer

ROOT=Path("data/gauge_match_audit")
CENTER=(-98.0,39.0)
# Local metric azimuthal equidistant projection centered on CONUS.
PROJ="+proj=aeqd +lat_0=39 +lon_0=-98 +datum=WGS84 +units=m +type=crs"
T=Transformer.from_crs("EPSG:4326",PROJ,always_xy=True)
def fit(x,y):
    # Regression y = intercept + slope*x, report slope, R², robust median bin statistics.
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
    A=np.column_stack((np.ones(len(x)),x))
    coef=np.linalg.lstsq(A,y,rcond=None)[0]
    pred=A@coef
    den=np.sum((y-y.mean())**2)
    return {"intercept_m":round(float(coef[0]),3),"scale_error_fraction":round(float(coef[1]),8),"scale_error_percent":round(float(coef[1])*100,5),"r_squared":round(float(1-np.sum((y-pred)**2)/den),5) if den else None}
def main():
    rows=[]
    with (ROOT/"matches.csv").open() as f:
        for r in csv.DictReader(f):
            if not r.get("river_lon") or not r.get("river_lat"):continue
            if float(r["nearest_m"])>1000:continue
            gx,gy=T.transform(float(r["lon"]),float(r["lat"]))
            rx,ry=T.transform(float(r["river_lon"]),float(r["river_lat"]))
            d=np.array([rx-gx,ry-gy]);v=np.array([gx,gy]);radius=float(np.linalg.norm(v))
            radial=float(np.dot(d,v)/radius) if radius else 0
            tangential=float((v[0]*d[1]-v[1]*d[0])/radius) if radius else 0
            rows.append({"noaa_lid":r["noaa_lid"],"state":r.get("state",""),"radius_from_center_km":round(radius/1000,2),"radial_river_minus_gauge_m":round(radial,3),"tangential_m":round(tangential,3),"nearest_m":r["nearest_m"],"gauge_x_m":gx,"gauge_y_m":gy,"river_x_m":rx,"river_y_m":ry})
    if not rows:raise RuntimeError("No usable gauge/river matches")
    x=[r["radius_from_center_km"]*1000 for r in rows];y=[r["radial_river_minus_gauge_m"] for r in rows]
    bins=[]
    for a,b in [(0,250),(250,500),(500,750),(750,1000),(1000,1250),(1250,1500),(1500,2000),(2000,3000),(3000,6000)]:
        sub=[r for r in rows if a<=r["radius_from_center_km"]<b]
        if not sub:continue
        bins.append({"radius_km":[a,b],"n":len(sub),"median_radial_offset_m":round(float(np.median([r["radial_river_minus_gauge_m"] for r in sub])),2),"mean_radial_offset_m":round(float(np.mean([r["radial_river_minus_gauge_m"] for r in sub])),2),"median_absolute_offset_m":round(float(np.median([abs(r["radial_river_minus_gauge_m"]) for r in sub])),2)})
    # Directional scale: regress x-offset on x-position and y-offset on y-position.
    xs=[r["gauge_x_m"] for r in rows];ys=[r["gauge_y_m"] for r in rows]
    dx=[r["river_x_m"]-r["gauge_x_m"] for r in rows];dy=[r["river_y_m"]-r["gauge_y_m"] for r in rows]
    summary={"center_lon_lat":CENTER,"included_gauges":len(rows),"inclusion":"nearest EDNA river within 1000 m","radial_fit":fit(x,y),"east_west_fit":fit(xs,dx),"north_south_fit":fit(ys,dy),"radial_bins":bins,"caution":"Nearest-point offsets can be perpendicular to rivers and biased by missing river segments; regression tests scale consistency but is not a definitive geodetic calibration."}
    (ROOT/"scale_test_summary.json").write_text(json.dumps(summary,indent=2))
    with (ROOT/"scale_test_points.csv").open("w",newline="") as f:
        fields=["noaa_lid","state","radius_from_center_km","radial_river_minus_gauge_m","tangential_m","nearest_m"]
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:w.writerow({k:r[k] for k in fields})
    print(json.dumps(summary,indent=2),flush=True)
if __name__=="__main__":main()
