"""Restore bounded paper artifacts and grade immutable pregame forecasts.

No sportsbook settlement or ROI is inferred. Missing participation evidence
prevents player-stat contract grading. The earliest forecast per game and exact
parameter pair is used, so hourly runs cannot inflate the effective sample.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib, io, json, math, os, urllib.request, urllib.error, zipfile
import numpy as np
from nfl.research import canonical, outcome_id, unknown, save

REPO='Ninjagorilla/Tennis-model'
REPO_ID=1422683336
MAX_BYTES=12_000_000

def score(p, outcome):
    if not p or outcome not in p or any(not math.isfinite(v) or v<0 or v>1 for v in p.values()) or abs(sum(p.values())-1)>1e-8:
        raise ValueError('Invalid categorical forecast')
    return {'log_loss':-math.log(max(p[outcome],1e-15)),
            'brier':sum((v-int(k==outcome))**2 for k,v in p.items())}

def read_freeze(path):
    d=json.loads(Path(path).read_text());p=d['payload']
    if d['sha256']!=hashlib.sha256(canonical(p)).hexdigest():raise ValueError('Changed paper freeze')
    if p.get('schema')!='nfl-paper-freeze-1' or p.get('evidence_class')!='PREGAME_TWO_SOURCE_PAPER':return None
    stamp=datetime.fromisoformat(p['created_at_utc']);assert stamp.tzinfo is not None
    eligible=[]
    for g in p['games']:
        start=datetime.fromisoformat(g['starts_at'])
        if start.tzinfo is None or stamp>=start:continue
        if any('baseline_probabilities' not in v for v in g['first_td'].values()):continue
        eligible.append(g)
    p=dict(p);p['games']=eligible;p['_original_freeze']=d
    return p

def key(p,g):return '|'.join((g['event_id'],p['model_parameter_sha256'],p['first_td_parameter_sha256']))

def grade(directory, records, output):
    directory,output=Path(directory),Path(output);output.mkdir(parents=True,exist_ok=True)
    labels={r['game_id']:r for r in records};chosen={};prior={};invalid=[]
    for path in sorted(directory.rglob('*.json')):
        try:
            if path.name=='grades.json':
                ledger=json.loads(path.read_text())
                if ledger.get('schema')!='nfl-paper-grades-1':raise ValueError('Unknown grade ledger')
                for row in ledger['rows']:
                    if row['sha256']!=hashlib.sha256(canonical(row['result'])).hexdigest():raise ValueError('Changed grade ledger')
                    v=row['result'];old=prior.get(v['key'])
                    if old is None or v['forecast_at_utc']<old['forecast_at_utc']:prior[v['key']]=v
                continue
            if not path.name.startswith('forecast_'):continue
            p=read_freeze(path)
            if p is None:continue
            for g in p['games']:
                k=key(p,g)
                if k not in chosen or p['created_at_utc']<chosen[k][0]['created_at_utc']:chosen[k]=(p,g)
        except (ValueError,KeyError,TypeError,AssertionError) as exc:
            invalid.append({'file':path.name,'reason':str(exc)[:120]})
    pending={};new=0
    for k,(p,g) in chosen.items():
        if k in prior and prior[k]['forecast_at_utc']<=p['created_at_utc']:continue
        r=labels.get(g['event_id'])
        if r is None:
            pending.setdefault(p['created_at_utc'],(p,[]))[1].append(g);continue
        if (r['home'],r['away'])!=(g['home'],g['away']):raise ValueError('Paper result identity conflict')
        row={'key':k,'event_id':g['event_id'],'forecast_at_utc':p['created_at_utc'],'graded_at_utc':datetime.now(timezone.utc).isoformat(),
             'model_parameter_sha256':p['model_parameter_sha256'],'first_td_parameter_sha256':p['first_td_parameter_sha256'],'first_td':{}}
        if 'home_score' in r and 'away_score' in r:
            outcome='home' if r['home_score']>r['away_score'] else ('away' if r['away_score']>r['home_score'] else 'tie')
            row['game_winner']=score({'home':g['game']['home_win'],'away':g['game']['away_win'],'tie':g['game']['tie']},outcome)
            row['game_winner']['outcome']=outcome
        for m,d in g['first_td'].items():
            label=r['game_first'] if m=='game' else r['team_first'][m]
            actual=outcome_id(label)
            if actual not in d['probabilities']:actual=unknown(label['team'])
            b=d['baseline_probabilities'];c=d['probabilities']
            row['first_td'][m]={'outcome':actual,'baseline':score(b,actual),'challenger':score(c,actual)}
        prior[k]=row;new+=1
    rows=[{'result':v,'sha256':hashlib.sha256(canonical(v)).hexdigest()} for _,v in sorted(prior.items())]
    save(output/'grades.json',{'schema':'nfl-paper-grades-1','rows':rows,'invalid_inputs':invalid,'new_grades':new,'promotion_approved':False,
        'limits':['Research categorical scores, not settled bets','No player-stat contract grading without participation evidence','Repeated forecasts deduplicated per game and parameter pair']})
    # Carry unresolved forecasts forward so postponements survive artifact expiration.
    for stamp,(p,games) in pending.items():
        save(output/('forecast_'+stamp.replace(':','').replace('.','')+'.json'),p['_original_freeze'])
    summary={'unique_games_graded':len({v['event_id'] for v in prior.values()}),'parameter_game_pairs_graded':len(prior),'new_grades':new,
             'pending_games':len({g['event_id'] for p,g in chosen.values() if g['event_id'] not in labels}),
             'invalid_files':len(invalid),'publication_approved':False,'by_parameters':{}}
    groups={}
    for v in prior.values():groups.setdefault(v['model_parameter_sha256']+'|'+v['first_td_parameter_sha256'],[]).append(v)
    for params,values in groups.items():
        metrics={}
        for market in ['game','team']:
            for metric in ['log_loss','brier']:
                deltas=[]
                for v in values:
                    subset=[d for m,d in v['first_td'].items() if (m=='game')==(market=='game')]
                    if subset:deltas.append(float(np.mean([d['challenger'][metric]-d['baseline'][metric] for d in subset])))
                if deltas:
                    a=np.array(deltas);ci=None
                    if len(a)>=20:
                        rng=np.random.default_rng(20261017);boot=[rng.choice(a,len(a),replace=True).mean() for _ in range(5000)];ci=np.quantile(boot,[.025,.975]).tolist()
                    metrics[market+'_'+metric]={'paired_games':len(a),'challenger_minus_baseline':float(a.mean()),'paired_game_bootstrap_95pct':ci}
        summary['by_parameters'][params]=metrics
    save(output/'prospective_summary.json',summary)
    return summary

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def restore(output):
    """Read only main-branch artifacts from this public repository, without writes."""
    token=os.environ.get('GH_TOKEN')
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if not token:return {'status':'unavailable','reason':'Artifact read token absent','artifacts':0}
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'Courtside-paper-reader'}
    def api(url):
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45) as r:return json.loads(r.read(MAX_BYTES+1))
    restored=0
    for page in [1,2]:
        data=api(f'https://api.github.com/repos/{REPO}/actions/artifacts?per_page=100&page={page}')
        for a in data.get('artifacts',[]):
            w=a.get('workflow_run',{})
            if a.get('expired') or not a['name'].startswith('nfl-paper-') or w.get('head_branch')!='main' or w.get('head_repository_id')!=REPO_ID:continue
            if a['size_in_bytes']>MAX_BYTES:continue
            url=f'https://api.github.com/repos/{REPO}/actions/artifacts/{int(a["id"])}/zip'
            # GitHub's token is never sent to the artifact-storage redirect host.
            try:
                urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url,headers=headers),timeout=45)
                raise ValueError('Artifact redirect missing')
            except urllib.error.HTTPError as e:
                if e.code!=302:raise
                location=e.headers['Location']
            if not location.startswith('https://'):raise ValueError('Non-HTTPS artifact')
            with urllib.request.urlopen(location,timeout=60) as r:raw=r.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise ValueError('Artifact size limit')
            z=zipfile.ZipFile(io.BytesIO(raw));total=sum(i.file_size for i in z.infolist())
            if total>MAX_BYTES:raise ValueError('Expanded artifact size limit')
            dest=out/str(a['id']);dest.mkdir(exist_ok=True)
            for i in z.infolist():
                name=Path(i.filename).name
                if name!='grades.json' and not(name.startswith('forecast_') and name.endswith('.json')):continue
                if '/' in i.filename or '\\' in i.filename or i.file_size>MAX_BYTES:raise ValueError('Unsafe artifact member')
                (dest/name).write_bytes(z.read(i))
            restored+=1
            if restored>=28:return {'status':'restored','artifacts':restored,'coverage':'Latest 28 matching artifacts; carried-forward ledger'}
        if len(data.get('artifacts',[]))<100:break
    return {'status':'restored','artifacts':restored,'coverage':'At most 200 recent artifact records searched; carried-forward ledger'}
