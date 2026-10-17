"""Chronological first-touchdown research. No odds or current-game usage features.

Quarters are at-risk intervals, with all overtime pooled into interval five.
Game-first and team-first estimators have distinct risk sets. Unseen scorers and
non-offensive TDs remain explicit team-specific residual outcomes. Historical
sources are current-vintage, not archived pregame availability observations.
"""
from __future__ import annotations
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
import copy, hashlib, json, math
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import softmax, logsumexp
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

VERSION = 'NFL-First-TD-Research-0.2.1'
NO_TD = '__no_touchdown__'
CHANNELS = ('rush', 'receive', 'other')
HISTORY = 8
PLAN = {
    'version': VERSION, 'warmup': [2021], 'fit': [2022, 2023],
    'calibration': [2024], 'retrospective_test': [2025, 2026],
    'hazard_regularization_C': 0.1, 'share_l2_penalty': 5.0,
    'temperature_grid': [0.8, 1.0, 1.25, 1.6], 'bootstrap_games': 5000,
    'market_definitions': ['game_first_td_including_overtime', 'team_first_td_including_overtime'],
    'promotion_requires': 'Prospective paired Brier/log-loss improvement and no material subgroup degradation',
    'prior_test_exposure': '2025/2026 have been examined in other NFL diagnostics. This is retrospective, not prospective.',
    'availability': 'Historical candidates use only earlier games, never the target game participating roster.',
    'play_order': 'Provider order_sequence, never numeric play_id chronology',
    'data_repair': 'Corrected sequence handling before publication; provisional 0.2.0 results retained separately',
    'fixed_baseline': 'Smoothed training-quarter cause rates plus fixed prior-only opportunity/scoring shares',
}

def canonical(x): return json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b'\n')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def unknown(team): return '__unknown__:' + team
def outcome_id(label):
    pid=label['player_id']
    return pid if pid.startswith('__') else label['team']+'|'+pid

def valid_plays(p):
    """Only recorded plays, not nullified touchdowns or conversion attempts."""
    return p[~p.play_deleted.eq(1) & ~p.play_type.eq('no_play') &
             ~p.extra_point_attempt.eq(1) & ~p.two_point_attempt.eq(1)].copy()

def first_label(p, team=None):
    t = p[p.touchdown.eq(1)]
    if team is not None: t = t[t.td_team.eq(team)]
    if t.empty: return {'quarter': 6, 'team': None, 'player_id': NO_TD, 'channel': None}
    ordered = t.sort_values(['order_sequence','play_id'], kind='stable')
    if len(ordered)>1 and ordered.iloc[0].order_sequence == ordered.iloc[1].order_sequence:
        raise ValueError('Ambiguous first-scoring play sequence')
    r = ordered.iloc[0]
    if pd.isna(r.td_team): raise ValueError('A scoring team is missing')
    return {'quarter': min(int(r.qtr), 5), 'team': str(r.td_team),
            'player_id': str(r.td_player_id) if pd.notna(r.td_player_id) else unknown(str(r.td_team)),
            'channel': 'receive' if r.pass_touchdown == 1 else ('rush' if r.rush_touchdown == 1 else 'other')}

def history_summary(history, team):
    games = list(history.get(team, [])); players = {}; team_values = np.zeros(8)
    if not games: return {'players': {}, 'team': [0.8, 1.5, 0.9, 0.2, 0.8, 1.5, 0.9, 0.2], 'last_date': None}
    weights = np.array([0.8 ** i for i in range(len(games) - 1, -1, -1)])
    for g, w in zip(games, weights):
        team_values += w * np.array(g['team_features'])
        for pid, rec in g['players'].items():
            out = players.setdefault(pid, {'name': rec['name'], 'stats': np.zeros((2, 5))})
            out['stats'] += w * np.array(rec['stats'])
    # League-like fixed priors are identical for every team. No outcomes from this game.
    prior = np.array([0.8, 1.5, 0.9, 0.2, 0.8, 1.5, 0.9, 0.2])
    team_values = (team_values + 3 * prior) / (weights.sum() + 3)
    return {'players': {k: {'name': v['name'], 'stats': v['stats'].tolist()} for k, v in players.items()},
            'team': team_values.tolist(), 'last_date': games[-1]['date']}

