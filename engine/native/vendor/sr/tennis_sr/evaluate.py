"""Predeclared quarterly walk-forward development, calibration, and held-out replay."""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict
from collections import defaultdict
import json,hashlib,time
import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.optimize import minimize, minimize_scalar
from .core import ServeReturnModel,Config
from .scoring import batch_match

PRIMARY={'main','challenger','wta125','main_qualifying','challenger_qualifying','wta125_qualifying'}
CONFIGS=[Config(180,50,200),Config(365,50,200),Config(365,200,500),Config(730,50,200)]


def load_data(root:Path):
    d=pd.read_csv(root/'data/matches.csv.gz',low_memory=False,parse_dates=['tournament_date','historical_release'])
    return d

def metrics(y,p):
    y=np.asarray(y,float);p=np.clip(np.asarray(p,float),1e-12,1-1e-12)
    if not len(y):return {'n':0}
    bins=np.minimum((p*10).astype(int),9);ece=0.
    curve=[]
    for i in range(10):
        sel=bins==i
        if sel.any():
            avg=float(p[sel].mean());actual=float(y[sel].mean());n=int(sel.sum())
            ece+=n/len(y)*abs(avg-actual)
            curve.append({'bin_low':i/10,'bin_high':(i+1)/10,'n':n,'mean_probability':avg,'observed_frequency':actual})
    return {'n':len(y),'brier':float(np.mean((p-y)**2)),'log_loss':float(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p))),
            'accuracy':float(np.mean((p>=.5)==y)),'ece_10_bins':float(ece),'calibration_curve':curve}

def point_logloss(events,ea,eb):
    num=0.;den=0.
    for side,eta in [('a',ea),('b',eb)]:
        k=events[f'{side}_serve_won'].to_numpy(float);n=events[f'{side}_serve_total'].to_numpy(float)
        valid=np.isfinite(k)&np.isfinite(n)
        num+=float(np.sum(n[valid]*np.logaddexp(0,eta[valid])-k[valid]*eta[valid]));den+=float(n[valid].sum())
    return num,den

class Elo:
    """Reconstructed historical surface Elo, not today's Tennis Abstract ratings."""
    def __init__(self):self.global_=defaultdict(lambda:1500.);self.surface=defaultdict(lambda:1500.)
    def update(self,r):
        a,b,s=r.player_a,r.player_b,r.surface;y=r.y
        for table,x,z in [(self.global_,a,b),(self.surface,(a,s),(b,s))]:
            p=1/(1+10**((table[z]-table[x])/400));step=24*(y-p)
            table[x]+=step;table[z]-=step
    def predict(self,r):
        a=.5*self.global_[r.player_a]+.5*self.surface[(r.player_a,r.surface)]
        b=.5*self.global_[r.player_b]+.5*self.surface[(r.player_b,r.surface)]
        p=1/(1+10**((b-a)/400))
        if r.best_of==5:
            # Convert BO3 match probability via underlying IID set probability.
            lo,hi=0.,1.
            for _ in range(40):
                q=(lo+hi)/2
                if q*q*(3-2*q)<p:lo=q
                else:hi=q
            q=(lo+hi)/2;p=q**3*(1+3*(1-q)+6*(1-q)**2)
        return p

def baselines(data,cutoffs):
    result={};e=Elo();ordered=list(data.sort_values(['historical_release','match_id']).itertuples());j=0
    for start,end in cutoffs:
        cut=pd.Timestamp(start)
        while j<len(ordered) and ordered[j].historical_release<cut:
            e.update(ordered[j]);j+=1
        batch=data[(data.tournament_date>=cut)&(data.tournament_date<pd.Timestamp(end))&data.supported_forecast&data.regime.isin(PRIMARY)]
        for r in batch.itertuples():
            if np.isfinite(r.rank_a) and np.isfinite(r.rank_b):p=.5+.6752*(expit(.72*np.log(r.rank_b/r.rank_a))-.5)
            else:p=.5
            result[r.match_id]=(float(p),float(e.predict(r)))
    return result

def windows(year):
    return [(f'{year}-01-01',f'{year}-04-01'),(f'{year}-04-01',f'{year}-07-01'),(f'{year}-07-01',f'{year}-10-01'),(f'{year}-10-01',f'{year+1}-01-01')]

