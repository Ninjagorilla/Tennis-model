"""Opponent-adjusted hierarchical serve/return binomial model.

logit P(server wins point) = tour-surface intercept + global serve(server)
 + surface serve(server) - global return(receiver) - surface return(receiver)
 + tournament-surface context + competition-scope context.

The penalized likelihood is fitted on point counts, not winners, ranks or odds.
Time decay handles changing ability. Gaussian penalties partially pool thin data.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.special import expit
from scipy.optimize import minimize
from .scoring import batch_match,predict_distribution

@dataclass(frozen=True)
class Config:
    half_life_days:float=365.
    player_penalty:float=50.
    surface_penalty:float=200.
    context_penalty:float=200.
    history_years:float=5.
    maxiter:int=300

class ServeReturnModel:
    def __init__(self,tour:str,config:Config=Config()):
        if tour not in ('ATP','WTA'):raise ValueError('unknown_tour')
        self.tour=tour;self.config=config;self.surface={'Hard':0,'Clay':1,'Grass':2}
        self.players={};self.contexts={};self.regimes={};self.coefficients=None
        self.exposures={};self.recent={};self.fit_receipt={};self.calibration_scale=1.;self.form_beta=0.
    def _matrix(self,server,receiver,surfaces,contexts,regimes):
        n=len(server);rows=[];cols=[];vals=[];p=len(self.players)
        for i,(a,b,s,c,r) in enumerate(zip(server,receiver,surfaces,contexts,regimes)):
            if s not in self.surface:raise ValueError('unsupported_surface')
            si=self.surface[s]; rows.append(i);cols.append(si);vals.append(1.)
            for player,role,sign in ((a,0,1.),(b,1,-1.)):
                pi=self.players.get(player)
                if pi is not None:
                    rows.extend([i,i]);cols.extend([3+role*p+pi,3+2*p+role*3*p+pi*3+si]);vals.extend([sign,sign])
            ci=self.contexts.get(c)
            if ci is not None:rows.append(i);cols.append(3+8*p+ci);vals.append(1.)
            ri=self.regimes.get(r)
            if ri is not None:rows.append(i);cols.append(3+8*p+len(self.contexts)+ri);vals.append(1.)
        return csr_matrix((vals,(rows,cols)),shape=(n,self.dimension),dtype=float)
    def fit(self,data:pd.DataFrame,cutoff:str):
        cut=pd.Timestamp(cutoff)
        if cut.tzinfo:cut=cut.tz_convert('UTC').tz_localize(None)
        # Strict cutoff is intentionally not derived from the target outcome date.
        d=data[(data.tour==self.tour)&(data.historical_release<cut)&
               (data.tournament_date>=cut-pd.Timedelta(days=365.25*self.config.history_years))&data.surface.isin(self.surface)].copy()
        blocks=[]
        for side,other in (('a','b'),('b','a')):
            v=d[d[f'{side}_serve_total'].notna()]
            blocks.append(pd.DataFrame({'server':v[f'player_{side}'],'receiver':v[f'player_{other}'],
                'surface':v.surface,'context':v.tournament_key+'|'+v.surface,'regime':v.regime,
                'won':v[f'{side}_serve_won'],'n':v[f'{side}_serve_total'],'date':v.tournament_date}))
        obs=pd.concat(blocks,ignore_index=True)
        if len(obs)<100:raise ValueError('insufficient_point_history')
        self.players={p:i for i,p in enumerate(sorted(set(obs.server)|set(obs.receiver)))}
        self.contexts={c:i for i,c in enumerate(sorted(set(obs.context)))}
        self.regimes={r:i for i,r in enumerate(sorted(set(obs.regime)))}
        p=len(self.players);self.dimension=3+8*p+len(self.contexts)+len(self.regimes)
        X=self._matrix(obs.server,obs.receiver,obs.surface,obs.context,obs.regime)
        weights=np.exp(-np.log(2)*(cut-obs.date).dt.total_seconds().to_numpy()/86400/self.config.half_life_days)
        won=obs.won.to_numpy(float)*weights;n=obs.n.to_numpy(float)*weights
        penalty=np.r_[np.repeat(.2,3),np.repeat(self.config.player_penalty,2*p),
                      np.repeat(self.config.surface_penalty,6*p),np.repeat(self.config.context_penalty,len(self.contexts)),np.repeat(50.,len(self.regimes))]
        prior=np.zeros(self.dimension)
        for s,idx in self.surface.items():
            mask=obs.surface.to_numpy()==s
            rate=(won[mask].sum()+60)/(n[mask].sum()+100)
            prior[idx]=np.log(rate/(1-rate))
        def objective(theta):
            eta=X@theta;pr=expit(eta);dev=theta-prior
            return (np.sum(n*np.logaddexp(0,eta)-won*eta)+.5*np.sum(penalty*dev*dev),
                    np.asarray(X.T@(n*pr-won)).ravel()+penalty*dev)
        preconditioner=np.sqrt(np.asarray(X.power(2).T@(n*.24)).ravel()+penalty)
        def scaled(z):
            value,grad=objective(prior+z/preconditioner)
            return value,grad/preconditioner
        result=minimize(scaled,np.zeros(self.dimension),method='L-BFGS-B',jac=True,options={'maxiter':self.config.maxiter,'ftol':1e-10,'gtol':1e-4,'maxcor':20})
        if not np.isfinite(result.x).all():raise ValueError('nonfinite_fit')
        self.coefficients=prior+result.x/preconditioner
        # Diagonal curvature is stored as a local approximation, NOT a calibrated CI.
        probs=expit(X@self.coefficients)
        self.diagonal_precision=np.asarray(X.power(2).T@(n*probs*(1-probs))).ravel()+penalty
        self.exposures={}
        for role,col in ((0,'server'),(1,'receiver')):
            for player,g in obs.groupby(col):
                self.exposures[(player,role)]=(float(g.n.sum()),int(len(g)))
        # Recent residuals are diagnostics learned only from eligible past observations.
        obs['residual']=obs.won.to_numpy()-obs.n.to_numpy()*probs
        recent=obs[obs.date>=cut-pd.Timedelta(days=90)]
        own_sums=recent.groupby('server')[['residual','n']].sum()
        opp_sums=recent.groupby('receiver')[['residual','n']].sum()
        self.recent={}
        for player in self.players:
            own=own_sums.loc[player] if player in own_sums.index else None
            opp=opp_sums.loc[player] if player in opp_sums.index else None
            self.recent[player]=float((own.residual/(own.n+200) if own is not None else 0)-(opp.residual/(opp.n+200) if opp is not None else 0))
        self.fit_receipt={'tour':self.tour,'cutoff':cut.isoformat(),'latest_training_release':d.historical_release.max().isoformat(),
            'matches_with_any_points':int((d.point_sides_valid>0).sum()),'service_observations':len(obs),
            'service_points':int(obs.n.sum()),'players':p,'config':asdict(self.config),'optimizer_success':bool(result.success),
            'optimizer_message':str(result.message),'iterations':int(result.nit),'coefficient_sha256':hashlib.sha256(self.coefficients.tobytes()).hexdigest()}
        return self
    def point_logits(self,events):
        if self.coefficients is None:raise ValueError('model_not_fitted')
        if not (events.tour==self.tour).all():raise ValueError('cross_tour_input_forbidden')
        c=events.tournament_key+'|'+events.surface
        xa=self._matrix(events.player_a,events.player_b,events.surface,c,events.regime)
        xb=self._matrix(events.player_b,events.player_a,events.surface,c,events.regime)
        eta_a=np.asarray(xa@self.coefficients);eta_b=np.asarray(xb@self.coefficients)
        exposures=[];form=[]
        for a,b in zip(events.player_a,events.player_b):
            exposures.append(min(self.exposures.get((p,r),(0,0))[0] for p in (a,b) for r in (0,1)))
            form.append((self.recent.get(a,0)-self.recent.get(b,0))/2)
        return eta_a,eta_b,np.asarray(exposures),np.asarray(form)
    def predict(self,events,scale=None,beta=None):
        ea,eb,n,form=self.point_logits(events)
        p=batch_match(ea,eb,events.best_of.to_numpy(np.int64),events.deciding_tiebreak_target.to_numpy(np.int64),
                      self.calibration_scale if scale is None else scale,form,self.form_beta if beta is None else beta)
        return {'p':p,'eta_a':ea,'eta_b':eb,'minimum_historical_points':n,'form_delta':form}
    def explain(self,event):
        d=pd.DataFrame([event]);e=self.predict(d)
        a,b=event['player_a'],event['player_b'];si=self.surface[event['surface']];n=len(self.players)
        def player_parts(p):
            i=self.players.get(p)
            if i is None:return {'known':False,'global_serve':0.,'surface_serve':0.,'global_return':0.,'surface_return':0.}
            return {'known':True,'global_serve':float(self.coefficients[3+i]),'surface_serve':float(self.coefficients[3+2*n+3*i+si]),
                    'global_return':float(self.coefficients[3+n+i]),'surface_return':float(self.coefficients[3+5*n+3*i+si])}
        common=(e['eta_a'][0]+e['eta_b'][0])/2;rawdiff=(e['eta_a'][0]-e['eta_b'][0])/2
        diff=self.calibration_scale*rawdiff+self.form_beta*e['form_delta'][0]
        pa,pb=expit(common+diff),expit(common-diff)
        result={'player_a':a,'player_b':b,'a_components':player_parts(a),'b_components':player_parts(b),
                'point_probability_raw_a':float(expit(e['eta_a'][0])),'point_probability_raw_b':float(expit(e['eta_b'][0])),
                'point_probability_calibrated_a':float(pa),'point_probability_calibrated_b':float(pb),
                'calibration_scale':self.calibration_scale,'form_beta':self.form_beta,
                'minimum_historical_points':float(e['minimum_historical_points'][0]),'fit_receipt':self.fit_receipt,
                'distribution':predict_distribution(float(pa),float(pb),event['best_of'],event['deciding_tiebreak_target'])}
        stresses={}
        for label,shift in [('a_service_minus_1pp',(-.01,0)),('b_service_plus_1pp',(0,.01)),('a_service_plus_1pp',(.01,0)),('b_service_minus_1pp',(0,-.01))]:
            aa,bb=np.clip(pa+shift[0],1e-5,1-1e-5),np.clip(pb+shift[1],1e-5,1-1e-5)
            stresses[label]=predict_distribution(float(aa),float(bb),event['best_of'],event['deciding_tiebreak_target'])['p_a']
        result['stress_tests_not_primary']=stresses
        result['stress_range_not_confidence_interval']=[min(stresses.values()),max(stresses.values())]
        return result
    def save(self,path:Path):
        raise RuntimeError('INFERENCE_ONLY_NO_REFIT')
    @classmethod
    def load(cls,path:Path):
        m=json.loads((path/'model.json').read_text())
        if hashlib.sha256((path/'weights.json').read_bytes()).hexdigest()!=m['weights_sha256']:raise ValueError('artifact_hash_mismatch')
        model=cls(m['tour'],Config(**m['config']));arr={k:np.asarray(v,dtype=np.float64) for k,v in json.loads((path/'weights.json').read_text()).items()}
        for k in ('players','contexts','regimes','dimension','fit_receipt','calibration_scale','form_beta','recent'):setattr(model,k,m[k])
        model.coefficients=arr['coefficients'];model.diagonal_precision=arr['diagonal_precision']
        model.exposures={(p,r):(points,matches) for p,r,points,matches in m['exposures']}
        return model
