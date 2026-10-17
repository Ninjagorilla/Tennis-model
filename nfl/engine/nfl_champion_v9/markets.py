"""Downstream market comparison/settlement. Quotes never become model features."""
import math
import numpy as np
from .engine import market_draws
from .freezing import utc


def decimal(american):
    if isinstance(american,bool) or not isinstance(american,(float,int)) or not math.isfinite(american) or abs(american)<100:raise ValueError('Invalid American odds')
    return 1+american/100 if american>0 else 1+100/abs(american)


def evaluate(samples,market):
    if market.get('side') not in (['home','away'] if market['kind'] in ['moneyline','spread'] else ['over','under']):raise ValueError('Invalid market side')
    x,line,side,active=market_draws(samples,market);w=samples['weights']
    if not np.isfinite(line):raise ValueError('Nonfinite line')
    equal=np.isclose(x,line,atol=1e-10,rtol=0);won=(x>line if side=='over' else x<line)&~equal
    void=np.zeros(len(x),bool)
    if market['kind']=='moneyline':
        rule=market.get('tie_rule')
        if rule not in ['push','loss']:raise ValueError('Explicit moneyline tie_rule push/loss required')
        if rule=='loss':equal[:]=False
    if active is not None:
        if market['player_id']=='__unallocated__':raise ValueError('Unknown-scorer bucket is not a tradable player')
        rule=market.get('dnp_rule')
        if rule not in ['void','action']:raise ValueError('Explicit player dnp_rule void/action required')
        if rule=='void':void=~active;won&=active;equal&=active
    lost=~(won|equal|void)
    return {'win':float(w[won].sum()),'loss':float(w[lost].sum()),'push':float(w[equal].sum()),'void':float(w[void].sum())},{'win':won,'loss':lost,'push':equal,'void':void}


def compare(samples,quotes,event_id,as_of):
    ids=set();result=[]
    for q in quotes:
        if not q.get('quote_id') or q['quote_id'] in ids:raise ValueError('Missing/duplicate quote ID')
        ids.add(q['quote_id'])
        if q['event_id']!=event_id:raise ValueError('Quote event mismatch')
        age=(utc(as_of)-utc(q['captured_at_utc'])).total_seconds()
        if age<0 or age>900:raise ValueError('Quote future-dated or older than 15 minutes')
        if not q.get('venue') or not q.get('source_ref'):raise ValueError('Quote provenance required')
        p,_=evaluate(samples,q);dec=decimal(q['american_odds']);action=p['win']+p['loss']
        result.append({'quote_id':q['quote_id'],'venue':q['venue'],'quote':q,'probabilities':p,'market_break_even':1/dec,'model_win_conditional_decision':p['win']/action if action else None,'expected_profit_per_unit':p['win']*(dec-1)-p['loss'],'fair_decimal':1+p['loss']/p['win'] if p['win']>0 else None,'captured_at_utc':q['captured_at_utc'],'verification':'Caller-supplied quote; not authenticated execution verification','verdict':'RESEARCH_ONLY'})
    return sorted(result,key=lambda x:(x['venue'].lower()!='novig',-x['expected_profit_per_unit']))


def joint(samples,legs):
    if not legs:raise ValueError('At least one leg required')
    identities=[str(sorted(x.items())) for x in legs]
    if len(set(identities))!=len(identities):raise ValueError('Duplicate parlay legs')
    events={x.get('event_id') for x in legs}
    if len(events)!=1:raise ValueError('Only same-event joint simulation supported')
    masks=[evaluate(samples,x)[1] for x in legs];w=samples['weights']
    allwin=np.logical_and.reduce([m['win'] for m in masks]);loss=np.logical_or.reduce([m['loss'] for m in masks])
    refund=np.logical_and.reduce([m['push']|m['void'] for m in masks]);reduced=~(allwin|loss|refund)
    return {'all_legs_win':float(w[allwin].sum()),'any_leg_loses':float(w[loss].sum()),'all_legs_refund':float(w[refund].sum()),'reduced_ticket':float(w[reduced].sum()),'method':'Same joint simulation and calibration weights; no marginal probability multiplication','payout_note':'Reduced-ticket payout requires venue rules; no fabricated parlay price'}


def settle(market,outcome):
    if market.get('event_id')!=outcome.get('event_id'):raise ValueError('Settlement event mismatch')
    if outcome.get('status')!='FINAL':return {'status':'PENDING'}
    kind=market['kind'];home=float(outcome['home_score']);away=float(outcome['away_score'])
    if not all(math.isfinite(x) and x>=0 and x==int(x) for x in [home,away]):raise ValueError('Invalid final score')
    if kind=='player':
        player=outcome.get('players',{}).get(market['player_id'])
        if player is None:return {'status':'PENDING','reason':'Player result/participation missing'}
        if player.get('participated') is False and market.get('dnp_rule')=='void':return {'status':'VOID','profit_per_unit':0.}
        if player.get('participated') is not True and market.get('dnp_rule')!='action':return {'status':'PENDING','reason':'Participation unverified'}
        if market['stat'] not in player:return {'status':'PENDING','reason':'Stat missing'}
        value=float(player[market['stat']]);line=float(market['line']);side=market['side']
    elif kind=='moneyline':
        value=home-away if market['side']=='home' else away-home;line=0.;side='over'
        if value==0 and market.get('tie_rule')=='loss':return {'status':'LOSS','profit_per_unit':-1.}
        if market.get('tie_rule') not in ['push','loss']:raise ValueError('Missing moneyline tie rule')
    elif kind=='spread':value=(home-away if market['side']=='home' else away-home)+float(market['line']);line=0.;side='over'
    elif kind=='total':value=home+away;line=float(market['line']);side=market['side']
    elif kind=='team_total':value=home if market['team_side']=='home' else away;line=float(market['line']);side=market['side']
    else:raise ValueError('Unknown market')
    if not math.isfinite(value) or not math.isfinite(line):raise ValueError('Invalid settlement value')
    if value==line:return {'status':'PUSH','profit_per_unit':0.}
    win=(value>line) if side=='over' else (value<line)
    return {'status':'WIN' if win else 'LOSS','profit_per_unit':decimal(market['american_odds'])-1 if win else -1.}
