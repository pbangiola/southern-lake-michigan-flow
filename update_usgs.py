#!/usr/bin/env python3
"""Fetch new USGS stage readings since the last atlas update, then rebuild statistics.

Run from repository root:
    python3 update_usgs.py
    python3 update_usgs.py --publish

Requires the original USGS bulk ZIP downloads in ~/Downloads.
No third-party Python packages required.
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent

def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True,
                          text=True, capture_output=True).stdout.strip()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--publish', action='store_true', help='Commit and push refreshed data')
    p.add_argument('--batch-size', type=int, default=10)
    p.add_argument('--delay', type=float, default=2.0)
    p.add_argument('--downloads', type=Path, default=Path.home() / 'Downloads')
    args = p.parse_args()
    if not 1 <= args.batch_size <= 30:
        p.error('--batch-size must be between 1 and 30')
    # Only block changes to files this updater overwrites; unrelated local work is safe.
    protected = {'data/stage_minima.json', 'data/stage_minima_audit.csv'}
    changed = set()
    for line in git('status', '--porcelain', '--untracked-files=all').splitlines():
        if line:
            changed.add(line[3:].strip().strip('"'))
    conflicts = sorted(protected & changed)
    if conflicts:
        sys.exit('Uncommitted changes to updater output files: ' + ', '.join(conflicts) + '. Commit or back up these files before running.')
    git('fetch', 'origin', 'main')
    if git('rev-parse', 'HEAD') != git('rev-parse', 'origin/main'):
        sys.exit('Local HEAD differs from origin/main. Run git pull --ff-only origin main.')
    target = ROOT / 'data/stage_minima.json'
    if not target.exists():
        sys.exit('Missing data/stage_minima.json')
    last = date.fromisoformat(json.loads(target.read_text())['metadata']['end_date'])
    today = date.today()
    start = last + timedelta(days=1)
    print('Last dataset:', last, '| today:', today, '| new dates:', start, 'to', today, flush=True)
    if today < last:
        sys.exit('Local clock predates dataset. Check system date.')
    if start > today:
        print('Already current through today; nothing to fetch.')
        return
    ids = sorted({line.strip().replace('USGS-', '', 1)
                  for line in (ROOT / 'usgs_gauge_ids.txt').read_text().splitlines()
                  if line.strip()})
    if not ids:
        sys.exit('No gauge IDs found.')
    rows = []
    for i in range(0, len(ids), args.batch_size):
        batch = ids[i:i + args.batch_size]
        params = urlencode({'format': 'json', 'sites': ','.join(batch),
                            'startDT': start.isoformat(), 'endDT': today.isoformat(),
                            'parameterCd': '00065', 'siteStatus': 'all'})
        url = 'https://waterservices.usgs.gov/nwis/iv/?' + params
        try:
            with urlopen(Request(url, headers={'User-Agent': 'SouthernLakeMichiganFlowAtlas/1.0'}),
                         timeout=90) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            sys.exit('USGS download failed at batch %s: %s. No data published.' %
                     (i // args.batch_size + 1, exc))
        count = 0
        for series in payload.get('value', {}).get('timeSeries', []):
            src = series.get('sourceInfo', {})
            sid = next((c.get('value', '') for c in src.get('siteCode', []) if c.get('value')), '')
            sid = sid.replace('USGS-', '', 1)
            codes = [c.get('value') for c in series.get('variable', {}).get('variableCode', [])]
            if sid not in batch or '00065' not in codes:
                continue
            for group in series.get('values', []):
                for v in group.get('value', []):
                    try:
                        n = float(v['value'])
                    except (KeyError, ValueError, TypeError):
                        continue
                    if not -1000 < n < 10000:
                        continue
                    rows.append(('USGS-' + sid, '00065', '00011',
                                 v.get('dateTime', ''), str(n)))
                    count += 1
        print('Batch %d/%d: %d observations' %
              (i // args.batch_size + 1, (len(ids) + args.batch_size - 1) // args.batch_size, count),
              flush=True)
        time.sleep(args.delay)
    if not rows:
        sys.exit('USGS returned no observations. Existing dataset unchanged.')
    # The consolidator scans the top level of Downloads, not nested directories.
    args.downloads.mkdir(parents=True, exist_ok=True)
    outfile = args.downloads / ('usgs_atlas_update_%s_%s.csv' % (start, today))
    with outfile.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['monitoring_location_id', 'parameter_code',
                         'statistic_id', 'time', 'value'])
        writer.writerows(dict.fromkeys(rows))
    print('Saved new observations:', outfile, flush=True)
    print('Rebuilding rolling 365-day statistics...', flush=True)
    subprocess.run([sys.executable, str(ROOT / 'consolidate_usgs.py'),
                    '--end', today.isoformat(), '--downloads', str(args.downloads)],
                   cwd=ROOT, check=True)
    if args.publish:
        git('add', 'data/stage_minima.json', 'data/stage_minima_audit.csv')
        if git('diff', '--cached', '--name-only'):
            git('commit', '-m', 'Update USGS annual stage statistics through %s' % today)
            git('push', 'origin', 'main')
            print('Published updated dataset to origin/main.')
        else:
            print('No dataset changes to publish.')
    else:
        print('Review the results, then rerun with --publish to commit and push.')

if __name__ == '__main__':
    main()
