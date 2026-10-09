#!/usr/bin/env python3
"""Consolidate USGS bulk exports from ~/Downloads and audit annual gage-height minima.

Run from the atlas repository:
  python3 consolidate_usgs.py
  python3 consolidate_usgs.py --fill  # fetch missing daily values, then targeted instantaneous fallback
No third-party dependencies. Input files are never modified.
"""
import argparse, csv, io, json, re, sys, time, zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SITE_RE = re.compile(r'(?:USGS-)?(\d{8,15})$')
SITE_IN_NAME = re.compile(r'(?<!\d)(\d{8,15})(?!\d)')
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def site_id(s):
    m = SITE_RE.fullmatch(str(s).strip())
    return m.group(1) if m else None


def day(s):
    s = str(s or '').strip()
    m = DATE_RE.search(s)
    if not m:
        return None
    try:
        # Normalize timestamped observations to UTC before grouping by day.
        # Date-only USGS published daily statistics retain their published date.
        if 'T' in s or re.search(r'\\d{2}:\\d{2}', s):
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).date()
        return date.fromisoformat(m.group())
    except ValueError:
        return None


def number(s):
    try:
        v = float(str(s).strip())
        return v if -1000 < v < 10000 and v == v else None
    except (ValueError, TypeError):
        return None


def classify(header):
    h = str(header).strip().lower().replace(' ', '_')
    if h in ('monitoring_location_id','site_no','site_number','site_id','site','location_id'):
        return 'site'
    if h in ('time','datetime','date','date_time','observation_time'):
        return 'date'
    if h in ('value','result','result_value','observed_value','daily_value'):
        return 'value'
    if h in ('parameter_code','parameter_cd','parameter'):
        return 'parameter'
    if h in ('statistic_id','statistic_code','stat_cd','statistic_cd'):
        return 'stat'
    if h in ('approval_status','qualifier','qualifiers'):
        return 'qualifier'
    # Legacy NWIS RDB: 12345_00065_00002 or 12345_00065
    if re.search(r'(?:^|_)00065(?:_|$)', h):
        if h.endswith('_cd'):
            return 'qualifier'
        return 'minimum' if h.endswith('_00002') else 'instant'
    return None


def extract_rows(text, filename, add, counters):
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith('#')]
    if not lines:
        return
    sep = '\t' if '\t' in lines[0] else ','
    try:
        rows = csv.reader(lines, delimiter=sep)
        headers = next(rows)
    except (csv.Error, StopIteration):
        return
    kinds = [classify(h) for h in headers]
    if 'date' not in kinds:
        return
    ix = lambda k: [i for i, v in enumerate(kinds) if v == k]
    sitecols, datecols, valuecols = ix('site'), ix('date'), ix('value')
    parametercols, statcols = ix('parameter'), ix('stat')
    legacycols = ix('minimum') + ix('instant')
    filename_site = (SITE_IN_NAME.search(filename) or [None])[0]
    count = 0
    for cells in rows:
        if len(cells) != len(headers) or (cells and cells[0] in ('5s', '15s', '20d')):
            continue
        sid = next((site_id(cells[i]) for i in sitecols if site_id(cells[i])), None) or filename_site
        d = day(cells[datecols[0]])
        if not sid or not d:
            continue
        if parametercols and str(cells[parametercols[0]]).strip().zfill(5) != '00065':
            continue
        if statcols and str(cells[statcols[0]]).strip().zfill(5) not in ('00002', '00011'):
            continue
        if legacycols:
            candidates = [(i, 'daily' if kinds[i] == 'minimum' else 'instant') for i in legacycols]
        else:
            candidates = [(i, 'daily' if statcols and str(cells[statcols[0]]).strip().zfill(5) == '00002' else 'instant') for i in valuecols]
        for i, kind in candidates:
            v = number(cells[i])
            if v is not None:
                add(sid, d, v, kind)
                count += 1
    if count:
        counters[filename] = count