def game_observation(p, team, opp, date):
    o = p[p.posteam.eq(team)]; d = p[p.posteam.eq(opp)]
    td = p[p.touchdown.eq(1) & p.td_team.eq(team)]
    against = p[p.touchdown.eq(1) & p.td_team.eq(opp)]
    def opening(frame):
        drive = frame.loc[(frame.rush_attempt.eq(1) | frame.pass_attempt.eq(1)), 'fixed_drive'].dropna()
        return frame[frame.fixed_drive.eq(drive.min())] if len(drive) else frame.iloc[:0]
    op = opening(o); dp = opening(d)
    features = [float(td.rush_touchdown.sum()), float(td.pass_touchdown.sum()), float(len(td) > 0),
                float(op.touchdown.eq(1).any()), float(against.rush_touchdown.sum()),
                float(against.pass_touchdown.sum()), float(len(against) > 0), float(dp.touchdown.eq(1).any())]
    players = {}
    for channel, id_col, name_col, mask, td_col in [
        (0, 'rusher_player_id', 'rusher_player_name', o.rush_attempt.eq(1), 'rush_touchdown'),
        (1, 'receiver_player_id', 'receiver_player_name', o.pass_attempt.eq(1), 'pass_touchdown')]:
        used = o[mask & o[id_col].notna()]
        for pid, g in used.groupby(id_col):
            name = g[name_col].dropna()
            v = players.setdefault(str(pid), {'name': str(name.iloc[-1]) if len(name) else str(pid), 'stats': np.zeros((2, 5))})
            v['stats'][channel] = [float((td.td_player_id.eq(pid) & td[td_col].eq(1)).sum()),
                float(g.yardline_100.le(20).sum()), float(g.yardline_100.le(5).sum()),
                float(g.fixed_drive.isin(op.fixed_drive.dropna().unique()).sum()), float(len(g))]
    return {'date': date, 'team_features': features,
            'players': {k: {'name': v['name'], 'stats': v['stats'].tolist()} for k, v in players.items()}}

def build_dataset(inputs, output):
    inputs, output = Path(inputs), Path(output); output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((inputs/'source_manifest.json').read_text())
    for source in manifest:
        if source['status'] == 'SUCCESS' and sha(inputs/source['name']) != source['sha256']:
            raise ValueError('Input hash mismatch: ' + source['name'])
    schedule = pd.read_csv(inputs/'games.csv')
    schedule = schedule[schedule.season.between(2021, 2026) & schedule.home_score.notna() & schedule.away_score.notna()]
    if schedule.game_id.duplicated().any(): raise ValueError('Duplicate schedule identity')
    columns = ['game_id','play_id','order_sequence','qtr','touchdown','td_team','td_player_id','td_player_name',
        'pass_touchdown','rush_touchdown','play_deleted','play_type','extra_point_attempt','two_point_attempt',
        'posteam','total_home_score','total_away_score','fixed_drive','yardline_100',
        'rush_attempt','pass_attempt','receiver_player_id','receiver_player_name','rusher_player_id','rusher_player_name']
    history = defaultdict(lambda: deque(maxlen=HISTORY)); records = []; coverage = []; exclusions = []
    for season, sch in schedule.groupby('season', sort=True):
        pbp = pd.read_parquet(inputs/f'pbp_{season}.parquet', columns=columns)
        groups = {str(k): g for k, g in pbp.groupby('game_id', sort=False)}
        for day, batch in sch.sort_values(['gameday','game_id']).groupby('gameday', sort=True):
            pending = []
            for r in batch.itertuples():
                if r.game_id not in groups:
                    exclusions.append({'game_id': r.game_id, 'reason': 'PBP missing'}); continue
                raw = groups[r.game_id].sort_values(['order_sequence','play_id'], kind='stable')
                if raw.order_sequence.isna().any():
                    exclusions.append({'game_id':r.game_id,'reason':'Missing chronological sequence'});continue
                if raw.play_id.duplicated().any():
                    exclusions.append({'game_id': r.game_id, 'reason': 'Duplicate play identities'}); continue
                last = raw.iloc[-1]
                if last.total_home_score != r.home_score or last.total_away_score != r.away_score:
                    exclusions.append({'game_id': r.game_id, 'reason': 'Final score mismatch'}); continue
                p = valid_plays(raw)
                if p[p.touchdown.eq(1)].td_team.isna().any() or not set(p.loc[p.touchdown.eq(1), 'td_team']).issubset({r.home_team,r.away_team}):
                    exclusions.append({'game_id': r.game_id, 'reason': 'Scoring team unresolved'}); continue
                h, a = history_summary(history, r.home_team), history_summary(history, r.away_team)
                for s in [h,a]:
                    if s['last_date'] is not None and s['last_date'] >= day: raise ValueError('Target-date feature leakage')
                rec = {'game_id': r.game_id, 'season': int(season), 'date': day, 'home': r.home_team,
                       'away': r.away_team, 'home_state': h, 'away_state': a,
                       'home_score':float(r.home_score),'away_score':float(r.away_score),
                       'game_first': first_label(p), 'team_first': {t:first_label(p,t) for t in [r.home_team,r.away_team]}}
                records.append(rec)
                pending += [(t,game_observation(p,t,o,day)) for t,o in [(r.home_team,r.away_team),(r.away_team,r.home_team)]]
            # No game on this calendar date enters any other game's predictors.
            for team, obs in pending: history[team].append(obs)
        coverage.append({'season': int(season), 'scheduled_completed': len(sch),
                         'verified': sum(x['season']==season for x in records), 'pbp_games': len(groups)})
    if len(records) < 1400: raise ValueError('Historical coverage is insufficient')
    report = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'coverage': coverage, 'exclusions': exclusions,
              'verified_games': len(records), 'game_first_no_td': sum(r['game_first']['player_id']==NO_TD for r in records),
              'team_first_no_td': sum(v['player_id']==NO_TD for r in records for v in r['team_first'].values()),
              'missing_game_first_scorer': sum(r['game_first']['player_id'].startswith('__unknown__') for r in records),
              'source_hashes': {x['name']:x.get('sha256') for x in manifest if x['status']=='SUCCESS'},
              'limitations': ['Single play-by-play provider, verified against its schedule final scores',
                             'Current-vintage history; no archived injury/roster availability',
                             'Candidates come from the previous eight team games, including explicit unknown outcomes',
                             'No current-game targets, carries, possession winner, roster or scoring enters predictors']}
    save(output/'dataset_report.json', report); save(output/'records.json', records)
    state = {t: history_summary(history,t) for t in history}
    save(output/'latest_state.json', {'as_of': max(r['date'] for r in records), 'teams': state})
    return records, report, state

