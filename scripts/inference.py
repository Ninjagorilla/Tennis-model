import concurrent.futures,json,os,subprocess,sys
from pathlib import Path
ROLES=('champion','challenger','experimental')
def execute(runtime,events,as_of,dest,roles=ROLES):
    dest.mkdir(parents=True,exist_ok=True);input_path=dest/'input.json';input_path.write_text(json.dumps({'events':events,'as_of':as_of}))
    def run(role):
        output=dest/(role+'.jsonl');output.unlink(missing_ok=True);env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',NUMBA_CACHE_DIR=str(dest/'numba'))
        for k in ('PYTHONPATH','PYTHONHOME'):env.pop(k,None)
        try:
            p=subprocess.run([sys.executable,str(Path(__file__).with_name('model_worker.py')),role,str(runtime),str(input_path),str(output)],env=env,capture_output=True,timeout=480)
            if p.returncode:print(role+': worker failed; details retained locally',file=sys.stderr)
            (dest/(role+'.log')).write_bytes(p.stderr)
        except subprocess.TimeoutExpired:print(role+': worker timeout',file=sys.stderr)
        rows={}
        if output.exists():
            for line in output.read_text().splitlines():
                try:r=json.loads(line);rows[r['index']]=r
                except (ValueError,KeyError):continue
        return role,rows
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:return dict(pool.map(run,roles))
def preflight(runtime,dest):
    cases=json.loads((runtime/'canaries.json').read_text());events=[r['event'] for r in cases['cases']]
    out=execute(runtime,events,cases['as_of'],dest)
    return {role:{'passed':sum(abs(out[role].get(i,{}).get('result',{}).get('p_a',-100)-c['expected'][role])<1e-10 for i,c in enumerate(cases['cases'])),'total':len(events)} for role in ROLES}
if __name__=='__main__':
    r=preflight(Path(sys.argv[1]),Path(sys.argv[2]));print(json.dumps(r));sys.exit(0 if all(x['passed']==x['total'] for x in r.values()) else 1)
