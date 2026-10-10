#!/usr/bin/env python3
"""Convert authoritative downstream-oriented hydrographic flowlines into river IDs.

Input: GeoJSON flowlines whose coordinate order is explicitly documented as
upstream-to-downstream. No EDNA/gauge-derived direction is assumed.
Input name properties: GNIS_Name, gnis_name, GNIS_NAME, or name.
Unresolved branches and cycles are reported, never silently given identities.
"""
import argparse
import collections
import json
import math
from pathlib import Path
from assign_river_identity import assign


def snap(point, latitude, meters):
    return (round(point[0]*111200*math.cos(math.radians(latitude))/meters),
            round(point[1]*111200/meters))


def prepare(data, snap_m=5):
    bbox = data.get('bbox')
    if not bbox:
        coords = [xy for f in data['features'] for xy in (f['geometry']['coordinates'][0],f['geometry']['coordinates'][-1])]
        latitude = (min(x[1] for x in coords)+max(x[1] for x in coords))/2
    else:
        latitude = (bbox[1]+bbox[3])/2
    features = []
    for i, f in enumerate(data['features']):
        geom = f.get('geometry') or {}
        if geom.get('type') != 'LineString' or len(geom.get('coordinates', [])) < 2:
            continue
        p = dict(f.get('properties') or {})
        a = snap(geom['coordinates'][0], latitude, snap_m)
        b = snap(geom['coordinates'][-1], latitude, snap_m)
        if a == b:
            continue
        p['from_node'] = f'{a[0]}:{a[1]}'
        p['to_node'] = f'{b[0]}:{b[1]}'
        p['established_name'] = next((str(p[k]).strip() for k in ('GNIS_Name','gnis_name','GNIS_NAME','name') if p.get(k)), '')
        features.append({'type':'Feature','geometry':geom,'properties':p})
    return features


def components(features):
    """Return edge-index groups connected by endpoints, for isolated validation."""
    incident = collections.defaultdict(list)
    for i, f in enumerate(features):
        p=f['properties']
        incident[p['from_node']].append(i)
        incident[p['to_node']].append(i)
    seen=set()
    for i in range(len(features)):
        if i in seen:continue
        todo=[i]
        seen.add(i)
        group=[]
        while todo:
            j=todo.pop()
            group.append(j)
            p=features[j]['properties']
            for node in (p['from_node'],p['to_node']):
                for k in incident[node]:
                    if k not in seen:
                        seen.add(k)
                        todo.append(k)
        yield group


def run(data, snap_m=5):
    features=prepare(data,snap_m)
    accepted=[]
    rejected=[]
    for group in components(features):
        subset=[features[i] for i in group]
        try:
            assign(subset)
        except ValueError as exc:
            rejected.append({'segments':len(group),'reason':str(exc),
                             'sample_segment_ids':[features[i]['properties'].get('segment_id',i) for i in group[:5]]})
            continue
        # Assign returns per-component IDs starting at 1. Make globally unique.
        prefix=f'component-{len(accepted)+1:06d}-'
        for f in subset:
            p=f['properties']
            p['river_id']=prefix+p['river_id']
            if p['filter_river'].startswith('river-'):
                p['filter_river']=p['river_id']
        accepted.extend(subset)
    result={'type':'FeatureCollection','metadata':{
        'direction_source':'authoritative upstream-to-downstream coordinate order (required input contract)',
        'input_segments':len(features),'accepted_segments':len(accepted),
        'rejected_segments':sum(x['segments'] for x in rejected),
        'rejected_components':rejected,
        'note':'Do not feed EDNA stream geometry without independently verified direction.'
    },'features':accepted}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path,help='Authoritative downstream-oriented GeoJSON')
    p.add_argument('--output',type=Path,default=Path('local/authoritative_named_rivers.geojson'))
    p.add_argument('--snap-m',type=float,default=5)
    p.add_argument('--confirm-downstream-geometry',action='store_true',
                   help='Explicit acknowledgement that input geometry is downstream-oriented')
    args=p.parse_args()
    if not args.confirm_downstream_geometry:
        p.error('Refusing to infer flow direction: pass --confirm-downstream-geometry only for documented downstream-oriented data')
    if args.snap_m<=0:p.error('--snap-m must be positive')
    result=run(json.loads(args.input.read_text()),args.snap_m)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,separators=(',',':')))
    print(json.dumps({k:v for k,v in result['metadata'].items() if k!='rejected_components'},indent=2))
    if result['metadata']['rejected_segments']:
        print('WARNING: Some components rejected; see metadata.rejected_components')


if __name__=='__main__':main()