def make_plan(root):
    plan={'experiment':'TENNIS-SR-20260924-R3','champion':'v7.8 RFG-HC-LT, unchanged',
          'candidate':'SR-GLM-0.1 research Challenger','raw_data_sha256':hashlib.sha256((root/'data/matches.csv.gz').read_bytes()).hexdigest(),
          'burn_in':'2020-2022','hyperparameter_development':'2023 quarterly prequential point log loss',
          'calibration':'2024 quarterly prequential match log loss','held_out_replay':['2025','2026 through saved supported source coverage'],
          'point_configs':[asdict(c) for c in CONFIGS],'selection_rule':'lowest 2023 held-forward aggregate service-point log loss, per tour',
          'calibration_rule':'symmetric service-logit contrast scaling; common service level unchanged; same scoring recursion produces all marginals',
          'current_state_extension':'90-day eligible past point residuals, coefficient estimated using 2024 only',
          'update_rule':'refit at each quarter start, using only tournament_date+14days strictly before cutoff; no within-quarter outcomes',
          'scope':sorted(PRIMARY),'no_random_train_test_split':True,'no_market_features':True,'no_automatic_promotion':True,
          'historical_vintage_limitation':'retrospective current-vintage replay, not prospective or historical as-published data',
          'revision_note':'R3 corrects F=Tour Finals scope and excludes NextGen short-set spelling variants. R2 results were already inspected; this is a transparent data/schema correction, not a new untouched holdout. Hyperparameter selection and calibration still use only 2023 and 2024.', 'registered_at':pd.Timestamp.now(tz='UTC').isoformat()}
    path=root/'evidence/experiment_registration.json'
    if path.exists():
        existing=json.loads(path.read_text())
        if existing['raw_data_sha256']!=plan['raw_data_sha256']:raise ValueError('registered_data_changed')
        return existing
    path.write_text(json.dumps(plan,indent=2));return plan

