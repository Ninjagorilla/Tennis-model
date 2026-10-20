"""Execute recovered models, recheck fixtures, and project only public results."""
import json,math,os,sys
from datetime import timedelta
from pathlib import Path
from collect import collect,utc,fingerprint
from runtime import stage,sha,ENGINE
from inference import execute,preflight,ROLES
from explanations import sanitize
from quality import challenge
NAMES={'champion':'SR-Elo 1.0','challenger':'SR-GLM 0.2','experimental':'Matchup Intelligence V2 (v3.4-A baseline)'}
def project(row):
    if not row or 'result' not in row:return {'status':'unavailable','reason':(row or {}).get('error','EXECUTION_UNAVAILABLE')}
    r=row['result'];p=r.get('p_a');q=r.get('p_b')
    if type(p) not in (int,float) or type(q) not in (int,float) or not math.isfinite(p) or not math.isfinite(q) or not 0<=p<=1 or abs(p+q-1)>1e-9:return {'status':'unavailable','reason':'INVALID_PROBABILITY'}
    return {'status':'ok',**{k:r[k] for k in ('p_a','p_b','model_id','state_date','artifact_sha256','research_only')},'explanation':sanitize(row.get('model'),r.get('explanation')),'v2_readiness':r.get('v2_readiness') if row.get('model')=='experimental' else None}
def scan():
    start=utc();dest=Path('work/scan');dest.mkdir(parents=True,exist_ok=True);runtime=Path('work/runtime').resolve()
    doc={'schema_version':2,'generated_at':start.isoformat(),'expires_at':(start+timedelta(minutes=90)).isoformat(),'prediction_status':'blocked','build':{'commit':os.getenv('GITHUB_SHA'),'run_id':os.getenv('GITHUB_RUN_ID')},'models':[],'matches':[],'coverage':{'coverage':'unavailable','note':'Scan did not complete.'},'limitations':['Frozen recovered model states: Champion 2026-10-05; Challenger 2026-09-26; v3.4-A fit 2026-10-10. No automatic retraining.','Historical point data is pinned to June 2026; experimental result updates extend through October 14. Current fixtures do not imply fully current ratings.','Research probabilities conditional on match completion. Experimental Matchup Intelligence V2 currently reproduces uncalibrated v3.4-A probabilities; unverified new factors are not included. No automatic promotion.','Partial fixture coverage. Scheduled times are estimates; refreshes are hourly and can be delayed.']}
    checks={};outputs={};events=[]
    try:
        stage(runtime,os.getenv('OFFLINE_RUNTIME'))
        checks=preflight(runtime,dest/'preflight')
        events,coverage=collect();doc['coverage']=coverage
        eligible=[r for r in ROLES if checks[r]['passed']==checks[r]['total']==4]
        if eligible and events:outputs=execute(runtime,events,start.date().isoformat(),dest/'matches',eligible)
        # No stale fixture survives a missing/changed/started second observation.
        fresh,coverage=collect();doc['coverage']=coverage;current={fingerprint(e) for e in fresh}
        for i,e in enumerate(events):
            if fingerprint(e) not in current:continue
            results={r:project(outputs.get(r,{}).get(i)) if r in eligible else {'status':'unavailable','reason':'PREFLIGHT_FAILED'} for r in ROLES}
            match={k:e[k] for k in ('source_match_id','tour','regime','tournament','tournament_key','best_of','deciding_tiebreak_target','surface','name_a','name_b','starts_at','round','event_source','surface_source','format_source')}|{'results':results}
            if e['tour']=='WTA':
                # WTA SR-Elo blend is SHADOW ONLY. Never expose its probability
                # in the primary Champion slot or quietly promote a fallback.
                blend=results['champion']
                match['wta_blend_shadow']={**blend,'role':'SHADOW',
                    'not_for_action':True,'historical_metrics_citable':False}
                results['champion']={'status':'unavailable',
                    'reason':'WTA_BLEND_DEMOTED_TO_SHADOW'}
                sr=results['challenger']
                match['wta_selected']={
                    'role':'SR_CHALLENGER_RESEARCH' if sr['status']=='ok' else 'NO_FORECAST',
                    'status':sr['status'],
                    'selection_reason':'WTA_BLEND_DEMOTED_TO_SHADOW',
                    'research_only':True,
                    'model_id':sr.get('model_id') if sr['status']=='ok' else None,
                    'p_a':sr.get('p_a') if sr['status']=='ok' else None,
                    'p_b':sr.get('p_b') if sr['status']=='ok' else None}
            match['court_enclosure']=e.get('court_enclosure','Unknown')
            match['devils_advocate']=challenge(match)
            doc['matches'].append(match)
        doc['coverage']['model_missing_reasons']={role:{reason:sum(e['results'][role].get('reason')==reason for e in doc['matches']) for reason in sorted({e['results'][role].get('reason') for e in doc['matches'] if e['results'][role]['status']!='ok'})} for role in ROLES}
        doc['prediction_status']='available' if any(r['status']=='ok' for e in doc['matches'] for r in e['results'].values()) else 'unavailable'
    except Exception as exc:
        print('Scan blocked: '+type(exc).__name__,file=sys.stderr)
        doc['failure_code']='RUNTIME_OR_SCAN_FAILED'
    for role in ROLES:
        check=checks.get(role,{'passed':0,'total':4});count=sum(e['results'][role]['status']=='ok' for e in doc['matches'])
        doc['models'].append({'id':role,'name':NAMES[role],'preflight':check,'cloud_status':'verified' if check['passed']==4 else 'unavailable','predictions':count})
    end=utc();doc.update(generated_at=end.isoformat(),expires_at=(end+timedelta(minutes=90)).isoformat(),runtime_manifest_sha256=sha(ENGINE/'manifest.json'))
    Path('work/snapshot.json').write_text(json.dumps(doc,allow_nan=False,ensure_ascii=False),encoding='utf8')
    print(json.dumps({'status':doc['prediction_status'],'matches':len(doc['matches']),'models':doc['models']}))
if __name__=='__main__':scan()