def hazard_features(record, quarter, market, team=None):
    hs, aws = record['home_state']['team'], record['away_state']['team']
    # A team prediction is oriented toward that team, not toward the eventual scorer.
    if market == 'team' and team == record['away']: hs, aws = aws, hs
    return [int(quarter==q) for q in range(1,6)] + list(hs) + list(aws) + [int(team==record['home']) if market=='team' else 1]

def cause(record, label, market):
    if label['player_id'] == NO_TD: return 0
    c = CHANNELS.index(label['channel']) + 1
    return c + (3 if market=='game' and label['team']==record['away'] else 0)

def risk_rows(records, market):
    x, y, quarters = [], [], []
    for r in records:
        labs = [(None,r['game_first'])] if market=='game' else list(r['team_first'].items())
        for team, lab in labs:
            for q in range(1,min(lab['quarter'],5)+1):
                x.append(hazard_features(r,q,market,team));quarters.append(q)
                y.append(cause(r,lab,market) if q==lab['quarter'] else 0)
    return np.asarray(x,float),np.asarray(y,int),np.asarray(quarters,int)

def candidate_table(record, team, channel, roster=None):
    state = record['home_state'] if team==record['home'] else record['away_state']
    persons = state['players']; j = 0 if channel=='rush' else 1
    ids, features, base, names = [], [], [], []
    for pid in sorted(persons):
        if roster is not None and (pid not in roster or roster[pid].get('status')=='out'): continue
        v = np.asarray(persons[pid]['stats'],float)[j]
        if v[4] <= 0: continue
        ids.append(team+'|'+pid);names.append(persons[pid]['name']);features.append(np.r_[np.log1p(v),0.])
        base.append(.25*v[0]+.025*v[1]+.025*v[2]+.008*v[3]+.002*v[4]+.01)
    ids.append(unknown(team));names.append('Other / unallocated scorer');features.append([0.,0.,0.,0.,0.,1.]);base.append(.15)
    return ids,np.asarray(features,float),np.log(np.asarray(base)),names

def share_training_rows(records, market, channel):
    rows=[]
    for r in records:
        labs=[r['game_first']] if market=='game' else list(r['team_first'].values())
        for lab in labs:
            if lab['channel']!=channel: continue
            ids,x,offset,_=candidate_table(r,lab['team'],channel)
            actual=outcome_id(lab)
            winner=ids.index(actual) if actual in ids else len(ids)-1
            rows.append((x,offset,winner))
    return rows