def run_tour(root:Path,tour:str,stage='all'):
    data=load_data(root);data=data[data.tour==tour].copy();out=root/'reports'/tour;out.mkdir(exist_ok=True)
    eligible=data[data.supported_forecast&data.regime.isin(PRIMARY)]
    if not (root/'evidence/experiment_registration.json').exists():raise ValueError('registration_required')
    selected_file=out/'selected_config.json'
    if not selected_file.exists():
        tests=[]
        for ci,cfg in enumerate(CONFIGS):
            num=0.;den=0.;folds=[]
            for start,end in windows(2023):
                model=ServeReturnModel(tour,cfg).fit(data,start)
                test=eligible[(eligible.tournament_date>=pd.Timestamp(start))&(eligible.tournament_date<pd.Timestamp(end))]
                pred=model.predict(test);n,d=point_logloss(test,pred['eta_a'],pred['eta_b']);num+=n;den+=d
                folds.append({**model.fit_receipt,'evaluation_n':len(test),'point_logloss':n/d if d else None})
                print(tour,'development',ci,start,'point_ll',n/d,'converged',model.fit_receipt['optimizer_success'],flush=True)
            tests.append({'config':asdict(cfg),'point_logloss':num/den,'points':den,'folds':folds})
        best=min(tests,key=lambda x:x['point_logloss'])
        (out/'hyperparameter_development.json').write_text(json.dumps(tests,indent=2));selected_file.write_text(json.dumps(best['config'],indent=2))
    if stage=='tune':return
    cfg=Config(**json.loads(selected_file.read_text()));rows=[];fits=[]
    periods=windows(2024)+windows(2025)+windows(2026)[:3]
    baseline=baselines(data,periods)
    for start,end in periods:
        output=out/f'replay_{start}.csv.gz'
        receipt=out/f'fit_{start}.json'
        if output.exists() and receipt.exists():
            rows.append(pd.read_csv(output));fits.append(json.loads(receipt.read_text()));continue
        model=ServeReturnModel(tour,cfg).fit(data,start)
        test=eligible[(eligible.tournament_date>=pd.Timestamp(start))&(eligible.tournament_date<pd.Timestamp(end))].copy()
        pred=model.predict(test)
        test['p_raw']=pred['p'];test['eta_a']=pred['eta_a'];test['eta_b']=pred['eta_b'];test['minimum_historical_points']=pred['minimum_historical_points'];test['form_delta']=pred['form_delta']
        test['p_rank']=[baseline[x][0] for x in test.match_id];test['p_surface_elo']=[baseline[x][1] for x in test.match_id]
        test['fold_start']=start;test['training_release_max']=model.fit_receipt['latest_training_release']
        test['split']='calibration_2024' if start.startswith('2024') else 'held_out_'+start[:4]
        test['evidence_grade']=np.where(test.minimum_historical_points>=1000,'B',np.where(test.minimum_historical_points>=200,'C','D'))
        keep=['match_id','tour','tournament','tournament_key','tournament_date','regime','surface','best_of','deciding_tiebreak_target','round','level','player_a','player_b','name_a','name_b','y','rank_a','rank_b','point_sides_valid','a_serve_won','a_serve_total','b_serve_won','b_serve_total','p_raw','eta_a','eta_b','minimum_historical_points','form_delta','p_rank','p_surface_elo','fold_start','training_release_max','split','evidence_grade']
        test=test[keep];test.to_csv(output,index=False,compression={'method':'gzip','compresslevel':1});receipt.write_text(json.dumps(model.fit_receipt,indent=2))
        rows.append(test);fits.append(model.fit_receipt)
        print(tour,'replay',start,len(test),'raw_ll',metrics(test.y,test.p_raw)['log_loss'],flush=True)
    all_=pd.concat(rows,ignore_index=True);cal=all_[all_.split=='calibration_2024']
    def probabilities(d,scale,beta=0.):
        return batch_match(d.eta_a.to_numpy(float),d.eta_b.to_numpy(float),d.best_of.to_numpy(np.int64),d.deciding_tiebreak_target.to_numpy(np.int64),float(scale),d.form_delta.to_numpy(float),float(beta))
    def objective(x):return metrics(cal.y,probabilities(cal,x))['log_loss']
    fit=minimize_scalar(objective,bounds=(.2,2.5),method='bounded',options={'xatol':1e-4})
    scale=float(fit.x)
    def objective_plus(x):return metrics(cal.y,probabilities(cal,x[0],x[1]))['log_loss']+.0005*x[1]**2
    fitplus=minimize(objective_plus,[scale,0.],method='L-BFGS-B',bounds=[(.2,2.5),(-5,5)],options={'maxiter':40})
    all_['p_calibrated']=probabilities(all_,scale)
    all_['p_current_state']=probabilities(all_,float(fitplus.x[0]),float(fitplus.x[1]))
    all_.to_csv(out/'predictions.csv.gz',index=False,compression={'method':'gzip','compresslevel':1})
    calibration={'tour':tour,'source_split':'2024','core_scale':scale,'core_success':bool(fit.success),
                 'extended_scale':float(fitplus.x[0]),'extended_beta':float(fitplus.x[1]),'extended_success':bool(fitplus.success),
                 'calibration_n':len(cal),'not_refitted_on_2025_2026':True}
    (out/'calibration.json').write_text(json.dumps(calibration,indent=2));(out/'fits.json').write_text(json.dumps(fits,indent=2))
    summary=[]
    for (split,scope),g in all_.groupby(['split','regime']):
        for col in ['p_rank','p_surface_elo','p_raw','p_calibrated','p_current_state']:
            summary.append({'split':split,'tour':tour,'regime':scope,'model':col,**metrics(g.y,g[col])})
    (out/'metrics.json').write_text(json.dumps(summary,indent=2))
    current=ServeReturnModel(tour,cfg).fit(data,'2026-09-25T00:00:00')
    current.calibration_scale=scale;current.form_beta=0.
    current.save(root/'artifacts'/f'{tour}_SR_CORE')
    current.calibration_scale=float(fitplus.x[0]);current.form_beta=float(fitplus.x[1]);current.save(root/'artifacts'/f'{tour}_SR_CURRENT_STATE')
    print(tour,'DONE',calibration,flush=True)
