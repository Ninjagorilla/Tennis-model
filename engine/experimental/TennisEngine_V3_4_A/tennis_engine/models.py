"""New reconstructed tennis model. Not original ATP/WTA fitted Champion binaries."""
from __future__ import annotations
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.sparse import csr_matrix
from scipy.special import expit as scipy_expit
from .scoring import exact_match, elo_service_bridge, expit, logit, mix_exact

REFERENCE_COEFFICIENTS={
    'ATP':{'sr_scale':1.283104,'current_state_coefficient_UNAPPLIED':0.134922,
           'w_dense':0.408476,'w_sparse':0.827326},
    'WTA':{'sr_scale':1.140916,'current_state_coefficient_UNAPPLIED':-0.178639,
           'w_dense':0.3424,'w_sparse':0.6054}}
CHAMPION_LABEL='RECONSTRUCTED_SRELO_REFERENCE_PARAMS_V1'
CHALLENGER_LABEL='RECONSTRUCTED_SR_GLM_180D_V1'


def sha256_data(data:dict)->str:
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def save_artifact(path, data:dict):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    wrapper={'payload':data, 'sha256':sha256_data(data)}
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(wrapper,indent=2,sort_keys=True,allow_nan=False),encoding='utf-8')
    tmp.replace(path)


def load_artifact(path)->dict:
    blob=json.loads(Path(path).read_text(encoding='utf-8'))
    if sha256_data(blob['payload'])!=blob['sha256']:
        raise ValueError(f'model artifact hash mismatch: {path}')
    return blob['payload']


def read_csv(path,fields:list[str])->list[dict]:
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f)
        if not rd.fieldnames: raise ValueError(f'empty CSV: {path}')
        missing=set(fields)-set(rd.fieldnames)
        if missing: raise ValueError(f'{path}: missing columns {sorted(missing)}')
        return list(rd)


def checked_date(s:str)->date:
    return date.fromisoformat(s.strip()[:10])


def checked_iso_time(s:str)->datetime:
    ts=datetime.fromisoformat(s.strip().replace('Z','+00:00'))
    if ts.tzinfo is None: raise ValueError('all timestamps must carry UTC offset')
    return ts.astimezone(timezone.utc)


def _feature_values(row:dict)->dict[str,float]:
    server=row['server_id']; receiver=row['receiver_id']; surface=row['surface'].lower()
    tournament=row['tournament_id'];level=row['level'].upper()
    return {f'intercept:{surface}':1.,f'serve_global:{server}':1.,
            f'serve_surface:{surface}:{server}':1.,
            f'return_global:{receiver}':-1.,
            f'return_surface:{surface}:{receiver}':-1.,
            f'tournament:{tournament}':1.,f'level:{level}':1.}


def _as_of_instant(cutoff:date,as_of:datetime | None)->datetime:
    if as_of is None:
        return datetime.combine(cutoff,datetime.min.time(),tzinfo=timezone.utc)
    if as_of.tzinfo is None:raise ValueError('AS_OF_TIME_REQUIRES_UTC_OFFSET')
    return as_of.astimezone(timezone.utc)


