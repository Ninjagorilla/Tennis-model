"""V3.4-A EXPERIMENTAL serve/return form Challenger.

A deliberately separate, UNCALIBRATED research-only model. Computes historical
opponent-adjusted point residuals using the frozen SR model, with Bayesian pooling,
recency weights, tier-transfer discounts and last 5/10/15 descriptive diagnostics.
Never edits the reference SR-Elo Champion or the prospective prediction ledger.

Archive date caveat: tourney_date frequently denotes the *tournament week*;
within-event chronology and exact recent workload cannot be inferred from it.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime
from math import exp, log
from .models import predict_serve
from .scoring import expit, logit, exact_match, mix_exact

VERSION='V3.4-A_EXPERIMENTAL_DYNAMIC_RESIDUALS_1'
# Provisional hyperparameters. These are not fitted Champion values.
PARAMS={'prior_point_exposure':650.,'form_half_life_days':120.,
        'last_n_weights':(0.5,0.3,0.2), 'logit_adjustment_slope':0.30,
        'max_player_logit_shift':0.16,'maximum_total_logit_shift':0.25,
        'cross_tier_exposure_factor':0.65,'old_results_taper_after_days':90}


def past_only(rows, cutoff, *, strict_observed_as_of=None):
    """Only prior dated rows. Strict mode additionally enforces observed_at.

    Research archive rows were ingested after their original match times and
    are therefore NEVER retroactively certified prospective by this function.
    """
    cutoff=date.fromisoformat(str(cutoff)[:10])
    result=[]
    for r in rows:
        try:
            dt=date.fromisoformat(r['date'][:10])
            if dt>=cutoff: continue
            if strict_observed_as_of is not None:
                obs=datetime.fromisoformat(r['observed_at'].replace('Z','+00:00'))
                if obs>=strict_observed_as_of:continue
        except (KeyError,ValueError,TypeError): continue
        result.append(r)
    return result


def approximate_opponent_quality(results, cutoff):
    """Prior-tournament-date Elo as opponent quality, *not* final rating.

    Because archive dates may be tournament week starts, all matches sharing
    a date use a rating frozen before that date. This avoids leaking earlier
    or later same-event results into the displayed opponent quality metric.
    """
    played=sorted(past_only(results,cutoff),key=lambda x:(x['date'],x['match_id']))
    ratings=defaultdict(lambda:1500.); quality={};i=0
    while i<len(played):
        j=i+1
        while j<len(played) and played[j]['date']==played[i]['date']:j+=1
        group=played[i:j]
        for r in group:
            quality[r['match_id']]={'winner_opponent_elo':ratings[r['loser_id']],
                'loser_opponent_elo':ratings[r['winner_id']],
                'winner_pre_elo':ratings[r['winner_id']],
                'loser_pre_elo':ratings[r['loser_id']]}
        # Deterministic updates, but quality for same date is prior-date only.
        for r in group:
            a,b=r['winner_id'],r['loser_id']
            pa=1/(1+10**((ratings[b]-ratings[a])/400))
            ratings[a]+=24*(1-pa);ratings[b]-=24*(1-pa)
        i=j
    return quality


def _row_delta(svc, ret, model):
    try:
        exp_serve=predict_serve(model,svc['server_id'],svc['receiver_id'],
                   svc['surface'],svc['tournament_id'],svc['level'])
        n=int(svc['serve_points_total']);wins=int(svc['serve_points_won'])
        if n<1 or not 0<=wins<=n:return None
        return (wins/n-exp_serve,n)
    except (KeyError,ValueError):return None


def _tier_factor(observed_level, target_level):
    # Only discounts reliability; does not claim a learnt tour-to-tour skill offset.
    return 1. if observed_level==target_level else PARAMS['cross_tier_exposure_factor']


def _form_windows(match_rows, point_rows, model, pid, surface, target_level, cutoff, quality):
    cutoff=date.fromisoformat(str(cutoff)[:10])
    samples=[]
    for match in sorted(match_rows,key=lambda r:(r['date'],r['match_id']),reverse=True)[:60]:
        dt=date.fromisoformat(match['date'][:10]);days=(cutoff-dt).days
        won=match['winner_id']==pid
        opp=match['loser_id'] if won else match['winner_id']
        q=quality.get(match['match_id'],{})
        opp_elo=q.get('winner_opponent_elo' if won else 'loser_opponent_elo')
        sres=rres=None;sn=rn=0
        rows=point_rows.get(match['match_id'],[])
        for rec in rows:
            if rec['server_id']==pid:
                delta=_row_delta(rec,None,model)
                if delta:sres,sn=delta
            if rec['receiver_id']==pid:
                delta=_row_delta(rec,None,model)
                if delta:rres,rn=(-delta[0],delta[1])
        samples.append({'date':match['date'],'days_ago':days,'match_id':match['match_id'],
                        'won':won,'opponent_id':opp,'opponent_pre_event_elo':opp_elo,
                        'surface':match['surface'],'level':match['level'],
                        'serve_residual':sres,'return_residual':rres,
                        'serve_points':sn,'return_points':rn})
    def summary(slice_rows):
        n=len(slice_rows);wins=sum(x['won'] for x in slice_rows)
        q=[x['opponent_pre_event_elo'] for x in slice_rows if x['opponent_pre_event_elo'] is not None]
        return {'matches':n,'wins':wins,'win_rate':wins/n if n else None,
            'mean_opponent_prior_elo':sum(q)/len(q) if q else None,
            'verified_point_stat_matches':sum(x['serve_residual'] is not None and x['return_residual'] is not None for x in slice_rows)}
    results={'all':{f'last_{n}':summary(samples[:n]) for n in (5,10,15)},
             'surface':{f'last_{n}':summary([x for x in samples if x['surface']==surface][:n]) for n in (5,10,15)}}
    selected=samples[:15]
    def calculate(side,window):
        part=selected[:window];numerator=denominator=0.;eff=0.
        for m in part:
            resid=m[f'{side}_residual'];n=m[f'{side}_points']
            if resid is None or not n:continue
            decay=2**(-m['days_ago']/PARAMS['form_half_life_days'])
            surf_factor=1.0 if m['surface']==surface else 0.40
            tier_factor=_tier_factor(m['level'],target_level)
            weight=decay*surf_factor*tier_factor*n
            numerator+=weight*resid;denominator+=weight
            eff+=weight
        if denominator==0:return 0.,0.
        # Normal prior of 0 recent residual, with point-count-based pooling.
        return numerator/(denominator+PARAMS['prior_point_exposure']),eff
    effective={'serve':0.,'return':0.}
    shifts={}
    for side in ('serve','return'):
        ws=PARAMS['last_n_weights']; windows=[calculate(side,n) for n in (5,10,15)]
        # overlapping windows intentional; multiscale smoothers, not independent samples.
        residual=sum(w*value for w,(value,eff) in zip(ws,windows))
        effective[side]=max(x[1] for x in windows)
        # Convert point-probability residual into approximate logit adjustment,
        # conservative provisional slope; needs prospective fitting.
        shift=max(-PARAMS['max_player_logit_shift'],min(PARAMS['max_player_logit_shift'],
                PARAMS['logit_adjustment_slope']*residual/(.65*.35)))
        if selected:
            age=selected[0]['days_ago']
            if age>PARAMS['old_results_taper_after_days']:
                shift*=exp(-(age-PARAMS['old_results_taper_after_days'])/90)
        shifts[side]=shift
    latest=selected[0]['date'] if selected else None
    known_dates={x['date'] for x in selected}
    recent_7=sum(0<=x['days_ago']<=7 for x in selected)
    recent_14=sum(0<=x['days_ago']<=14 for x in selected)
    recent_tiers=[x['level'] for x in selected[:10]]
    flags=[]
    if not selected:flags.append('NO_RESULT_HISTORY')
    if effective['serve']<200 or effective['return']<200:flags.append('SPARSE_OPPONENT_ADJUSTED_POINT_RESIDUALS')
    if selected and selected[0]['days_ago']>45:flags.append('RECENT_RESULTS_OLDER_THAN_45_DAYS')
    if selected and any(x['level']!=target_level for x in selected[:5]): flags.append('CROSS_TIER_TRANSFER_UNCERTAINTY')
    if selected and sum(x['surface']==surface for x in selected[:15])<5:flags.append('LIMITED_RECENT_SURFACE_MATCHES')
    if any(x['match_id'].startswith('TML') for x in selected):flags.append('TML_DATE_PRECISION_UNVERIFIED')
    return {'player_id':pid,'model_id':VERSION,'cutoff_exclusive':cutoff.isoformat(),
        'latest_result_date_proxy':latest,'windows':results,
        'recent_level_mix':{t:recent_tiers.count(t) for t in sorted(set(recent_tiers))},
        'recent_match_rows_7d_DATE_PROXY':recent_7,'recent_match_rows_14d_DATE_PROXY':recent_14,
        'different_observed_date_buckets':len(known_dates),
        'effective_exposure':effective,'serve_logit_shift':shifts['serve'],
        'return_logit_shift':shifts['return'],'flags':flags,
        'match_detail':selected[:15]}


def prepare_form_history(history,cutoff):
    results=past_only(history['results'],cutoff)
    points=defaultdict(list)
    for rec in past_only(history['points'],cutoff):points[rec['match_id']].append(rec)
    by_player=defaultdict(list)
    for r in results:
        by_player[r['winner_id']].append(r);by_player[r['loser_id']].append(r)
    return {'quality':approximate_opponent_quality(results,cutoff),'points':points,'by_player':by_player}


def build_dynamic_projection(fixture, pkg, history, cutoff, quality=None, prepared=None):
    """Compute a completely separate V3.4-A exact scoring distribution.

    Never write this to the Champion field. No market prices are consulted.
    """
    from .models import score_match
    tour=fixture['tour'].upper();surf=fixture['surface'].lower()
    if history['tour']!=tour:raise ValueError('CROSS_TOUR_HISTORY')
    cutoff=date.fromisoformat(str(cutoff)[:10]); a=fixture['player_a_id'];b=fixture['player_b_id']
    base=score_match(fixture,pkg)
    prepared=prepared if prepared is not None else prepare_form_history(history,cutoff)
    point_rows=prepared['points'];by_player=prepared['by_player']
    quality=quality if quality is not None else prepared['quality']
    model=pkg['sr_champion'][tour]
    da=_form_windows(by_player[a],point_rows,model,a,surf,fixture['level'],cutoff,quality)
    db=_form_windows(by_player[b],point_rows,model,b,surf,fixture['level'],cutoff,quality)
    shift_a=max(-PARAMS['maximum_total_logit_shift'],min(PARAMS['maximum_total_logit_shift'],
                 da['serve_logit_shift']-db['return_logit_shift']))
    shift_b=max(-PARAMS['maximum_total_logit_shift'],min(PARAMS['maximum_total_logit_shift'],
                 db['serve_logit_shift']-da['return_logit_shift']))
    spa=expit(logit(base['sr_service_a'])+shift_a)
    spb=expit(logit(base['sr_service_b'])+shift_b)
    sr=exact_match(spa,spb,int(fixture['format'][-1]))
    # Elo synthetic bridge stays frozen, avoids a second calibration or re-fit.
    bridge=exact_match(base['elo_bridge_service_a'],base['elo_bridge_service_b'],int(fixture['format'][-1]))
    exact=mix_exact(sr,bridge,base['elo_weight'])
    flags=list(sorted(set(da['flags']+db['flags'])))
    if abs(exact['p_a']-base['p_a'])>=.03:flags.append('EXPERIMENTAL_DYNAMIC_VS_BASELINE_GE_3PP')
    return {'model_id':VERSION,'status':'EXPERIMENTAL_UNCALIBRATED_RESEARCH_ONLY',
            'p_a':exact['p_a'],'p_b':exact['p_b'],'pick':a if exact['p_a']>=.5 else b,
            'reference_p_a':base['p_a'],'baseline_challenger_p_a':base['challenger_p_a'],
            'service_probabilities':{'sr_a':spa,'sr_b':spb,'elo_bridge_a':base['elo_bridge_service_a'],
                                     'elo_bridge_b':base['elo_bridge_service_b'],'elo_weight':base['elo_weight']},
            'exact':exact,'player_a':da,'player_b':db,'flags':flags,
            'provisional_parameters':PARAMS.copy(),
            'data_time_limit':'TOURNAMENT_DATE_PROXY; NOT HISTORICALLY_VERIFIED_PUBLICATION_SNAPSHOT',
            'no_market_inputs':True,'certified_prospective':False}
