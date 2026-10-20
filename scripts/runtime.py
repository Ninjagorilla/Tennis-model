"""Verify and stage the sanitized, inference-only runtime. No pickle, refit or secrets."""
import concurrent.futures,hashlib,json,shutil,sys,urllib.request
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT/'engine'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def stage(dest,offline=None):
    manifest=json.loads((ENGINE/'manifest.json').read_text())
    for n,h in manifest['files'].items():
        p=ENGINE/n
        if not p.resolve().is_relative_to(ENGINE.resolve()) or sha(p)!=h:raise ValueError('RUNTIME_HASH_MISMATCH')
    shutil.copytree(ENGINE,dest,dirs_exist_ok=True)
    def fetch(item):
        p=dest/item['path'];p.parent.mkdir(parents=True,exist_ok=True)
        if not p.resolve().is_relative_to(dest.resolve()):raise ValueError('INVALID_DATA_PATH')
        if offline:
            raw=(Path(offline)/item['path']).read_bytes()
        else:
            url=item['url']
            if not url.startswith('https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/83733587353df8a41f2fd4f516147d5aa83f5a8d/'):raise ValueError('UNAPPROVED_SOURCE')
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Courtside-personal-research'}),timeout=45) as response:
                raw=response.read(16000000)
            if len(raw)>=16000000:raise ValueError('DATA_TOO_LARGE')
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('HISTORICAL_INPUT_HASH_MISMATCH')
        p.write_bytes(raw);p.with_suffix('.source.json').write_text(json.dumps({'url':item['url'],'sha256':item['sha256'],'retrieved_at':datetime.now(timezone.utc).isoformat()}))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,json.loads((ENGINE/'sources.json').read_text())))
    return manifest
if __name__=='__main__':
    stage(Path(sys.argv[1]),sys.argv[2] if len(sys.argv)>2 else None)
    print('Verified inference runtime staged; no training performed.')
