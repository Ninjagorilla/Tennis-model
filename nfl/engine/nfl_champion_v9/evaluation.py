"""Chronological diagnostic evaluation. Never invent frozen historical evidence."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .model import means
from .engine import run, scoring_draws
from .data import write


def binary_metrics(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float)
    if not len(y):return {'n':0}
    clipped=np.clip(p,1e-8,1-1e-8)
    bins=[]
    for lower in np.arange(0,1,.1):
        mask=(p>=lower)&(p<lower+.1 if lower<.9 else p<=1)
        if mask.any():bins.append({'lower':round(float(lower),1),'n':int(mask.sum()),'mean_probability':float(p[mask].mean()),'observed_rate':float(y[mask].mean())})
    return {'n':len(y),'accuracy':float(((p>=.5)==y).mean()),'brier':float(np.mean((p-y)**2)),'log_loss':float(-np.mean(y*np.log(clipped)+(1-y)*np.log(1-clipped))),'calibration_bins':bins}


def evaluate(bundle,data,output,draws=3000,include_players=True):
    data=Path(data);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    rows=pd.read_parquet(data.parent/'fitted/pregame_features.parquet')
    games=pd.read_csv(data/'games.csv').set_index('game_id');ts=pd.read_parquet(data/'team_stats.parquet');ps=pd.read_parquet(data/'player_stats.parquet')
    eval_rows=rows[rows.season.ge(2025)].copy();game_records=[];prop_records=[];coverage=[]
    lines={'passing_yards':[199.5,249.5],'pass_attempts':[29.5],'passing_tds':[1.5],'rushing_yards':[39.5,59.5],'carries':[9.5],'receiving_yards':[29.5,49.5],'receptions':[3.5,5.5],'tds':[.5,1.5]}
    for k,(_,r) in enumerate(eval_rows.iterrows()):
        actual=games.loc[r.game_id];seed=11000+k
        env=means(bundle,r.to_dict());team,w=scoring_draws(bundle,env,draws,np.random.default_rng(seed))
        h,a=team['home']['score'],team['away']['score'];tot=h+a;mar=h-a
        rec={'game_id':r.game_id,'season':int(r.season),'week':int(r.week),'p_home':env['p_home_conditional_non_tie'],'y':int(r.y),'tie':bool(r.tie),'actual_margin':float(r.margin),'actual_total':float(r.total),'pred_margin':float(np.dot(mar,w)),'pred_total':float(np.dot(tot,w)),'total_p10':float(np.quantile(tot,.1)),'total_p90':float(np.quantile(tot,.9))}
        for line in [35.5,45.5,55.5]:rec[f'over_{line}']=float(w[tot>line].sum())
        game_records.append(rec)
        if include_players:
            game={'event_id':r.game_id,'season':int(r.season),'week':int(r.week),'home':r.home,'away':r.away,'kickoff_utc':r.gameday+'T23:00:00+00:00','as_of_utc':r.gameday+'T00:00:00+00:00','home_qb_id':str(actual.home_qb_id),'away_qb_id':str(actual.away_qb_id)}
            report,samples=run(bundle,game,ps,ts,n=draws,seed=seed,row=r.to_dict(),replay=True)
            truth=ps[ps.game_id.eq(r.game_id)].set_index('player_id')
            actual_ids=set(truth.index);pred_ids=set()
            for team_id,ds in samples['players'].items():
                meta={p['player_id']:p for p in report['inputs'][team_id]['players']}
                for pid,dd in ds.items():
                    if pid=='__unallocated__':continue
                    m=meta[pid];pred_ids.add(pid)
                    for stat,thresholds in lines.items():
                        if stat in ['passing_yards','pass_attempts','passing_tds'] and m['pass_attempts']<10:continue
                        if stat in ['rushing_yards','carries'] and m['carries']<3:continue
                        if stat in ['receiving_yards','receptions'] and m['targets']<2:continue
                        if stat=='tds' and m['targets']<2 and m['carries']<3:continue
                        # Diagnostic conditional participation cohort. This is explicitly not a DNP prediction test.
                        if pid not in truth.index:continue
                        observed=float(truth.loc[pid,stat]) if stat!='tds' else float(truth.loc[pid,['rushing_tds','receiving_tds','other_tds']].sum())
                        for line in thresholds:
                            prob=float(samples['weights'][dd[stat]>line].sum())
                            prop_records.append({'game_id':r.game_id,'season':int(r.season),'week':int(r.week),'player_id':pid,'stat':stat,'line':line,'probability':prob,'observed':observed,'y':int(observed>line),'mean':float(np.dot(dd[stat],samples['weights']))})
            coverage.append({'game_id':r.game_id,'actual_stat_participants':len(actual_ids),'forecast_candidates':len(pred_ids),'covered_stat_participants':len(actual_ids&pred_ids),'missed_stat_participants':len(actual_ids-pred_ids)})
        if k%25==0:print(f'EVALUATED {k+1}/{len(eval_rows)}',flush=True)
    g=pd.DataFrame(game_records);p=pd.DataFrame(prop_records)
    report={'version':bundle['version'],'protocol':bundle['protocol'],'scope':'Retrospective, current-vintage diagnostics. 2025/2026 are previously inspected, not untouched. QB IDs are actual historical starters. Prop evaluation conditional on actual participation, candidate/threshold selection uses prior history only. No betting ROI/CLV claim.','draws_per_game':draws,'games':{},'props':{},'coverage':coverage,'benchmarks':{'flat_ml_brier':.25,'flat_ml_log_loss':float(np.log(2))}}
    for season,s in g.groupby('season'):
        q=s[~s.tie];scores=binary_metrics(q.y,q.p_home)
        scores.update(margin_mae=float(abs(s.pred_margin-s.actual_margin).mean()),total_mae=float(abs(s.pred_total-s.actual_total).mean()),totals={str(line):binary_metrics((s.actual_total>line).astype(int),s[f'over_{line}']) for line in [35.5,45.5,55.5]})
        report['games'][str(season)]=scores
    if len(p):
        for (season,stat,line),s in p.groupby(['season','stat','line']):report['props'][f'{season}:{stat}:{line}']=binary_metrics(s.y,s.probability)
        p.to_parquet(out/'prop_predictions.parquet',index=False)
    g.to_csv(out/'game_predictions.csv',index=False);write(out/'evaluation.json',report)
    return report