def train_glm(rows:list[dict],cutoff:date,half_life:int=365,
              as_of:datetime | None=None)->dict:
    """Weighted grouped-binomial ridge GLM. Different ATP/WTA training artifacts."""
    if not rows: raise ValueError('no training service-point rows')
    tours={r['tour'].upper() for r in rows}
    if len(tours)!=1 or tours.pop() not in ('ATP','WTA'):
        raise ValueError('train_glm requires single ATP or WTA tour')
    as_of=_as_of_instant(cutoff,as_of)
    # Training a GLM directly must not bypass the CLI observation-time checks.
    for row in rows:
        if checked_date(row['date'])>=cutoff or checked_iso_time(row['observed_at'])>=as_of:
            raise ValueError('GLM_TRAINING_LOOKAHEAD_OR_SAME_DAY_CUTOFF')
    all_features=sorted({feat for row in rows for feat in _feature_values(row)})
    lookup={feature:i for i,feature in enumerate(all_features)}
    indptr=[0];indices=[];data=[];success=[];exposure=[];weights=[]
    point_totals=defaultdict(int)
    first_activity={}
    last_activity={}
    for row in rows:
        point_n=int(row['serve_points_total']); won=int(row['serve_points_won'])
        if not (point_n>=1 and 0<=won<=point_n): raise ValueError('invalid service wins/total')
        age=(cutoff-checked_date(row['date'])).days
        if age<0: raise ValueError('future match in fitted rows')
        for player in (row['server_id'],row['receiver_id']):
            point_totals[player]+=point_n
            last_activity[player]=max(last_activity.get(player,'0000'),row['date'])
            first_activity[player]=min(first_activity.get(player,'9999'),row['date'])
        for feat,val in _feature_values(row).items():
            indices.append(lookup[feat]);data.append(val)
        indptr.append(len(indices))
        success.append(won);exposure.append(point_n)
        weights.append(2**(-age/half_life))
    X=csr_matrix((data,indices,indptr),shape=(len(rows),len(all_features)),dtype=float)
    hits=np.array(success,float);totals=np.array(exposure,float); decay=np.array(weights,float)
    penalties=np.array([0. if x.startswith('intercept:') else
        50. if x.startswith(('serve_global:','return_global:')) else 200.
        for x in all_features],float)
    def objective(beta):
        eta=np.clip(X @ beta,-20,20)
        # weighted negative grouped-binomial log-likelihood
        loss=np.sum(decay*(totals*np.logaddexp(0,eta)-hits*eta))+.5*np.sum(penalties*beta*beta)
        gradient=np.asarray(X.T @ (decay*(totals*scipy_expit(eta)-hits))).ravel()+penalties*beta
        return float(loss),gradient
    res=minimize(objective,np.zeros(len(all_features)),jac=True,method='L-BFGS-B',options={'maxiter':350,'ftol':1e-10})
    if not res.success and np.linalg.norm(res.jac,np.inf)>1e-2:
        raise RuntimeError(f'GLM fit failed: {res.message}')
    return {'half_life_days':half_life,'cutoff':cutoff.isoformat(),
            'as_of':as_of.isoformat(),
            'latest_source_observation':max(checked_iso_time(r['observed_at']).isoformat() for r in rows),
            'model_kind':'opponent_adjusted_grouped_binomial_ridge_glm',
            'features':{k:float(res.x[i]) for k,i in lookup.items()},
            'point_exposure':dict(point_totals), 'last_activity':last_activity,
            'first_activity':first_activity,
            'optimizer':{'success':bool(res.success),'message':str(res.message),
                         'iterations':int(res.nit),'gradient_inf':float(np.linalg.norm(res.jac,np.inf))},
            'training_rows':len(rows)}


def predict_serve(model:dict,server:str,receiver:str,surface:str,tournament_id:str,level:str)->float:
    keys=_feature_values({'server_id':server,'receiver_id':receiver,'surface':surface,
                         'tournament_id':tournament_id,'level':level})
    features=model['features']
    # AUDIT NOTE 2026-10-08 (F2): a player WITH history but unseen on a given
    # surface/tournament/level falls back to coefficient 0 for those specific
    # features, i.e. the population-mean effect (ridge prior). That is a deliberate
    # shrinkage choice, not a data fill: the player's own global serve/return
    # coefficients still apply, and Elo flags UNSEEN_SURFACE_PLAYER_A/B separately.
    for player in (server,receiver):
        if player not in model['point_exposure']: raise ValueError(f'NO_SR_HISTORY:{player}')
    if not any(x.startswith('intercept:'+surface.lower()) for x in features):
        raise ValueError(f'UNTRAINED_SURFACE:{surface}')
    log_odds=sum(features.get(k,0.)*v for k,v in keys.items())
    return float(expit(log_odds))