def fit_share(rows):
    if len(rows)<50: return np.zeros(6),{'events':len(rows),'fit':False}
    def objective(w):
        loss=2.5*np.dot(w,w);grad=5*w.copy()
        for x,offset,y in rows:
            z=offset+x@w;p=softmax(z);loss+=logsumexp(z)-z[y];grad+=x.T@p-x[y]
        return loss,grad
    result=minimize(objective,np.zeros(6),method='L-BFGS-B',jac=True,options={'maxiter':400,'ftol':1e-11})
    if not result.success: raise ValueError('Player share fit did not converge: '+result.message)
    return result.x,{'events':len(rows),'fit':True,'iterations':int(result.nit)}

def fit_models(records):
    train=[r for r in records if r['season'] in PLAN['fit']]; fitted={}; receipts={}
    for market in ['game','team']:
        x,y,q=risk_rows(train,market);n=7 if market=='game' else 4
        model=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=2000,tol=1e-8))
        model.fit(x,y)
        baseline={str(k):((np.bincount(y[q==k],minlength=n)+.5)/(sum(q==k)+.5*n)).tolist() for k in range(1,6)}
        shares={};sr={}
        for channel in ['rush','receive']:
            w,receipt=fit_share(share_training_rows(train,market,channel));shares[channel]=w.tolist();sr[channel]=receipt
        fitted[market]={'model':model,'baseline':baseline,'shares':shares,'temperature':1.,'share_temperature':1.}
        receipts[market]={'risk_rows':len(y),'cause_counts':np.bincount(y,minlength=n).tolist(),'share_fits':sr}
    return fitted,receipts

def interval_hazards(record, fitted, market, *, baseline=False, team=None, rosters=None):
    n=7 if market=='game' else 4;model=fitted[market];qs=list(range(1,6))
    if baseline: causes=np.array([model['baseline'][str(q)] for q in qs])
    else:
        x=np.asarray([hazard_features(record,q,market,team) for q in qs],float)
        raw=model['model'].predict_proba(x);causes=np.full((5,n),1e-12)
        for j,c in enumerate(model['model'].classes_):causes[:,int(c)]=raw[:,j]
        causes=softmax(np.log(np.maximum(causes,1e-12))/model['temperature'],axis=1)
        # Rare overtime survivors use training-smoothed empirical risks in both models.
        causes[4]=np.array(model['baseline']['5'])
    teams=[record['home'],record['away']] if market=='game' else [team]
    shares={};names={}
    for t in teams:
        for c in ['rush','receive']:
            ids,x,offset,nms=candidate_table(record,t,c,None if rosters is None else rosters.get(t,{}))
            w=np.zeros(6) if baseline else np.array(model['shares'][c])
            p=softmax((offset+x@w)/(1. if baseline else model['share_temperature']))
            shares[(t,c)]=dict(zip(ids,p));names.update(dict(zip(ids,nms)))
    intervals=[]
    for q in qs:
        hazards=defaultdict(float)
        for j,t in enumerate(teams):
            for ci,c in enumerate(CHANNELS):
                mass=float(causes[q-1,1+3*j+ci])
                if c=='other': hazards[unknown(t)]+=mass
                else:
                    for pid,v in shares[(t,c)].items(): hazards[pid]+=mass*float(v)
        intervals.append({'index':q,'hazards':dict(hazards)})
    return intervals,names

def distribution(record,fitted,market,*,baseline=False,team=None,rosters=None):
    intervals,_=interval_hazards(record,fitted,market,baseline=baseline,team=team,rosters=rosters)
    result=defaultdict(float);survival=1.
    for interval in intervals:
        for pid,p in interval['hazards'].items():result[pid]+=survival*p
        survival*=1-math.fsum(interval['hazards'].values())
    result[NO_TD]=survival
    if abs(math.fsum(result.values())-1)>1e-10 or min(result.values()) < -1e-12:raise ValueError('Probability conservation failure')
    return dict(result)

def metrics(p, label):
    y=outcome_id(label)
    if y not in p:y=unknown(label['team'])
    if y not in p:raise ValueError('No matching residual outcome')
    named={k:v for k,v in p.items() if not k.startswith('__')}
    top=max(named,key=named.get) if named else None
    return {'log_loss':-math.log(max(p[y],1e-15)), 'brier':sum(v*v for v in p.values())-2*p[y]+1,
            'top_named_hit':int(top==outcome_id(label)), 'actual_probability':p[y], 'observed_bucket':y}

