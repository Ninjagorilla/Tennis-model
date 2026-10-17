"""Seeded joint scoring/usage simulation, all outputs weighted by the same ML calibration.

Scored TDs are distinct from passing credit. Scores and TD counts share draws.
Receptions sum to QB completions, receiving yards to passing yards. This is a
research model: several dependence assumptions still need prospective validation.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from .features import features
from .model import means, VERSION
from .players import project, scenario_players
from .td import TDRequest, allocate
from .freezing import utc


def nb(rng,mu,shape,n):
    return rng.poisson(rng.gamma(shape,mu/shape,size=n))

def split(rng,counts,weights,concentration=None):
    w=np.asarray(weights,float)
    if not np.isfinite(w).all() or (w<0).any() or w.sum()<=0:raise ValueError('Invalid allocation weights')
    w/=w.sum();n=len(counts);p=np.tile(w,(n,1))
    if concentration:
        mask=w>0;p[:,mask]=rng.dirichlet(w[mask]*concentration,n)
    result=np.zeros((n,len(w)),dtype=int);remaining=np.asarray(counts,dtype=int).copy();left=np.ones(n)
    for i in range(len(w)-1):
        prob=np.divide(p[:,i],left,out=np.zeros(n),where=left>1e-12)
        result[:,i]=rng.binomial(remaining,np.clip(prob,0,1));remaining-=result[:,i];left-=p[:,i]
    result[:,-1]=remaining
    return result


def scoring_draws(bundle,env,n,rng):
    params=bundle['params'];teams={}
    for side in ['home','away']:
        m=env[side];shape=params['scoring_shape'];g=rng.gamma(shape,1/shape,n)
        counts={k:rng.poisson(m[k]*g) for k in ['pass_td','rush_td','other_td','fg']}
        count_td=counts['pass_td']+counts['rush_td']+counts['other_td']
        extra=split(rng,count_td,params['extra_point_probs'])
        safety=rng.poisson(params['safety_mean'],n)
        score=6*count_td+3*counts['fg']+extra[:,1]+2*extra[:,2]+2*safety
        # Defensive conversion returns are rare and included as a separately fitted event rate.
        defensive_two=rng.poisson(params.get('defensive_two_mean',0),n)
        score+=2*defensive_two
        counts.update(score=score,tds=count_td,extra_points=extra[:,1],two_point_conversions=extra[:,2],safeties=safety,defensive_two=defensive_two)
        teams[side]=counts
    # NFL regular-season ties remain possible. Calibration is conditional on no tie.
    h=teams['home']['score'];a=teams['away']['score'];win=h>a;loss=h<a;tie=h==a
    weights=np.ones(n,dtype=float)/n
    p=env['p_home_conditional_non_tie'];tie_rate=params['tie_rate'];non_tie=1-tie_rate
    if not tie.any():raise ValueError('Insufficient tie support; increase draws')
    weights[tie]=tie_rate/tie.sum()
    if not win.any() or not loss.any():raise ValueError('Insufficient Monte Carlo support; increase draws')
    weights[win]=non_tie*p/win.sum();weights[loss]=non_tie*(1-p)/loss.sum()
    return teams,weights


def simulate_team(bundle,team_id,event_id,env,counts,base,unknown,scenarios,n,rng,scenario_choices=None):
    probs=np.array([s['probability'] for s in scenarios],float)
    if not np.isfinite(probs).all() or (probs<=0).any() or abs(probs.sum()-1)>1e-10:raise ValueError('Scenario probabilities must sum to one')
    if len({s['scenario_id'] for s in scenarios})!=len(scenarios):raise ValueError('Duplicate availability scenarios')
    choice=rng.choice(len(scenarios),size=n,p=probs) if scenario_choices is None else scenario_choices
    ids=[x['player_id'] for x in base]+['__unallocated__']
    cols=['targets','receptions','receiving_yards','carries','rushing_yards','pass_attempts','completions','passing_yards','passing_tds','rushing_tds','receiving_tds','other_tds','tds']
    result={pid:{k:np.zeros(n,dtype=float) for k in cols}|{'active':np.zeros(n,dtype=bool)} for pid in ids}
    params=bundle['params'];priors=params['priors'];diagnostics=[]
    for i,scenario in enumerate(scenarios):
        idx=np.flatnonzero(choice==i);ns=len(idx)
        if ns==0:continue
        people,_=scenario_players(base,unknown,scenario)
        for p in people:result[p['player_id']]['active'][idx]=p['player_id'] in scenario['active_player_ids']
        weights={p['player_id']:{'rush':p['rush_td_weight'],'receive':p['receive_td_weight'],'other_score':p['other_td_weight']} for p in people if p['player_id'] in scenario['active_player_ids']}
        unallocated={'rush':max(unknown['carries'],.25),'receive':max(unknown['targets'],.5),'other_score':1.}
        request=TDRequest.from_dict({'team':team_id,'event_id':event_id,'kind':'RESEARCH','players':[{'player_id':p['player_id'],'name':p['name'],'status':p['status']} for p in people], 'scenarios':[{'scenario_id':scenario['scenario_id'],'probability':1.,'team_means':{'rush':env['rush_td'],'receive':env['pass_td'],'other_score':env['other_td']},'weights':weights,'unallocated_weights':unallocated,'dispersion_shape':params['scoring_shape'],'source_refs':scenario['source_refs']}]})
        allocated=allocate(request,request.scenarios[0])
        td_arrays={}
        for channel,target,stat in [('rush','rush_td','rushing_tds'),('receive','pass_td','receiving_tds'),('other_score','other_td','other_tds')]:
            shares=[allocated[pid][channel] for pid in ids]
            td_arrays[stat]=split(rng,counts[target][idx],shares)
            for j,pid in enumerate(ids):result[pid][stat][idx]=td_arrays[stat][:,j]
        attempts=nb(rng,env['pass_attempts'],params['volume_shapes']['pass_attempts'],ns)
        carries=nb(rng,env['carries'],params['volume_shapes']['carries'],ns)
        target_alloc=split(rng,attempts,[p['targets'] for p in people]+[unknown['targets']],params['share_concentration'])
        carry_alloc=split(rng,carries,[p['carries'] for p in people]+[unknown['carries']],params['share_concentration'])
        catches=rng.binomial(target_alloc,np.clip([p['catch_rate'] for p in people]+[priors['catch_rate']],0,1))
        # Structural constraints, counted so changes to count marginals are reviewable.
        original_catches=catches.copy();original_carries=carry_alloc.copy()
        catches=np.maximum(catches,td_arrays['receiving_tds']);target_alloc=np.maximum(target_alloc,catches)
        carry_alloc=np.maximum(carry_alloc,td_arrays['rushing_tds'])
        rec_mean=catches*np.array([p['ypc'] for p in people]+[priors['yards_per_catch']])
        rush_mean=carry_alloc*np.array([p['ypr'] for p in people]+[priors['yards_per_carry']])
        rec_yards=np.rint(rng.normal(rec_mean,np.sqrt(catches)*priors['receiving_yard_sd_per_sqrt_catch']))
        rush_yards=np.rint(rng.normal(rush_mean,np.sqrt(carry_alloc)*priors['rushing_yard_sd_per_sqrt_carry']))
        # Enforce feasible aggregate loss bounds; individual play lengths are not simulated.
        rec_yards=np.maximum(rec_yards,-99*catches);rush_yards=np.maximum(rush_yards,-99*carry_alloc)
        for j,pid in enumerate(ids):
            for stat,arr in [('targets',target_alloc),('receptions',catches),('receiving_yards',rec_yards),('carries',carry_alloc),('rushing_yards',rush_yards)]:result[pid][stat][idx]=arr[:,j]
        qb=scenario.get('qb_id')
        if qb is None:
            candidates=[p for p in people if p['player_id'] in scenario['active_player_ids']]
            qb=max(candidates,key=lambda p:p['pass_attempts'])['player_id'] if candidates and max(p['pass_attempts'] for p in candidates)>0 else '__unallocated__'
        if qb!='__unallocated__' and qb not in scenario['active_player_ids']:raise ValueError('Scenario quarterback is not active')
        result[qb]['pass_attempts'][idx]=target_alloc.sum(axis=1)
        result[qb]['completions'][idx]=catches.sum(axis=1)
        result[qb]['passing_yards'][idx]=rec_yards.sum(axis=1)
        result[qb]['passing_tds'][idx]=counts['pass_td'][idx]
        diagnostics.append({'scenario_id':scenario['scenario_id'],'n_draws':ns,'receiving_td_constraint_additions':int((catches-original_catches).sum()),'rushing_td_constraint_additions':int((carry_alloc-original_carries).sum()),'qb_id':qb})
    for pid in ids:result[pid]['tds']=result[pid]['rushing_tds']+result[pid]['receiving_tds']+result[pid]['other_tds']
    return result,diagnostics


def probability(draws,weights,line,side='over'):
    if isinstance(line,bool) or not np.isfinite(line):raise ValueError('Finite numeric line required')
    if side not in ['over','under']:raise ValueError('side must be over or under')
    equal=np.isclose(draws,line,rtol=0,atol=1e-10);win=(draws>line) if side=='over' else (draws<line)
    return {'win':float(weights[win & ~equal].sum()),'push':float(weights[equal].sum()),'loss':float(weights[~win & ~equal].sum())}


def summary(x,w):
    order=np.argsort(x);q=np.interp([.1,.5,.9],np.cumsum(w[order]),x[order])
    return {'mean':float(np.dot(x,w)),'p10':float(q[0]),'median':float(q[1]),'p90':float(q[2])}


def run(bundle,game,history,team_stats,*,n=20000,seed=904,row=None,replay=False):
    if isinstance(n,bool) or not isinstance(n,int) or n<1000 or n>1000000:raise ValueError('draws must be 1000..1000000')
    required={'event_id','home','away','kickoff_utc','as_of_utc','season','week'}
    if required-set(game):raise ValueError('Missing fixture fields '+str(sorted(required-set(game))))
    allowed=required|{'home_qb_id','away_qb_id','rest_diff','neutral_site','rosters','scenarios','source_refs','status','status_checked_at_utc','context','roster_checked_at_utc'}
    if set(game)-allowed:raise ValueError('Unsupported fixture fields, including market inputs: '+str(sorted(set(game)-allowed)))
    home,away=game['home'],game['away'];kick=utc(game['kickoff_utc']);at=utc(game['as_of_utc']);cutoff=kick.date().isoformat()
    if home==away or home not in bundle['state'] or away not in bundle['state']:raise ValueError('Unknown or duplicate teams')
    if game['event_id']!=f"{int(game['season'])}_{int(game['week']):02d}_{away}_{home}":raise ValueError('Fixture identity mismatch')
    if at>=kick:raise ValueError('Forecast cutoff must precede kickoff')
    if not replay and bundle['protocol']['as_of']>=cutoff:raise ValueError('State contains target-date or later outcomes')
    if replay and row is None:raise ValueError('Replay requires prior-only feature row')
    row=row or features(bundle['state'],bundle['qbs'],home,away,game.get('home_qb_id',''),game.get('away_qb_id',''),game.get('rest_diff',0),game.get('neutral_site',False))
    env=means(bundle,row);rng=np.random.default_rng(seed)
    outplayers={};details={};issues=[];prepared={}
    if not replay and (at.date()-pd.Timestamp(bundle['protocol']['as_of']).date()).days>7:issues.append('Model state is over 7 days old; refresh inputs before relying on this forecast')
    for side,team in [('home',home),('away',away)]:
        base,unknown=project(history,team_stats,team,cutoff,bundle['params']['priors'],game.get('rosters',{}).get(team),game.get(side+'_qb_id'))
        scenarios=game.get('scenarios',{}).get(team)
        if scenarios is None:
            scenarios=[{'scenario_id':'assumed_available','probability':1.,'active_player_ids':[p['player_id'] for p in base if p['status']!='out'],'qb_id':game.get(side+'_qb_id'),'source_refs':['Recent historical usage; unverified availability assumption']}]
            issues.append(team+': availability assumed from history; not confirmed active')
        elif any(p['status']=='questionable' for p in base):issues.append(team+': caller-supplied availability scenario probabilities')
        if not game.get(side+'_qb_id'):issues.append(team+': starting QB not verified; team model uses unknown-QB prior')
        prepared[side]=(team,base,unknown,scenarios)
    hs=prepared['home'][3];aws=prepared['away'][3]
    for ss in [hs,aws]:
        if not ss or abs(sum(s['probability'] for s in ss)-1)>1e-10 or any(not np.isfinite(s['probability']) or s['probability']<=0 for s in ss):raise ValueError('Scenario probabilities must sum to one')
    qb_mixture=len(hs)>1 or len(aws)>1 or any(s.get('qb_id',game.get(side+'_qb_id'))!=game.get(side+'_qb_id') for side,ss in [('home',hs),('away',aws)] for s in ss)
    choices={'home':None,'away':None};scenario_environments=[]
    if qb_mixture:
        if replay:raise ValueError('Historical QB scenarios require archived scenario-specific feature state')
        combos=[(i,j,h['probability']*a['probability']) for i,h in enumerate(hs) for j,a in enumerate(aws)]
        if len(combos)>64:raise ValueError('At most 64 joint availability scenarios')
        sizes=np.floor(np.array([c[2] for c in combos])*n).astype(int)
        sizes[np.argmax(sizes)]+=n-int(sizes.sum())
        if (sizes==0).any():raise ValueError('Increase draws to represent rare availability scenarios')
        choices={'home':np.zeros(n,dtype=int),'away':np.zeros(n,dtype=int)};teams=None;w=np.zeros(n);offset=0
        for (i,j,prob),ns in zip(combos,sizes):
            hq=hs[i].get('qb_id',game.get('home_qb_id',''));aq=aws[j].get('qb_id',game.get('away_qb_id',''))
            sr=features(bundle['state'],bundle['qbs'],home,away,hq,aq,game.get('rest_diff',0),game.get('neutral_site',False));se=means(bundle,sr)
            candidate,cw=scoring_draws(bundle,se,max(int(ns),4000),rng)
            selected=rng.choice(len(cw),int(ns),p=cw)
            if teams is None:teams={side:{k:np.zeros(n,dtype=v.dtype) for k,v in z.items()} for side,z in candidate.items()}
            sl=slice(offset,offset+int(ns));w[sl]=prob/ns;choices['home'][sl]=i;choices['away'][sl]=j
            for side,z in candidate.items():
                for k,v in z.items():teams[side][k][sl]=v[selected]
            scenario_environments.append({'home_scenario':hs[i]['scenario_id'],'away_scenario':aws[j]['scenario_id'],'probability':prob,'environment':se})
            offset+=int(ns)
        issues.append('Joint team availability scenarios treated as independent; scenario QB changes recompute fitted team-scoring features')
    else:teams,w=scoring_draws(bundle,env,n,rng)
    for side in ['home','away']:
        team,base,unknown,scenarios=prepared[side]
        draws,diag=simulate_team(bundle,team,game['event_id'],env[side],teams[side],base,unknown,scenarios,n,rng,choices[side])
        details[team]={'players':base,'unallocated_opportunities':unknown,'scenarios':scenarios,'simulation_diagnostics':diag}
        outplayers[team]=draws
    h,a=teams['home']['score'],teams['away']['score']
    game_summary={'home_score':summary(h,w),'away_score':summary(a,w),'total':summary(h+a,w),'home_margin':summary(h-a,w),'home_win':float(w[h>a].sum()),'away_win':float(w[a>h].sum()),'tie':float(w[a==h].sum())}
    player_summary={}
    for team,players in outplayers.items():
        player_summary[team]={}
        for pid,draws in players.items():
            p={k:summary(x,w) for k,x in draws.items() if k!='active'}
            active=draws['active'];pa=float(w[active].sum());p['active_probability']=pa
            p['atd']=float(w[draws['tds']>=1].sum());p['two_plus_td']=float(w[draws['tds']>=2].sum())
            p['atd_conditional_active']=float(w[(draws['tds']>=1)&active].sum()/pa) if pa>0 else None
            player_summary[team][pid]=p
    if game.get('context'):issues.append('Weather/OL context retained for review but not assigned an untrained numeric effect')
    issues.append('Research baseline; no proven predictive improvement or betting profitability')
    result={'version':VERSION,'event_id':game['event_id'],'kind':'RESEARCH','game':game_summary,'players':player_summary,'inputs':details,'team_environment_before_ml_reweight':env,'scenario_environments':scenario_environments,'features':row,'warnings':issues,'fit_protocol':bundle['protocol'],'simulation':{'draws':n,'seed':seed,'effective_sample_size':float(1/np.dot(w,w)),'tie_method':'Final-score tie mass reweighted to 2024 empirical tie rate with Jeffreys smoothing; no explicit overtime sequence','dependence':'Shared team scoring gamma; ML calibration reweights every market. Cross-team tempo not explicitly modeled.','source':'Fitted scoring and volume models plus prior-only player usage'},'status':'REPLAY_DIAGNOSTIC' if replay else 'RESEARCH_FORECAST'}
    # Return sample arrays for downstream markets and exact same-draw parlay comparisons.
    return result,{'teams':teams,'players':outplayers,'weights':w}


def market_draws(samples,market):
    kind=market['kind'];h=samples['teams']['home']['score'];a=samples['teams']['away']['score']
    if kind=='moneyline':return (h-a if market['side']=='home' else a-h),0.,'over',None
    if kind=='spread':return (h-a if market['side']=='home' else a-h)+float(market['line']),0.,'over',None
    if kind=='total':return h+a,float(market['line']),market['side'],None
    if kind=='team_total':return samples['teams'][market['team_side']]['score'],float(market['line']),market['side'],None
    if kind=='player':
        if market['stat']=='active':raise ValueError('Unsupported prop stat')
        p=samples['players'][market['team']][market['player_id']]
        return p[market['stat']],float(market['line']),market['side'],p['active']
    raise ValueError('Unsupported market kind')
