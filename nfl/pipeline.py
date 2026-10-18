"""Run the complete recovered NFL engine and fitted first-TD research component.

Public publication is gated. Paper forecasts are separate, timestamped, hashed
artifacts. A failed NFL run never replaces a valid tennis snapshot.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import argparse,copy,hashlib,json,math,sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'nfl/engine')]
from nfl.acquire import acquire,fetch_bytes
from nfl.devils_advocate import analyze as challenge, VERSION as SHADOW_VERSION
from nfl.portable import load_numeric
from nfl.research import build_dataset,from_portable,interval_hazards,distribution,unknown,save,sha,VERSION
from nfl.first_td_challenger.core import predict as first_td_predict
from nfl_champion_v9.data import aggregate_players
from nfl_champion_v9.aggregate_team import aggregate
from nfl_champion_v9.features import roll
from nfl_champion_v9.engine import run,probability
from nfl_champion_v9.feeds import slate,roster_inputs,kickoff

LADDERS={
 'passing_yards':list(range(150,451,25)), 'pass_attempts':list(range(15,56,5)),
 'completions':list(range(10,41,5)), 'passing_tds':[1,2,3,4,5],
 'rushing_yards':list(range(20,161,20)), 'carries':[5,10,15,20,25,30],
 'receiving_yards':list(range(10,161,10)), 'receptions':list(range(1,11)),
 'targets':[2,4,6,8,10,12,14], 'rushing_tds':[1,2,3], 'receiving_tds':[1,2,3]}


def now():return datetime.now(timezone.utc).isoformat()
def verify_manifest():
    manifest=json.loads((ROOT/'nfl/manifest.json').read_text())
    for name,digest in manifest['files'].items():
        path=ROOT/name
        if not path.is_file() or path.is_symlink() or sha(path)!=digest:raise ValueError('NFL source/parameter integrity failure')
    return manifest

def fixture_evidence(games):
    """ESPN second-source status, identity and kickoff check, without odds ingestion."""
    records={};days=set()
    for g in games:
        start=datetime.fromisoformat(g['kickoff_utc'].replace('Z','+00:00'))
        if start.tzinfo is None:raise ValueError('Timezone-aware kickoff required')
        # ESPN groups overnight UTC kickoffs under the US Eastern calendar day.
        # Query both dates and deduplicate identical provider events.
        days.update([start.astimezone(ZoneInfo('America/New_York')).strftime('%Y%m%d'),
                     start.astimezone(timezone.utc).strftime('%Y%m%d')])
    days=sorted(days)
    aliases={'LAR':'LA','WSH':'WAS'}
    for day in days:
        url='https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates='+day+'&limit=100'
        payload=json.loads(fetch_bytes(url,5_000_000));checked=now()
        for event in payload.get('events',[]):
            competition=event.get('competitions',[{}])[0];competitors=competition.get('competitors',[])
            sides={x.get('homeAway'):aliases.get(x.get('team',{}).get('abbreviation'),x.get('team',{}).get('abbreviation')) for x in competitors}
            status=event.get('status',{}).get('type',{})
            if set(sides)!={'home','away'}:continue
            key=(sides['home'],sides['away'])
            candidate={'source':'ESPN','source_event_id':str(event.get('id','')),'starts_at':event.get('date'),
                          'state':status.get('state'),'completed':status.get('completed'), 'checked_at_utc':checked}
            if key in records:
                prior=records[key]
                if any(prior[k]!=candidate[k] for k in ['source_event_id','starts_at','state','completed']):
                    raise ValueError('Ambiguous independent fixture')
            records[key]=candidate
    return records

def verified(g,evidence):
    e=evidence.get((g['home'],g['away']))
    if not e or e['state']!='pre' or e['completed'] is not False:return False
    try:return abs((datetime.fromisoformat(e['starts_at'].replace('Z','+00:00'))-datetime.fromisoformat(g['kickoff_utc'])).total_seconds())<=120
    except (ValueError,TypeError):return False

def fresh_bundle(inputs,work):
    d=work/'aggregate';d.mkdir(parents=True,exist_ok=True)
    schedule=pd.read_csv(inputs/'games.csv');schedule=schedule[schedule.season.between(2021,2026)]
    schedule.to_csv(d/'games.csv',index=False)
    teams,players=aggregate_players(inputs,schedule,d)
    if teams.scoring_residual.ne(0).any():raise ValueError('Scoring reconciliation failed')
    aggregates,qbs=aggregate(inputs)
    completed=schedule[schedule.game_id.isin(teams.game_id)&schedule.home_score.notna()]
    _,state,qb_state=roll(completed,aggregates,qbs)
    b=load_numeric(ROOT/'nfl/original_parameters.json');b['state']=state;b['qbs']=qb_state
    b['protocol']=copy.deepcopy(b['protocol']);b['protocol']['as_of']=str(completed.gameday.max())
    b['protocol']['last_game']=str(completed.sort_values('gameday').iloc[-1].game_id)
    b['protocol']['state_refreshed_at_utc']=now();b['protocol']['parameters_refitted']=False
    b['protocol']['source_hashes']={f.name:sha(f) for f in [d/'games.csv',d/'player_stats.parquet',d/'team_stats.parquet']}
    return b,players,teams

def first_td(record,g,fitted,source_time):
    rosters={t:{p['player_id']:p for p in ps} for t,ps in g.get('rosters',{}).items()}
    results={}
    for market,team in [('game',None),('team',g['home']),('team',g['away'])]:
        intervals,names=interval_hazards(record,fitted,market,team=team,rosters=rosters)
        ids=sorted({pid for step in intervals for pid in step['hazards']})
        entities=[]
        for pid in ids:
            t=pid.split(':',1)[1] if pid.startswith('__unknown__:') else pid.split('|',1)[0]
            rid=pid.split('|',1)[1] if '|' in pid else None
            status=rosters.get(t,{}).get(rid,{}).get('status','unknown')
            entities.append({'id':pid,'name':names.get(pid,'Other / unallocated scorer'),'team':t,
                             'kind':'unknown' if pid.startswith('__') else 'player','status':status})
        requested='GAME_FIRST_TD' if market=='game' else 'TEAM_FIRST_TD'
        request={'event_id':g['event_id'],'kind':'RESEARCH','market':requested,'target_team':team,'include_overtime':True,
                 'kickoff_utc':g['kickoff_utc'],'data_as_of_utc':source_time,'parameter_model_id':VERSION,
                 'source_refs':['nflverse hashed snapshot','NFL fitted first-TD numeric parameters'],
                 'entities':entities,'scenarios':[{'id':'conditional_available','weight':1.,'hazard_conditioning':requested,
                     'horizon_complete':True,'active_entities':[e['id'] for e in entities if e['status']!='out'],'intervals':intervals}]}
        pred=first_td_predict(request)
        results['game' if team is None else team]={'probabilities':pred['probabilities'],'input_sha256':pred['input_sha256'],
                                                  'status':'FITTED_RETROSPECTIVE_RESEARCH','include_overtime':True,
                'baseline_probabilities':distribution(record,fitted,market,baseline=True,team=team,rosters=rosters)}
    return results

def compact_forecast(result,samples,g,ftd):
    w=samples['weights'];home=samples['teams']['home']['score'];away=samples['teams']['away']['score']
    model_players={}
    for t,ps in result['players'].items():
        details={p['player_id']:p for p in result['inputs'][t]['players']};rows=[]
        for pid,p in ps.items():
            if pid.startswith('__') or pid not in details:continue
            info=details[pid]
            if info['status']=='out' or info['targets']+info['carries']+info['pass_attempts']<=0:continue
            ladders={}
            for stat,lines in LADDERS.items():
                if p[stat]['mean']<=0:continue
                draws=samples['players'][t][pid][stat]
                ladders[stat]=[{'at_least':line,'probability':float(w[draws>=line].sum())} for line in lines]
            rows.append({'player_id':pid,'name':info['name'],'availability':info['status'],'assumed_participation':True,
                         'mean':{s:p[s]['mean'] for s in LADDERS},'atd':p['atd'],'two_plus_td':p['two_plus_td'],'ladders':ladders})
        model_players[t]=rows
    return {'event_id':g['event_id'],'home':g['home'],'away':g['away'],'starts_at':g['kickoff_utc'],
            'game':result['game'],'players':model_players,'first_td':ftd,
            'totals':[{'line':v,**probability(home+away,w,v)} for v in np.arange(25.5,75,1).tolist()],
            'spreads':[{'home_line':v,**probability(home-away+v,w,0)} for v in np.arange(-20.5,21,1).tolist()],
            'team_totals':{side:[{'line':v,**probability(samples['teams'][side]['score'],w,v)} for v in np.arange(10.5,45,1).tolist()] for side in ['home','away']},
            'simulation':result['simulation'],'research_only':True,
            'warnings':['Availability is assumed, not a fitted probability of participation.','No sportsbook prices or edges are verified.']+result['warnings']}

def public_status(status,*,paper_games=0,state_date=None,error=None,publication=False,games=None,fixtures=None):
    evaluation=json.loads((ROOT/'nfl/evidence/first_td_evaluation.json').read_text())
    stamp=datetime.now(timezone.utc)
    return {'schema_version':1,'generated_at':stamp.isoformat(),'expires_at':(stamp+timedelta(minutes=90)).isoformat(),
            'execution_status':status,'publication_approved':publication,'prediction_status':'available' if publication and games else 'gated',
            'engine_version':'NFL-v9.1-integrated-1','first_td_version':VERSION,'state_date':state_date,'paper_games':paper_games,
            'games':games if publication else [],'fixtures':fixtures or [],'validation':evaluation,
            'markets':['Moneyline','Spread','Game total','Team total','Passing yards / attempts / completions / TDs',
                       'Rushing yards / carries / TDs','Receiving yards / receptions / targets / TDs','Anytime TD / 2+ TD',
                       'Game-first TD / team-first TD'],
            'publication_gate':'Prospective evidence is not yet sufficient. New NFL forecasts remain paper-only; no Champion promotion.',
            'error':error,'limits':['No wager execution or account connection','Current-vintage historical data, not as-published injuries',
                                   'Questionable-player availability is not probabilistically estimated','First-TD quarters include a sparse, smoothed overtime interval',
                                   'Historical inputs are checksum-pinned; changes require review','Tennis engines are not modified']}

def execute(args):
    manifest=verify_manifest();work=Path(args.work);work.mkdir(parents=True,exist_ok=True)
    inputs=Path(args.inputs) if args.inputs else work/'inputs'
    if args.inputs:
        source_manifest=json.loads((inputs/'source_manifest.json').read_text())
        for entry in source_manifest:
            if entry['status']=='SUCCESS' and sha(inputs/entry['name'])!=entry['sha256']:
                raise ValueError('Saved input does not match its acquisition receipt')
    else:source_manifest=acquire(inputs,manifest['historical_input_hashes'])
    print('NFL refreshing Champion state from verified inputs',flush=True)
    bundle,players,teams=fresh_bundle(inputs,work)
    print('NFL building prior-only first-TD state',flush=True)
    records,dataset,state=build_dataset(inputs,work/'first_td_dataset')
    fitted=from_portable(json.loads((ROOT/'nfl/first_td_parameters.json').read_text()))
    games=slate(inputs)
    if getattr(args,'event',None):
        games=[g for g in games if g['event_id']==args.event]
        if not games:raise ValueError('Requested event absent from future slate')
    print('NFL verifying',len(games),'future fixtures',flush=True)
    evidence={} if args.offline else fixture_evidence(games)
    snapshot=[];excluded=[];shadow=[];sources_at=max(s['retrieved_at_utc'] for s in source_manifest if s['status']=='SUCCESS')
    for i,g in enumerate(games):
        if not args.offline and not verified(g,evidence):
            excluded.append({'event_id':g['event_id'],'reason':'Independent identity, kickoff or pregame status not verified'});continue
        g,issues=roster_inputs(inputs,g)
        for side in ['home','away']:
            t=g[side];rows=g.get('rosters',{}).get(t,[])
            if not rows:raise ValueError('Missing team roster')
            if any(p['player_id']==g.get(side+'_qb_id') and p['status']=='out' for p in rows):g[side+'_qb_id']=None
        g['as_of_utc']=now()
        r,s=run(bundle,g,players,teams,n=args.draws,seed=20261017+i)
        rec={'home':g['home'],'away':g['away'],'home_state':state[g['home']],'away_state':state[g['away']]}
        td=first_td(rec,g,fitted,sources_at);forecast=compact_forecast(r,s,g,td);snapshot.append(forecast)
        try:shadow.append(challenge(s,forecast))
        except Exception as exc:shadow.append({'event_id':g['event_id'],'status':'blocked','error_type':type(exc).__name__})
        print('NFL full-engine paper forecast',g['event_id'],flush=True)
    # A separate post-inference check prevents a stale fixture from being frozen.
    if not args.offline:
        after=fixture_evidence([g for g in games if any(s['event_id']==g['event_id'] for s in snapshot)])
        current={g['event_id']:g for g in slate(inputs)}
        kept=[]
        for record in snapshot:
            g=current[record['event_id']]
            if verified(g,after) and datetime.fromisoformat(g['kickoff_utc'])>datetime.now(timezone.utc):kept.append(record)
            else:excluded.append({'event_id':record['event_id'],'reason':'Started or changed during inference'})
        snapshot=kept
    shadow=[x for x in shadow if any(g['event_id']==x['event_id'] for g in snapshot)]
    for report in shadow:save(work/'shadow'/(report['event_id']+'.json'),report)
    stamp=now();payload={'schema':'nfl-paper-freeze-1','created_at_utc':stamp,
        'evidence_class':'LOCAL_SNAPSHOT_TIME_UNVERIFIED' if args.offline else 'PREGAME_TWO_SOURCE_PAPER',
        'model_parameter_sha256':sha(ROOT/'nfl/original_parameters.json'),'first_td_parameter_sha256':sha(ROOT/'nfl/first_td_parameters.json'),
        'source_hashes':{s['name']:s['sha256'] for s in source_manifest if s['status']=='SUCCESS'},
        'code_hashes':manifest['files'],'state_date':bundle['protocol']['as_of'],'games':snapshot,'excluded':excluded,
        'settlement_status':'PENDING','quotes_verified':False,'promotion_approved':False}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    dest=work/'paper';dest.mkdir(exist_ok=True)
    target=dest/('forecast_'+stamp.replace(':','').replace('.','')+'.json')
    if target.exists():raise ValueError('Paper freeze is immutable')
    save(target,{'payload':payload,'sha256':digest})
    from nfl.paper import restore,grade
    prior=work/'prior_paper'
    try: restored=restore(prior) if not args.offline else {'status':'offline','artifacts':0}
    except Exception as exc: restored={'status':'unavailable','artifacts':0,'reason':type(exc).__name__}
    save(work/'paper_restore.json',restored)
    summary=grade(work,records,work/'paper_archive')
    save(work/'paper_archive/restore_status.json',restored)
    # Publication must be an explicit, reviewed release decision, never automatic.
    public=public_status('verified' if not args.offline else 'offline_diagnostic',paper_games=len(snapshot),state_date=bundle['protocol']['as_of'],fixtures=[] if args.offline else [{k:g[k] for k in ['event_id','home','away','starts_at']} for g in snapshot])
    public['layers']={
        'champion':{'status':'executed','games':len(snapshot),'scope':'game_lines_and_player_props'},
        'challenger':{'status':'executed','games':len(snapshot),'scope':'first_touchdown_only'},
        'devils_advocate':{'status':'blocked' if any(x['status']=='blocked' for x in shadow) else 'executed_shadow',
                          'games':sum(x['status']=='executed_shadow' for x in shadow),'scope':'champion_draw_sensitivity','version':SHADOW_VERSION}}
    public['quotes_verified']=False
    public['calibration_status']='market_specific_validation_incomplete'
    public['prospective']=summary
    public['paper_history_restore']=restored
    save(ROOT/'work/nfl_snapshot.json',public)
    receipt={'created_at_utc':stamp,'execution_status':public['execution_status'],'paper_games':len(snapshot),
             'layers':public['layers'],'quotes_verified':False,'calibration_status':public['calibration_status'],
             'excluded_games':excluded,'public_forecasts':0,'publication_approved':False,'freeze_sha256':digest,
             'source_games':int(teams.game_id.nunique()),'first_td_verified_games':dataset['verified_games']}
    save(work/'receipt.json',receipt);print(json.dumps(receipt),flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--inputs');ap.add_argument('--work',default=str(ROOT/'work/nfl'))
    ap.add_argument('--event',help='Optional exact event ID, e.g. season_week_away_home');ap.add_argument('--draws',type=int,default=10000);ap.add_argument('--offline',action='store_true');args=ap.parse_args()
    try:execute(args);return 0
    except Exception as exc:
        print('NFL RUN BLOCKED:',type(exc).__name__,str(exc),file=sys.stderr)
        save(ROOT/'work/nfl_snapshot.json',public_status('blocked',error='NFL input or execution gate failed. See the run log.'))
        return 2

if __name__=='__main__':raise SystemExit(main())
