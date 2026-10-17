"""Bounded, hashed public data acquisition. No account or paid data API."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,time,urllib.request
import pyarrow.parquet as pq
import pandas as pd

MAX_BYTES=90_000_000

def fetch_bytes(url,limit=MAX_BYTES):
    req=urllib.request.Request(url,headers={'User-Agent':'Courtside-NFL-Research/1.0'})
    with urllib.request.urlopen(req,timeout=60) as response:raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('Source exceeded download limit')
    return raw

def acquire(out,pinned):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);receipts=[]
    sources=[('games.csv','https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv',True)]
    for year in range(2021,2027):sources.append((f'pbp_{year}.parquet',f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet',True))
    for name,tag,stem,required in [('rosters','rosters','roster',True),('injuries','injuries','injuries',False)]:
        sources.append((name+'.parquet',f'https://github.com/nflverse/nflverse-data/releases/download/{tag}/{stem}_2026.parquet',required))
    for name,url,required in sources:
        error=None
        for attempt in range(2):
            try:
                raw=fetch_bytes(url);digest=hashlib.sha256(raw).hexdigest()
                if name in pinned and digest!=pinned[name]:raise ValueError('Pinned historical input changed; review required')
                path=out/name;path.write_bytes(raw)
                rows=pq.read_metadata(path).num_rows if name.endswith('.parquet') else len(pd.read_csv(path,low_memory=False))
                receipts.append({'name':name,'url':url,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'sha256':digest,'bytes':len(raw),'rows':rows,'status':'SUCCESS'})
                print('NFL source',name,rows,flush=True);break
            except Exception as exc:
                error=str(exc)
                if attempt==0:time.sleep(2)
        else:
            receipts.append({'name':name,'url':url,'status':'UNAVAILABLE','error':error})
            (out/'source_manifest.json').write_text(json.dumps(receipts,indent=2))
            if required:raise RuntimeError('Required source unavailable: '+name)
    (out/'source_manifest.json').write_text(json.dumps(receipts,indent=2))
    return receipts