def train_elo(results:list[dict], cutoff:date,as_of:datetime | None=None)->dict:
    """Strict chronological Elo replay, K=24, global + independent surface."""
    as_of=_as_of_instant(cutoff,as_of)
    rating=defaultdict(lambda:1500.)
    counts=defaultdict(int)
    surface_rating=defaultdict(lambda:1500.)
    surface_counts=defaultdict(int)
    used=[]; latest_seen=None
    for r in sorted(results,key=lambda x:(x['date'],x['match_id'])):
        tour=r['tour'].upper();winner=r['winner_id'];loser=r['loser_id'];surf=r['surface'].lower()
        if tour not in ('ATP','WTA') or not winner or not loser or winner==loser:
            raise ValueError('invalid Elo result row')
        if surf not in ('hard','clay','grass'):
            raise ValueError('UNKNOWN_SURFACE_IN_ELO')
        if r['status'].lower()!='completed': continue
        if not checked_date(r['date'])<cutoff: continue
        # A timestamp on the cutoff date is not sufficient: a result may have
        # become observable *after* the match we are trying to predict.
        observed=checked_iso_time(r['observed_at'])
        if observed>=as_of: continue
        a=(tour,winner);b=(tour,loser)
        sa=(tour,surf,winner);sb=(tour,surf,loser)
        pa=1/(1+10**((rating[b]-rating[a])/400))
        ps=1/(1+10**((surface_rating[sb]-surface_rating[sa])/400))
        rating[a]+=24*(1-pa);rating[b]-=24*(1-pa)
        surface_rating[sa]+=24*(1-ps);surface_rating[sb]-=24*(1-ps)
        counts[a]+=1;counts[b]+=1
        surface_counts[sa]+=1;surface_counts[sb]+=1
        used.append(r['match_id'])
        latest_seen=max(latest_seen,observed) if latest_seen else observed
    return {'cutoff':cutoff.isoformat(),'k':24,'initial':1500,
            'as_of':as_of.isoformat(),
            'latest_source_observation':latest_seen.isoformat() if latest_seen else None,
            'global':{'|'.join(k):v for k,v in rating.items()},
            'surface':{'|'.join(k):v for k,v in surface_rating.items()},
            'global_count':{'|'.join(k):v for k,v in counts.items()},
            'surface_count':{'|'.join(k):v for k,v in surface_counts.items()},
            'result_count':len(used),'result_ids_hash':hashlib.sha256('\n'.join(used).encode()).hexdigest()}


def elo_prob(elo:dict,tour:str,surface:str,a:str,b:str):
    tour=tour.upper();surf=surface.lower()
    g=elo['global'];s=elo['surface']
    ga=f'{tour}|{a}';gb=f'{tour}|{b}'
    if ga not in g or gb not in g: raise ValueError('MISSING_ESTABLISHED_ELO_HISTORY')
    sa=f'{tour}|{surf}|{a}';sb=f'{tour}|{surf}|{b}'
    flags=[]
    if sa not in s: flags.append('UNSEEN_SURFACE_PLAYER_A')
    if sb not in s: flags.append('UNSEEN_SURFACE_PLAYER_B')
    ra=.5*(g[ga]+s.get(sa,1500.))
    rb=.5*(g[gb]+s.get(sb,1500.))
    return 1/(1+10**((rb-ra)/400)),flags


def scale_contrast(a:float,b:float,scale:float)->tuple[float,float]:
    mean=(logit(a)+logit(b))/2
    diff=(logit(a)-logit(b))*scale
    return expit(mean+diff/2),expit(mean-diff/2)


