"""User-authorized Champion SR-Elo 1.0, independently pinned from SR Challenger.

Completion-conditional ML is a sample-sensitive mixture of jointly estimated
serve/return skill and a separate historical result-Elo prior. All coefficients
were fitted on 2024 held-forward observations. No bookmaker features enter.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import math
import numpy as np
import pandas as pd
from scipy.special import expit
from .common import ROOT, digest, filehash, no_market_fields, probability, relative_path, timestamp, utcnow, write_new
from .semantics import COMPLETION
from tennis_sr.core import ServeReturnModel
from tennis_sr.evaluate import Elo
from tennis_sr.scoring import match_p, predict_distribution

VERSION = 'Tennis Champion SR-Elo 1.0'


def point_contrast_for_match_probability(common: float, target: float, best_of: int, deciding: int) -> tuple[float,float]:
    """Elo-to-score scenario mapping. Not independently estimated serve skill."""
    target=probability(float(target))
    target=min(1-1e-10,max(1e-10,target))
    lo,hi=-10.,10.
    for _ in range(64):
        mid=(lo+hi)/2
        pa,pb=float(expit(common+mid)),float(expit(common-mid))
        if float(match_p(pa,pb,best_of,deciding)) < target:lo=mid
        else:hi=mid
    mid=(lo+hi)/2
    return float(expit(common+mid)),float(expit(common-mid))


def mixture_distribution(sr: dict, elo: dict, weight: float) -> dict:
    if not 0<=weight<=1:raise ValueError('INVALID_MIXTURE_WEIGHT')
    if set(sr['scorelines'])!=set(elo['scorelines']):raise ValueError('SCORING_TARGET_MISMATCH')
    result={k:(1-weight)*float(sr[k])+weight*float(elo[k]) for k in ['p_a','p_b','expected_total_games','p_at_least_one_tiebreak']}
    result['scorelines']={k:(1-weight)*v+weight*elo['scorelines'][k] for k,v in sr['scorelines'].items()}
    result.update(conditional_on_completion=True,settlement_model='not_inferred',
                  score_distribution_status='COHERENT_MODEL_OUTPUT_NOT_INDEPENDENTLY_CALIBRATED_FOR_TOTALS_OR_SETS')
    if abs(result['p_a']+result['p_b']-1)>1e-10:raise ValueError('PROBABILITY_MASS_ERROR')
    return result


def ordered_elo_history(data:pd.DataFrame,as_of:str)->pd.DataFrame:
    """Admission uses observation/release times; rating replay uses sporting chronology.

    Forward snapshots use capture times as release times. Sorting ratings by those
    capture times would replay yearly files in download order. Match/tournament-day
    labels are retained as coarse labels, with match_id resolving same-day ties just
    as in the historical baseline. This does not invent within-day match timestamps.
    """
    g=data.copy(); cutoff=pd.Timestamp(as_of)
    observed=pd.to_datetime(g.source_observed_at,utc=True,format='mixed')
    released=pd.to_datetime(g.historical_release,utc=True,format='mixed')
    played=pd.to_datetime(g.tournament_date,utc=True,format='mixed')
    if observed.isna().any() or released.isna().any() or played.isna().any():
        raise ValueError('INVALID_ELO_CHRONOLOGY')
    if (observed>cutoff).any():raise ValueError('ELO_FUTURE_OBSERVATION')
    admitted=(released<=cutoff)&(played<=cutoff)
    g=g.loc[admitted].copy();g['_event_order']=played.loc[admitted]
    return g.sort_values(['_event_order','match_id']).drop(columns=['_event_order'])


def save_elo_history(registration: dict, tour: str, target: Path) -> dict:
    receipt=registration['history_receipt']; p=relative_path(receipt['history_file'])
    if filehash(p)!=receipt['history_sha256']:raise ValueError('ELO_HISTORY_HASH_MISMATCH')
    data=pd.read_csv(p,low_memory=False)
    if 'logical_key' in data and data.logical_key.duplicated().any():raise ValueError('ELO_DUPLICATE_HISTORY')
    data=data[data.tour==tour].copy()
    data['source_observed_at']=pd.to_datetime(data.source_observed_at,utc=True,format='mixed')
    data['historical_release']=pd.to_datetime(data.historical_release,utc=True,format='mixed')
    if (data.source_observed_at>pd.Timestamp(receipt['as_of'])).any():raise ValueError('ELO_FUTURE_OBSERVATION')
    eligible=ordered_elo_history(data,receipt['as_of'])
    e=Elo(); counts={}
    for row in eligible.itertuples():
        if row.y not in (0,1) or not str(row.player_a).startswith(tour+':') or not str(row.player_b).startswith(tour+':'):
            raise ValueError('ELO_BAD_ROW')
        e.update(row)
        for p in (row.player_a,row.player_b):counts[p]=counts.get(p,0)+1
    payload={'schema':'tennis-historical-elo-v1','tour':tour,'as_of':receipt['as_of'],'history_sha256':receipt['history_sha256'],
             'algorithm':'Inherited historical baseline: K=24, 50/50 global/surface, neutral=1500; no market',
             'rows':len(eligible),'replay_order':'tournament_date then canonical match_id; observation times gate availability only', 'global':dict(e.global_),'surface':[[a,s,v] for (a,s),v in e.surface.items()],
             'counts':counts,'latest_event_label':str(eligible.tournament_date.max()),'coverage_complete':False}
    write_new(target,payload)
    return {'path':str(target.relative_to(ROOT)),'sha256':filehash(target),'as_of':receipt['as_of'],'rows':len(eligible)}


class ChampionModel:
    def __init__(self,registration:dict,tour:str):
        r=registration['models'][tour+'_CHAMPION_REGISTERED']
        if r['role']!='CHAMPION' or r['tour']!=tour or r['version']!=VERSION:raise ValueError('CHAMPION_IDENTITY_MISMATCH')
        auth=relative_path(registration['replacement_authorization']['path'])
        if filehash(auth)!=registration['replacement_authorization']['sha256']:raise ValueError('CHAMPION_AUTHORIZATION_HASH_MISMATCH')
        authdata=json.loads(auth.read_text())
        if authdata.get('replacement_explicitly_authorized') is not True or authdata.get('new_champion')!=VERSION:raise ValueError('CHAMPION_REPLACEMENT_NOT_AUTHORIZED')
        for field in ('parameters','elo_state'):
            p=relative_path(r[field]['path'])
            if filehash(p)!=r[field]['sha256']:raise ValueError('CHAMPION_'+field.upper()+'_HASH_MISMATCH')
        for item in r['source_files']:
            if filehash(relative_path(item['path']))!=item['sha256']:raise ValueError('CHAMPION_SOURCE_HASH_MISMATCH')
        params=json.loads(relative_path(r['parameters']['path']).read_text())
        if params['tour']!=tour or params['model']!=VERSION or not params.get('optimizer_success'):raise ValueError('INVALID_CHAMPION_PARAMETERS')
        self.params=params['parameters']
        a,b,wd,ws=[self.params[k] for k in ('scale','beta','w_dense','w_sparse')]
        if not all(math.isfinite(v) for v in (a,b,wd,ws)) or not (.2<=a<=2.5 and -5<=b<=5 and 0<=wd<=.45 and wd<=ws<=.95):raise ValueError('CHAMPION_PARAMETER_BOUNDS')
        source=[]
        for field in ('core','state'):
            info=r[field];p=relative_path(info['artifact'])
            if filehash(p/'model.json')!=info['metadata_sha256'] or filehash(p/'weights.json')!=info['weights_sha256']:raise ValueError('CHAMPION_BASE_HASH_MISMATCH')
            m=ServeReturnModel.load(p)
            if m.tour!=tour or not m.fit_receipt.get('optimizer_success'):raise ValueError('CHAMPION_UNQUALIFIED_BASE_FIT')
            source.append(m)
        core,state=source
        for field in ('players','contexts','regimes','fit_receipt'):
            if getattr(core,field)!=getattr(state,field):raise ValueError('CHAMPION_BASE_MAPPING_MISMATCH')
        if not np.array_equal(core.coefficients,state.coefficients):raise ValueError('CHAMPION_BASE_COEFFICIENT_MISMATCH')
        self.model=core # Independent object; never change Challenger state.
        self.model.recent=copy.deepcopy(state.recent)
        self.model.calibration_scale=float(a);self.model.form_beta=float(b)
        self.elo=json.loads(relative_path(r['elo_state']['path']).read_text())
        if self.elo['tour']!=tour or self.elo['as_of']!=r['elo_state']['as_of']:raise ValueError('CHAMPION_ELO_TOUR_OR_TIME')
        self.surfaces={(p,s):v for p,s,v in self.elo['surface']}
        self.registration=r;self.tour=tour
        self.identity_hash=digest(r)
        self.input_state_time=max(timestamp(r['state']['as_of']),timestamp(self.elo['as_of']))
        self.fit_time=timestamp(core.fit_receipt['cutoff']+'Z')

    def elo_probability(self,event:dict):
        a,b,s=event['player_a'],event['player_b'],event['surface']
        ra=.5*self.elo['global'].get(a,1500.)+.5*self.surfaces.get((a,s),1500.)
        rb=.5*self.elo['global'].get(b,1500.)+.5*self.surfaces.get((b,s),1500.)
        p=float(expit((ra-rb)*math.log(10)/400))
        if event['best_of']==5:
            lo,hi=0.,1.
            for _ in range(40):
                q=(lo+hi)/2
                if q*q*(3-2*q)<p:lo=q
                else:hi=q
            q=(lo+hi)/2;p=q**3*(1+3*(1-q)+6*(1-q)**2)
        return p,ra,rb

    def explain(self,event:dict):
        no_market_fields(event)
        if event['tour']!=self.tour or any(not event[k].startswith(self.tour+':') for k in ('player_a','player_b')):raise ValueError('CROSS_TOUR_CHAMPION_INPUT')
        if event['player_a']==event['player_b']:raise ValueError('DUPLICATE_PLAYER')
        if event['regime'] not in self.registration['scopes']:raise ValueError('UNSUPPORTED_CHAMPION_SCOPE')
        now=timestamp(utcnow())
        if self.fit_time>now or self.input_state_time>now:raise ValueError('FUTURE_CHAMPION_STATE')
        start=event.get('starts_at') or event.get('not_before_at')
        if start and max(self.fit_time,self.input_state_time)>=timestamp(start):raise ValueError('CHAMPION_INPUT_AFTER_START')
        base=self.model.explain(event)
        e,ra,rb=self.elo_probability(event)
        common=(math.log(base['point_probability_raw_a']/(1-base['point_probability_raw_a']))+math.log(base['point_probability_raw_b']/(1-base['point_probability_raw_b'])))/2
        pa,pb=point_contrast_for_match_probability(common,e,event['best_of'],event['deciding_tiebreak_target'])
        ed=predict_distribution(pa,pb,event['best_of'],event['deciding_tiebreak_target'])
        n=base['minimum_historical_points'];wd,ws=self.params['w_dense'],self.params['w_sparse']
        w=wd+(ws-wd)*1000/(1000+n)
        dist=mixture_distribution(base['distribution'],ed,w)
        stresses={k:(1-w)*p+w*e for k,p in base['stress_tests_not_primary'].items()}
        for label,shift in [('elo_a_minus_50',-50),('elo_a_plus_50',50)]:
            # Sensitivity in probability-logit units; not an observed ratings change.
            ep=float(expit(math.log(e/(1-e))+shift*math.log(10)/400))
            stresses[label]=(1-w)*base['distribution']['p_a']+w*ep
        raw=self.model.predict(pd.DataFrame([event]),scale=self.params['scale'],beta=0.)['p'][0]
        noform=(1-w)*float(raw)+w*e
        gaps=[abs(dist['p_a']-p) for p in stresses.values()]
        reversal=any((p>=.5)!=(dist['p_a']>=.5) for p in stresses.values())
        risks=['Current history coverage is partial and fitness is unverified.',
               'College/junior translation and medical readiness are not fitted or applied.',
               'Model scores are conditional on completion; operator settlement rules are separate.',
               'Elo and point history share matches; agreement is not independent confirmation.']
        if n<1000:risks.append('Sparse point history: more weight is assigned to the separately observed result-rating prior.')
        if reversal:risks.append('A modest component stress reverses the preferred player.')
        return {'version':VERSION,'target':COMPLETION,'distribution':dist,'serve_return_component':base,
                'elo_component':{'p_a':e,'rating_a':ra,'rating_b':rb,'weight':w,'history_rows':self.elo['rows'],
                                 'synthetic_scoring_service_a':pa,'synthetic_scoring_service_b':pb,
                                 'scoring_service_rates_are_not_observed_skill_estimates':True},
                'serve_return_weight':1-w,'minimum_historical_points':n,
                'calibration_parameters':self.params,'final_probability_formula':'(1-elo_weight)*SR_probability+elo_weight*Elo_probability',
                'calibration_applied_once':True,'market_inputs_used':False,
                'ablations':{'without_elo':base['distribution']['p_a'],'without_current_state':noform,'elo_only':e},
                'stress_tests_not_primary':stresses,'stress_range_not_confidence_interval':[min(stresses.values()),max(stresses.values())],
                'side_reversal_under_stress':reversal,'fragility':'HIGH' if reversal or n<1000 else 'MODERATE',
                'evidence_grade':'B' if n>=1000 else 'C' if n>=200 else 'D',
                'risks':risks,'history_coverage_complete':False,'fitness_verified':False,
                'new_operational_champion_not_recovered_v78':True}

    def predict(self,event:dict):
        out=self.explain(event)
        return {'status':'EXECUTED_VERIFIED_REPLACEMENT_CHAMPION','model_id':self.registration['model_id'],
                'version':VERSION,'role':'CHAMPION','p_a':probability(out['distribution']['p_a']),
                'target':COMPLETION,'artifact_sha256':self.identity_hash,'executable_verified':True,
                'trained_through':self.fit_time.isoformat(),'state_observed_at':self.input_state_time.isoformat(),
                'history_coverage_certified':False,'betting_certified':False,'native_output':out,'breakdown':out}


def register_replacement(registration:dict,run_id:str,authorization:dict) -> dict:
    """Pin real artifact bindings. Used both on activation and routine state refresh."""
    sources=['tennis_ops/champion.py','vendor/sr/tennis_sr/core.py','vendor/sr/tennis_sr/scoring.py','vendor/sr/tennis_sr/evaluate.py']
    for tour in ('ATP','WTA'):
        prior=registration['models'].get(tour+'_CHAMPION_REGISTERED')
        # Learned meta-parameters survive future routine refresh unchanged.
        param=copy.deepcopy(prior['parameters']) if prior else {'path':f'champion/artifacts/{tour}_blend.json','sha256':filehash(ROOT/f'champion/artifacts/{tour}_blend.json')}
        elo=save_elo_history(registration,tour,ROOT/'champion/artifacts'/f'{run_id}_{tour}_elo.json')
        registration['models'][tour+'_CHAMPION_REGISTERED']={
            'model_id':tour+'_CHAMPION_SRELO_1_0','version':VERSION,'role':'CHAMPION','tour':tour,'target':COMPLETION,
            'scopes':['main','challenger','wta125','main_qualifying','challenger_qualifying','wta125_qualifying','itf','itf_qualifying'],
            'parameters':param,'elo_state':elo,
            'core':copy.deepcopy(registration['models'][tour+'_SR_CORE_REGISTERED']),
            'state':copy.deepcopy(registration['models'][tour+'_SR_STATE_OBSERVED']),
            'source_files':[{'path':p,'sha256':filehash(ROOT/p)} for p in sources],
            'history_complete':False,'prospective_superiority_proven':False,'operational_replacement':True}
    registration['replacement_authorization']=authorization
    registration['governance_champion']={'version':VERSION,'binding':{t:t+'_CHAMPION_SRELO_1_0' for t in ('ATP','WTA')},
            'selection_basis':'Explicit user authorization; new named operational replacement, not v7.8 recovery.',
            'retired_designation':'v7.8 RFG-HC-LT','original_artifact_recovered':False,'statistical_superiority_proven':False}
    registration['runtime_version']='Tennis Paired Runtime 2.0'
    return registration