def calibrate(records,fitted):
    calibration=[r for r in records if r['season'] in PLAN['calibration']];receipts={}
    for market in ['game','team']:
        best=None
        for t in PLAN['temperature_grid']:
            for st in PLAN['temperature_grid']:
                fitted[market]['temperature']=t;fitted[market]['share_temperature']=st;losses=[]
                for r in calibration:
                    items=[(None,r['game_first'])] if market=='game' else list(r['team_first'].items())
                    for team,lab in items:losses.append(metrics(distribution(r,fitted,market,team=team),lab)['log_loss'])
                value=float(np.mean(losses)); key=(value,t,st)
                if best is None or key<best:best=key
        loss,t,st=best;fitted[market]['temperature']=t;fitted[market]['share_temperature']=st
        receipts[market]={'temperature':t,'share_temperature':st,'calibration_log_loss':loss,'season':2024}
    return receipts

def evaluate(records,fitted,out):
    rows=[];calibration=[]
    for r in records:
        if r['season'] not in PLAN['retrospective_test']:continue
        for market in ['game','team']:
            items=[(None,r['game_first'])] if market=='game' else list(r['team_first'].items())
            for team,label in items:
                row={'game_id':r['game_id'],'season':r['season'],'market':market,'team':team}
                for kind in ['baseline','challenger']:
                    p=distribution(r,fitted,market,baseline=kind=='baseline',team=team)
                    m=metrics(p,label);row[kind]=m
                    if kind=='challenger':
                        for pid,prob in p.items():
                            if not pid.startswith('__'):calibration.append({'game_id':r['game_id'],'market':market,'p':prob,'y':int(pid==outcome_id(label))})
                rows.append(row)
    def aggregate(rs):
        return {kind:{metric:float(np.mean([r[kind][metric] for r in rs])) for metric in ['log_loss','brier','top_named_hit']} for kind in ['baseline','challenger']}
    result={}
    for market in ['game','team']:
        rs=[r for r in rows if r['market']==market];summary=aggregate(rs);groups=defaultdict(list)
        for r in rs:groups[r['game_id']].append(r)
        rng=np.random.default_rng(20261017);ids=sorted(groups);boot={}
        for metric in ['log_loss','brier']:
            diffs=np.array([np.mean([r['challenger'][metric]-r['baseline'][metric] for r in groups[k]]) for k in ids])
            values=np.array([diffs[rng.integers(0,len(diffs),len(diffs))].mean() for _ in range(5000)])
            boot[metric]={'challenger_minus_baseline':float(diffs.mean()),'paired_game_bootstrap_95pct':np.quantile(values,[.025,.975]).tolist()}
        bins=[];cr=[r for r in calibration if r['market']==market]
        edges=[0,.025,.05,.10,.15,.20,.30,.5,1.00001]
        for lo,hi in zip(edges,edges[1:]):
            b=[r for r in cr if lo<=r['p']<hi]
            if b:bins.append({'lower':lo,'upper':hi,'rows':len(b),'mean_probability':float(np.mean([r['p'] for r in b])),'observed_rate':float(np.mean([r['y'] for r in b]))})
        result[market]={'games':len(groups),'contracts':len(rs),'scores':summary,'paired_differences':boot,'named_player_calibration':bins,
            'by_season':{str(year):aggregate([r for r in rs if r['season']==year]) for year in sorted(set(r['season'] for r in rs))}}
    report={'version':VERSION,'protocol':PLAN,'results':result,'prospective_games_graded':0,'promotion_approved':False,
            'status':'RETROSPECTIVE_RESEARCH_ONLY','note':'Engineering success or retrospective improvement alone does not satisfy the prospective promotion gate.'}
    save(Path(out)/'first_td_evaluation.json',report);save(Path(out)/'first_td_test_rows.json',rows)
    return report

def to_portable(fitted):
    out={}
    for market,value in fitted.items():
        scale,model=value['model'].steps[0][1],value['model'].steps[1][1]
        out[market]={k:v for k,v in value.items() if k!='model'}
        out[market]['model']={'mean':scale.mean_.tolist(),'scale':scale.scale_.tolist(),'coef':model.coef_.tolist(),
            'intercept':model.intercept_.tolist(),'classes':model.classes_.tolist()}
    return out

class PortableLogit:
    def __init__(self,spec):self.spec=spec;self.classes_=np.array(spec['classes'])
    def predict_proba(self,x):
        s=self.spec;z=(np.asarray(x)-s['mean'])/s['scale'];return softmax(z@np.asarray(s['coef']).T+s['intercept'],axis=1)

def from_portable(spec):
    return {market:{**value,'model':PortableLogit(value['model'])} for market,value in spec.items()}