def score_match(fixture:dict, model_package:dict)->dict:
    tour=fixture['tour'].upper()
    surface=fixture['surface'].lower()
    if surface not in ('hard','clay','grass'): raise ValueError('UNKNOWN_SURFACE')
    if tour not in ('ATP','WTA'): raise ValueError('UNSUPPORTED_TOUR')
    if fixture['format'] not in ('bo3','bo5'):
        raise ValueError('UNSUPPORTED_FORMAT (regular bo3 or bo5 only)')
    best_of=int(fixture['format'][-1])
    if fixture['level'].upper()=='ITF':
        raise ValueError('ITF_NOT_VALIDATED_FOR_FORECAST')
    a,b=fixture['player_a_id'],fixture['player_b_id']
    if not a or not b or a==b: raise ValueError('AMBIGUOUS_PLAYER_IDENTITIES')
    champion_model=model_package['sr_champion'][tour]
    challenger_model=model_package['sr_challenger'][tour]
    p_a=predict_serve(champion_model,a,b,surface,fixture['tournament_id'],fixture['level'])
    p_b=predict_serve(champion_model,b,a,surface,fixture['tournament_id'],fixture['level'])
    # Coefficients borrowed as documented reference values; original current-state
    # transform is intentionally UNAPPLIED without original feature definition.
    reference=REFERENCE_COEFFICIENTS[tour]
    p_sr_a,p_sr_b=scale_contrast(p_a,p_b,reference['sr_scale'])
    sr=exact_match(p_sr_a,p_sr_b,best_of)
    eprob,flags=elo_prob(model_package['elo'],tour,surface,a,b)
    common_service=(logit(p_sr_a)+logit(p_sr_b))/2
    bridge_a,bridge_b=elo_service_bridge(eprob,expit(common_service),best_of)
    el=exact_match(bridge_a,bridge_b,best_of)
    n=min(champion_model['point_exposure'].get(a,0), champion_model['point_exposure'].get(b,0))
    weight=reference['w_dense']+(reference['w_sparse']-reference['w_dense'])*1000/(1000+n)
    combined=mix_exact(sr,el,weight)
    cs_a=predict_serve(challenger_model,a,b,surface,fixture['tournament_id'],fixture['level'])
    cs_b=predict_serve(challenger_model,b,a,surface,fixture['tournament_id'],fixture['level'])
    challenger=exact_match(cs_a,cs_b,best_of)
    flags+=['RECONSTRUCTED_NOT_ORIGINAL_CHAMPION', 'ORIGINAL_CURRENT_STATE_FEATURE_UNAVAILABLE',
            'ELO_TO_SERVICE_BRIDGE_RECONSTRUCTED']
    if n<5000: flags.append('SPARSE_POINT_EXPOSURE_DIAGNOSTIC')
    gap=abs(combined['p_a']-challenger['p_a'])
    if gap>=.08: flags.append('CHAMPION_CHALLENGER_DISAGREEMENT_GE_8PP')
    if (combined['p_a']-.5)*(challenger['p_a']-.5)<0:
        flags.append('MODEL_WINNER_REVERSAL')
    data_quality={'minimum_historical_point_exposure':n,
                  'surface_elo_matches_A':model_package['elo']['surface_count'].get(f'{tour}|{surface}|{a}',0),
                  'surface_elo_matches_B':model_package['elo']['surface_count'].get(f'{tour}|{surface}|{b}',0),
                  'source_age_days_since_training':(checked_date(fixture['start_at'].strip()[:10])-checked_date(champion_model['cutoff'])).days,
                  'quality_status':'caution' if flags else 'reviewed'}
    return {'model_id':CHAMPION_LABEL,'challenger_id':CHALLENGER_LABEL,
            'fixture':fixture,'p_a':combined['p_a'],'p_b':combined['p_b'],
            'pick':a if combined['p_a']>=.5 else b,
            'challenger_p_a':challenger['p_a'], 'sr_p_a':sr['p_a'],'elo_p_a':eprob,
            'elo_weight':weight,'sr_service_a':p_sr_a,'sr_service_b':p_sr_b,
            'elo_bridge_service_a':bridge_a,'elo_bridge_service_b':bridge_b,
            'exact':combined,'data_quality':data_quality,'fragility_flags':flags,
            'coefficient_provenance':'documented reference coefficients, reconstructed SR fit and scoring bridge',
            'fitness_adjustment':'none; unavailable original feature and verified numeric transform'}