def parse_geojson(text, filename, add, counters):
    try:
        obj = json.loads(text)
    except (ValueError, UnicodeError):
        return
    features = obj.get('features', []) if isinstance(obj, dict) else []
    count = 0
    for f in features:
        p = f.get('properties') or {}
        sid = site_id(p.get('monitoring_location_id') or p.get('site_no') or p.get('site'))
        d = day(p.get('time') or p.get('datetime') or p.get('date'))
        if str(p.get('parameter_code', '00065')).zfill(5) != '00065':
            continue
        stat = str(p.get('statistic_id', '00002')).zfill(5)
        if stat != '00002':
            continue
        v = number(p.get('value'))
        if sid and d and v is not None:
            add(sid, d, v, 'daily')
            count += 1
    if count:
        counters[filename] = count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downloads', type=Path, default=Path.home() / 'Downloads')
    parser.add_argument('--ids', type=Path, default=Path('usgs_gauge_ids.txt'))
    parser.add_argument('--out', type=Path, default=Path('data/stage_minima.json'))
    parser.add_argument('--days', type=int, default=365)
    parser.add_argument('--end', type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument('--fill', action='store_true', help='Fetch daily gaps and targeted instantaneous fallback via USGS; stop on rate limit')
    parser.add_argument('--max-fallback', type=int, default=20, help='Maximum stations for instantaneous fallback per run')
    args = parser.parse_args()
    if args.ids.exists():
        expected = {site_id(line) for line in re.split(r'[\s,]+', args.ids.read_text()) if site_id(line)}
    elif Path('data/gauges.geojson').exists():
        expected = {site_id(f['properties']['site']) for f in json.loads(Path('data/gauges.geojson').read_text())['features']}
    else:
        sys.exit('Missing gauge IDs. Put usgs_gauge_ids.txt beside this script or run inside the atlas repository.')
    start = args.end - timedelta(days=args.days - 1)
    values = defaultdict(lambda: defaultdict(dict))
    daily_sums = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    counters = {}
    def add(sid, d, v, kind):
        if sid not in expected or not start <= d <= args.end:
            return
        # Keep the smallest value for a day, but distinguish published daily minima from instantaneous samples.
        old = values[sid][d].get(kind)
        values[sid][d][kind] = min(old, v) if old is not None else v
        if kind == 'instant':
            daily_sums[sid][d][0] += v
            daily_sums[sid][d][1] += 1

    paths = sorted(args.downloads.iterdir()) if args.downloads.exists() else []
    for path in paths:
        if not path.is_file():
            continue
        try:
            if path.suffix.lower() == '.zip':
                with zipfile.ZipFile(path) as z:
                    for info in z.infolist():
                        if info.is_dir() or info.file_size > 150_000_000 or not info.filename.lower().endswith(('.csv','.tsv','.txt','.rdb','.json','.geojson')):
                            continue
                        content = z.read(info).decode('utf-8-sig', errors='replace')
                        name = path.name + '/' + info.filename
                        (parse_geojson if info.filename.lower().endswith(('.json','.geojson')) else extract_rows)(content, name, add, counters)
            elif path.suffix.lower() in ('.csv','.tsv','.txt','.rdb','.json','.geojson') and path.stat().st_size < 150_000_000:
                content = path.read_text(encoding='utf-8-sig', errors='replace')
                (parse_geojson if path.suffix.lower() in ('.json','.geojson') else extract_rows)(content, path.name, add, counters)
        except (OSError, zipfile.BadZipFile, UnicodeError, csv.Error) as e:
            print('Skipped', path.name, ':', e)

    def quality(sid):
        dates = sorted(d for d, types in values[sid].items() if types)
        # 75% overall, observations in every quarter, and no gap longer than 45 days.
        quarter_counts = [0,0,0,0]
        for d in dates:
            quarter_counts[min(3, (d - start).days * 4 // args.days)] += 1
        gaps = [(b-a).days-1 for a,b in zip([start-timedelta(days=1)] + dates, dates + [args.end+timedelta(days=1)])]
        max_gap = max(gaps, default=args.days)
        enough = len(dates) / args.days >= .75 and all(c >= 20 for c in quarter_counts) and max_gap <= 45
        return enough, len(dates), quarter_counts, max_gap

    def fetch(url):
        for attempt in range(3):
            try:
                req = Request(url, headers={'User-Agent':'SouthernLakeMichiganFlowAtlas/1.0 (data consolidation)'})
                with urlopen(req, timeout=90) as resp:
                    return resp.read().decode('utf-8-sig', errors='replace')
            except HTTPError as e:
                if e.code == 429:
                    raise RuntimeError('USGS returned 429; stopping requests. Run again later (downloads remain intact).')
                if e.code in (400,404):
                    print('  No data / invalid request:', e.code)
                    return ''
                print('  HTTP', e.code, 'attempt', attempt+1)
            except (URLError, TimeoutError) as e:
                print('  Network:', e, 'attempt', attempt+1)
            time.sleep(5 * (attempt+1))
        return ''

    if args.fill:
        missing = [sid for sid in sorted(expected) if not quality(sid)[0]]
        print('Daily coverage insufficient for', len(missing), 'stations; requesting missing daily minima in batches.')
        # Batches prevent per-gauge daily requests.
        for i in range(0, len(missing), 50):
            batch = missing[i:i+50]
            params = {'format':'rdb','sites':','.join(batch),'startDT':start.isoformat(),'endDT':args.end.isoformat(),'parameterCd':'00065','statCd':'00002','siteStatus':'all'}
            try:
                extract_rows(fetch('https://waterservices.usgs.gov/nwis/dv/?'+urlencode(params)), 'online_daily_batch_'+str(i//50+1), add, counters)
            except RuntimeError as e:
                print(e)
                break
            time.sleep(2)
        remaining = [sid for sid in sorted(expected) if not quality(sid)[0]]
        print('Still below daily threshold:', len(remaining))
        # Instantaneous fallback is intentionally bounded: these responses can be enormous.
        for sid in remaining[:args.max_fallback]:
            print('  Instantaneous fallback', sid, flush=True)
            params = {'format':'rdb','sites':sid,'startDT':start.isoformat(),'endDT':args.end.isoformat(),'parameterCd':'00065','siteStatus':'all'}
            try:
                extract_rows(fetch('https://waterservices.usgs.gov/nwis/iv/?'+urlencode(params)), 'online_instant_'+sid, add, counters)
            except RuntimeError as e:
                print(e)
                break
            time.sleep(2)

    stations = {}
    deficient = []
    for sid in sorted(expected):
        adequate, n_daily, quarters, max_gap = quality(sid)
        daily = [v.get('daily',v.get('unknown')) for v in values[sid].values() if 'daily' in v or 'unknown' in v]
        instant = [v['instant'] for v in values[sid].values() if 'instant' in v]
        # Never claim instantaneous samples are published daily minima.
        observed = daily + instant
        dates = sorted(values[sid])
        # Equal weight to each observed day, rather than overweighting days with more samples.
        day_means = [total / count for total, count in daily_sums[sid].values() if count]
        rec = {'minimum_ft': min(observed) if observed else None,
               'mean_stage_12mo_ft':round(sum(day_means)/len(day_means), 3) if day_means else None,
               'mean_observed_days':len(day_means),
               'coverage_days':len(dates), 'coverage_fraction':round(len(dates)/args.days,3),
               'complete_year':len(dates)/args.days >= .95,
               'daily_coverage_days':n_daily,'daily_coverage_fraction':round(n_daily/args.days,3),
               'daily_quarter_counts':quarters,'longest_daily_gap_days':max_gap,
               'daily_adequate_75pct_distributed':adequate and n_daily >= .75 * args.days,
               'observed_adequate_75pct_distributed':adequate,
               'daily_minimum_ft':min(daily) if daily else None,
               'instantaneous_sample_minimum_ft':min(instant) if instant else None,
               'daily_count':sum('daily' in v for v in values[sid].values()),'continuous_count':sum('instant' in v for v in values[sid].values()),
               'first_observation':dates[0].isoformat() if dates else None,
               'last_observation':dates[-1].isoformat() if dates else None}
        stations[sid] = rec
        if not adequate:
            deficient.append(sid)

    output = {'metadata':{'retrieved_at':datetime.now().astimezone().isoformat(),
                          'start_date':start.isoformat(),'end_date':args.end.isoformat(),
                          'method':'Annual minimum from available USGS stage observations; mean is the average of observed daily means from continuous stage readings',
                          'coverage_note':'Adequate observed coverage: >=75% of days, >=20 days in each quarter, longest gap <=45 days; instantaneous samples are not published daily minima.'},
              'stations':stations,'failures':{sid:'Inadequate distributed daily coverage' for sid in deficient}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    tmp=args.out.with_suffix('.tmp')
    tmp.write_text(json.dumps(output,indent=2))
    tmp.replace(args.out)
    report = args.out.with_name('stage_minima_audit.csv')
    with report.open('w',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['site','observed_days','observed_fraction','quarter_counts','longest_observed_gap','observed_adequate','published_daily_days','observed_min_ft','published_daily_min_ft','instant_sample_min_ft'])
        for sid,r in stations.items():
            writer.writerow([sid,r['coverage_days'],r['coverage_fraction'],'/'.join(map(str,r['daily_quarter_counts'])),r['longest_daily_gap_days'],r['observed_adequate_75pct_distributed'],r['daily_count'],r['minimum_ft'],r['daily_minimum_ft'],r['instantaneous_sample_minimum_ft']])
    print('\nParsed',len(counters),'data files:',sum(counters.values()),'records in requested window')
    print('Expected:',len(expected),'| with observations:',sum(bool(values[s]) for s in expected),
          '| adequate observed coverage:',len(expected)-len(deficient),'| needing review:',len(deficient))
    print('Output:',args.out,'| audit:',report)
    if not counters:
        print('WARNING: No supported data files parsed. Check your download format and directory.')
    print('Files read:',', '.join(counters) if counters else '(none)')

if __name__ == '__main__':
    main()