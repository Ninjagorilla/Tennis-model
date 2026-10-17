"""Train/serialize market-free scoring, volume and moneyline models chronologically."""
from __future__ import annotations
from pathlib import Path
import json, hashlib
import joblib, numpy as np, pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import PoissonRegressor, LogisticRegression
from .features import DIFF, SUM, features, roll
from .data import write, sha, now, validate_schedule

VERSION='NFL-v9.1-integrated-1'
TARGETS=['pass_td','rush_td','other_td','fg','pass_attempts','carries']
XCOLS=DIFF+SUM

def matrix(frame,side):
    x=frame[XCOLS].to_numpy(dtype=float).copy()
    if side=='away':x[:,:len(DIFF)]*=-1
    if not np.isfinite(x).all():raise ValueError('Nonfinite feature values')
    return x

def fit(data, output):
    data=Path(data);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    games=validate_schedule(pd.read_csv(data/'games.csv'))
    team=pd.read_parquet(data/'team_stats.parquet');players=pd.read_parquet(data/'player_stats.parquet')
    games=games[games.game_id.isin(team.game_id)&games.home_score.notna()].copy()
    a=json.loads((data/'team_game_aggregates.json').read_text());q=json.loads((data/'qb_game_aggregates.json').read_text())
    rows,state,qbs=roll(games,a,q)
    rows.to_parquet(output/'pregame_features.parquet',index=False)
    train=rows[rows.season.isin([2022,2023])];cal=rows[rows.season.eq(2024)]
    if len(train)<400 or len(cal)<200:raise ValueError('Insufficient chronological fit/calibration cohorts')
    X=np.vstack([matrix(train,'home'),matrix(train,'away')]);C=np.vstack([matrix(cal,'home'),matrix(cal,'away')])
    def targets(frame,name):
        ti=team.set_index(['game_id','team'])
        return np.r_[ti.loc[list(zip(frame.game_id,frame.home)),name].to_numpy(),ti.loc[list(zip(frame.game_id,frame.away)),name].to_numpy()]
    models={};calibration={};train_means={}
    for name in TARGETS:
        y=targets(train,name);cy=targets(cal,name)
        m=make_pipeline(StandardScaler(),PoissonRegressor(alpha=1.,max_iter=1000,tol=1e-8));m.fit(X,y)
        raw=m.predict(C);ratio=float(cy.sum()/raw.sum())
        models[name]=m;calibration[name]=ratio;train_means[name]=float(y.mean())
    # Shared team gamma scoring variance, learned only on calibration outcomes.
    cm=sum(models[k].predict(C)*calibration[k] for k in TARGETS[:3]);ct=sum(targets(cal,k) for k in TARGETS[:3])
    excess=float(np.mean((ct-cm)**2-ct));shape=float(np.clip(np.mean(cm**2)/max(excess,1e-6),.5,1000))
    volume_shapes={}
    for k in ['pass_attempts','carries']:
        mu=models[k].predict(C)*calibration[k];y=targets(cal,k)
        excess=float(np.mean((y-mu)**2-y));volume_shapes[k]=float(np.clip(np.mean(mu**2)/max(excess,1e-6),1,1000))
    # Symmetric calibrated win model. Its result reweights the entire joint simulation.
    tr=train[~train.tie];ca=cal[~cal.tie];dx=tr[DIFF].to_numpy()
    ml=make_pipeline(StandardScaler(with_mean=False),LogisticRegression(C=.1,fit_intercept=False,max_iter=2000))
    ml.fit(np.vstack([dx,-dx]),np.r_[tr.y,1-tr.y])
    z=ml.decision_function(ca[DIFF].to_numpy()).reshape(-1,1)
    calibrator=LogisticRegression(C=1,fit_intercept=False,max_iter=2000)
    calibrator.fit(np.vstack([z,-z]),np.r_[ca.y,1-ca.y])
    pt=players[players.season.isin([2022,2023])];tt=team[team.season.isin([2022,2023])]
    def ratio(a,b):return float(a.sum()/max(b.sum(),1))
    priors={'catch_rate':ratio(pt.receptions,pt.targets),'yards_per_catch':ratio(pt.receiving_yards,pt.receptions),'yards_per_carry':ratio(pt.rushing_yards,pt.carries),'passing_td_per_attempt':ratio(pt.passing_tds,pt.pass_attempts)}
    # Empirical per-game efficiency variability; capped estimates are explicitly in bundle.
    priors['receiving_yard_sd_per_sqrt_catch']=float(np.sqrt(np.mean(((pt.receiving_yards-priors['yards_per_catch']*pt.receptions)**2/(pt.receptions+1)))))
    priors['rushing_yard_sd_per_sqrt_carry']=float(np.sqrt(np.mean(((pt.rushing_yards-priors['yards_per_carry']*pt.carries)**2/(pt.carries+1)))))
    tds=tt[['pass_td','rush_td','other_td']].sum(axis=1).sum()
    extra=np.array([max(tds-tt.xp_made.sum()-tt.two_made.sum(),0),tt.xp_made.sum(),tt.two_made.sum()],float);extra/=extra.sum()
    params={'scoring_shape':shape,'volume_shapes':volume_shapes,'extra_point_probs':extra.tolist(),'safety_mean':float(tt.safety.mean()),'defensive_two_mean':float(tt.defensive_two.mean()),'tie_rate':float((cal.tie.sum()+.5)/(len(cal)+1)),'priors':priors,'share_concentration':30.,'share_concentration_status':'fixed conservative modeling assumption, not fitted','player_prior_opportunities':20.,'player_history_team_games':8,'player_recency_decay':.8}
    protocol={'version':VERSION,'created_at':now(),'warmup':[2021],'fit_seasons':[2022,2023],'calibration_seasons':[2024],'evaluation_seasons':[2025,2026],'n_fit_games':len(train),'n_calibration_games':len(cal),'as_of':str(games.gameday.max()),'last_game':str(games.sort_values('gameday').iloc[-1].game_id),'limitations':['Current-vintage historical data, not as-published availability','Actual historical starting QB used in diagnostic features','2025/2026 previously inspected; not untouched holdout','Player share concentration fixed at 30; evaluate sensitivity','No inferred injury penalties or fabricated current actives','No fitted weather or offensive-line availability effect'],'source_hashes':{p.name:sha(p) for p in [data/'team_stats.parquet',data/'player_stats.parquet',data/'games.csv',data/'team_game_aggregates.json',data/'qb_game_aggregates.json']}}
    bundle={'version':VERSION,'models':models,'scale':calibration,'ml':ml,'calibrator':calibrator,'params':params,'state':state,'qbs':qbs,'protocol':protocol}
    joblib.dump(bundle,output/'model.joblib',compress=3)
    write(output/'model_card.json',protocol|{'parameters':params,'calibration_scales':calibration,'model_sha256':sha(output/'model.joblib')})
    return bundle


def load(path):
    path=Path(path);card=json.loads(path.with_name('model_card.json').read_text())
    if sha(path)!=card['model_sha256']:raise ValueError('Fitted bundle checksum mismatch')
    b=joblib.load(path) # only load trusted, locally built package bytes
    if b['version']!=VERSION:raise ValueError('Unsupported model version')
    return b

def means(bundle,row):
    f=pd.DataFrame([row]);result={}
    for side in ['home','away']:
        x=matrix(f,side);result[side]={k:float(np.clip(m.predict(x)[0]*bundle['scale'][k],1e-8,100 if k in ['pass_attempts','carries'] else 12)) for k,m in bundle['models'].items()}
    z=bundle['ml'].decision_function(f[DIFF].to_numpy()).reshape(-1,1)
    result['p_home_conditional_non_tie']=float(bundle['calibrator'].predict_proba(z)[0,1])
    return result
