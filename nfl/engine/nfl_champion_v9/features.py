"""Market-free chronological team/QB state, inherited from NFL-Rebuild-0.1.
All same-day features are computed before outcomes. No archived fitted model is relabeled.
"""
import copy
import numpy as np
import pandas as pd
METRICS=['epa','pass_epa','rush_epa','success','explosive','sack_rate','redzone_success','plays']
DIFF=['off_'+k+'_diff' for k in METRICS]+['def_'+k+'_diff' for k in METRICS]+['margin_diff','pf_diff','pa_diff','qb_relative_diff','rest_diff','hfa']
SUM=['off_'+k+'_sum' for k in METRICS]+['def_'+k+'_sum' for k in METRICS]+['pf_sum','pa_sum','abs_margin_diff']
DEFAULT={'epa':0.,'pass_epa':0.,'rush_epa':0.,'success':.42,'explosive':.10,'sack_rate':.07,'redzone_success':.42,'plays':62.}


def seed_state(teams):return {t:{'off':copy.deepcopy(DEFAULT),'def':copy.deepcopy(DEFAULT),'margin':0.,'pf':22.,'pa':22.,'n':0} for t in teams}
def qb_mean(qbs,q):
    z=qbs.get(str(q),{'n':0.,'sum_epa':0.});return z['sum_epa']/(z['n']+180.)

def features(state,qbs,home,away,home_qb,away_qb,rest_diff,neutral):
    h,a=state[home],state[away];row={}
    for scope in ('off','def'):
        for k in METRICS:
            row[f'{scope}_{k}_diff']=(h[scope][k]-a[scope][k])*(1 if scope=='off' else -1)
            row[f'{scope}_{k}_sum']=h[scope][k]+a[scope][k]-2*DEFAULT[k]
    row.update(margin_diff=h['margin']-a['margin'],pf_diff=h['pf']-a['pf'],pa_diff=a['pa']-h['pa'],pf_sum=h['pf']+a['pf']-44,pa_sum=h['pa']+a['pa']-44,abs_margin_diff=abs(h['margin']-a['margin']),qb_relative_diff=(qb_mean(qbs,home_qb)-h['off']['pass_epa'])-(qb_mean(qbs,away_qb)-a['off']['pass_epa']),rest_diff=float(np.clip(rest_diff,-10,10)),hfa=0. if neutral else 1.)
    return row


def roll(schedule,aggregates,qb_aggregates):
    teams=sorted(set(schedule.home_team)|set(schedule.away_team));state=seed_state(teams);qbs={};rows=[];last_season=None
    games={(r['game_id'],r['team']):r for r in aggregates};qgames={}
    for r in qb_aggregates:qgames.setdefault(r['game_id'],[]).append(r)
    for day,batch in schedule.sort_values(['gameday','game_id']).groupby('gameday',sort=True):
        season=int(batch.iloc[0].season)
        if last_season is not None and season!=last_season:
            for t,s in state.items():
                for scope in ('off','def'):
                    for k in METRICS:s[scope][k]=.65*s[scope][k]+.35*DEFAULT[k]
                for k,target in [('margin',0.),('pf',22.),('pa',22.)]:s[k]=.65*s[k]+.35*target
            for q in qbs.values():q['n']*=.65;q['sum_epa']*=.65
        last_season=season;prior=copy.deepcopy(state)
        # Features for an entire date are generated before any same-date outcomes.
        for _,r in batch.iterrows():
            row=features(prior,qbs,r.home_team,r.away_team,r.home_qb_id,r.away_qb_id,r.home_rest-r.away_rest,r.location=='Neutral')
            rows.append(row|{'game_id':r.game_id,'season':season,'week':int(r.week),'gameday':day,'home':r.home_team,'away':r.away_team,'y':int(r.home_score>r.away_score),'tie':r.home_score==r.away_score,'margin':float(r.home_score-r.away_score),'total':float(r.home_score+r.away_score)})
        for _,r in batch.iterrows():
            for t,opp,pf,pa in [(r.home_team,r.away_team,r.home_score,r.away_score),(r.away_team,r.home_team,r.away_score,r.home_score)]:
                if (r.game_id,t) not in games:raise ValueError('missing completed game/team aggregate')
                obs=games[(r.game_id,t)];s=state[t]
                for k in METRICS:
                    v=obs[k]
                    if v is None:continue
                    # Efficiency residuals are adjusted against the opponent's prior.
                    adj_off=v;adj_def=v
                    if k in ('epa','pass_epa','rush_epa','success','explosive','sack_rate','redzone_success'):
                        adj_off=v-(prior[opp]['def'][k]-DEFAULT[k])
                        adj_def=v-(prior[t]['off'][k]-DEFAULT[k])
                    s['off'][k]=.8*s['off'][k]+.2*adj_off
                    state[opp]['def'][k]=.8*state[opp]['def'][k]+.2*adj_def
                for k,v in [('pf',pf),('pa',pa),('margin',pf-pa)]:s[k]=.8*s[k]+.2*float(v)
                s['n']+=1
            for q in qgames.get(r.game_id,[]):
                z=qbs.setdefault(q['qb_id'],{'n':0.,'sum_epa':0.});z['n']+=q['n'];z['sum_epa']+=q['sum_epa']
    return pd.DataFrame(rows),state,qbs

