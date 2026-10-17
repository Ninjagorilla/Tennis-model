"""Acquire public NFL research inputs with content hashes; never invent missing data."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, time, urllib.request
import pandas as pd

OUT = Path('nfl_inputs')
OUT.mkdir(exist_ok=False)
receipts = []
def get(name, url, required=True):
    path = OUT / name
    last = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Personal-NFL-Research/1.0'})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
            path.write_bytes(raw)
            if name.endswith('.parquet'):
                frame = pd.read_parquet(path)
                rows, columns = len(frame), list(frame.columns)
            elif name.endswith('.csv'):
                frame = pd.read_csv(path, low_memory=False)
                rows, columns = len(frame), list(frame.columns)
            else:
                rows, columns = None, None
            receipts.append({'name': name, 'url': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'rows': rows, 'columns': columns, 'status': 'SUCCESS'})
            print('DOWNLOADED', name, len(raw), rows, flush=True)
            return
        except Exception as exc:
            last = str(exc)
            if path.exists(): path.unlink()
            time.sleep(2 * (attempt + 1))
    receipts.append({'name': name, 'url': url, 'status': 'UNAVAILABLE', 'error': last})
    if required:
        (OUT / 'source_manifest.json').write_text(json.dumps(receipts, indent=2))
        raise RuntimeError(name + ': ' + str(last))

get('games.csv', 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv')
for year in range(2021, 2027):
    get(f'pbp_{year}.parquet', f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet')
for name, tag, stem in [('rosters', 'rosters', 'roster'), ('injuries', 'injuries', 'injuries'), ('depth_charts', 'depth_charts', 'depth_charts')]:
    get(name + '.parquet', f'https://github.com/nflverse/nflverse-data/releases/download/{tag}/{stem}_2026.parquet', required=False)
get('participation_2026.parquet', 'https://github.com/nflverse/nflverse-data/releases/download/pbp_participation/pbp_participation_2026.parquet', required=False)
(OUT / 'source_manifest.json').write_text(json.dumps(receipts, indent=2))
print('ACQUISITION COMPLETE', flush=True)
