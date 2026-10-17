"""Portable research engine commands. No betting execution or hidden background worker."""
from __future__ import annotations
import argparse, json, sys, shutil
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from .data import write, now, sha, download_snapshot, aggregate_players
from .model import load, fit
from .engine import run
from .markets import compare, settle
from .feeds import slate, roster_inputs, status_receipt
from .freezing import freeze, code_hashes, canonical
from .aggregate_team import aggregate

ROOT=Path(__file__).resolve().parents[1]

def parser():
    ap=argparse.ArgumentParser(description='NFL v9 integrated research engine');sub=ap.add_subparsers(dest='command',required=True)
    t=sub.add_parser('train');t.add_argument('--data',default=str(ROOT/'data'));t.add_argument('--output',required=True)
    e=sub.add_parser('evaluate');e.add_argument('--data',default=str(ROOT/'data'));e.add_argument('--model',default=str(ROOT/'fitted/model.joblib'));e.add_argument('--output',required=True);e.add_argument('--draws',type=int,default=3000);e.add_argument('--games-only',action='store_true')
    for name in ['predict','slate']:
        p=sub.add_parser(name);p.add_argument('--model',default=str(ROOT/'fitted/model.joblib'));p.add_argument('--data',default=str(ROOT/'data'));p.add_argument('--output',required=True);p.add_argument('--draws',type=int,default=20000);p.add_argument('--seed',type=int,default=904);p.add_argument('--quotes');p.add_argument('--freeze',action='store_true')
        if name=='predict':p.add_argument('--input',required=True)
        else:p.add_argument('--snapshot',default=str(ROOT/'live_snapshot'));p.add_argument('--limit',type=int)
    d=sub.add_parser('refresh');d.add_argument('--season',type=int,default=2026);d.add_argument('--history',required=True);d.add_argument('--output',required=True)
    s=sub.add_parser('settle');s.add_argument('--input',required=True);s.add_argument('--output',required=True)
    sub.add_parser('status')
    return ap

def execute(args):
    if args.command=='status':print((ROOT/'WORK_MODE_STATUS.md').read_text());return
    if args.command=='train':
        if Path(args.output).exists():raise ValueError('Use new model output directory')
        fit(args.data,args.output);print('TRAINED',args.output);return
    if args.command=='evaluate':
        from .evaluation import evaluate
        evaluate(load(args.model),args.data,args.output,args.draws,not args.games_only);return
    if args.command=='settle':
        x=json.loads(Path(args.input).read_text());write(args.output,[settle(q,x['outcome']) for q in x['markets']],exclusive=True);return
    if args.command=='refresh':
        dest=Path(args.output)
        if dest.exists():raise ValueError('Refresh output directory already exists')
        # Separate new snapshot; old fitted state never overwritten on failure.
        download_snapshot(dest/'snapshot',[args.season])
        cache=dest/'cache';cache.mkdir()
        history=Path(args.history)
        for y in range(2021,args.season):
            src=history/f'pbp_{y}.parquet'
            if not src.exists():raise ValueError('Missing historical snapshot '+str(src))
            (cache/src.name).symlink_to(src.resolve())
        (cache/f'pbp_{args.season}.parquet').symlink_to((dest/'snapshot'/f'pbp_{args.season}.parquet').resolve())
        data=dest/'data';data.mkdir();shutil.copy2(dest/'snapshot/games.csv',data/'games.csv')
        schedule=pd.read_csv(data/'games.csv');schedule=schedule[schedule.season.between(2021,args.season)]
        aggregate_players(cache,schedule,data);aggregate(cache)
        for n in ['team_game_aggregates.json','qb_game_aggregates.json']:shutil.copy2(cache/n,data/n)
        fit(data,dest/'fitted');write(dest/'READY.json',{'created_at':now(),'model_sha256':sha(dest/'fitted/model.joblib')});print('REFRESHED',dest);return
    bundle=load(args.model);data=Path(args.data)
    players=pd.read_parquet(data/'player_stats.parquet');teams=pd.read_parquet(data/'team_stats.parquet')
    # Prevent accidentally mixing a fitted bundle with a different player dataset.
    for p in [data/'player_stats.parquet',data/'team_stats.parquet']:
        if sha(p)!=bundle['protocol']['source_hashes'][p.name]:raise ValueError('Model/data provenance mismatch')
    games=[json.loads(Path(args.input).read_text())] if args.command=='predict' else slate(args.snapshot)
    if args.command=='slate' and args.limit:games=games[:args.limit]
    output=Path(args.output)
    if output.exists():raise ValueError('Output already exists; choose a new run directory')
    output.mkdir(parents=True);receipts=[]
    quotes=json.loads(Path(args.quotes).read_text()) if args.quotes else []
    for i,game in enumerate(games):
        try:
            if args.command=='slate':
                game,issues=roster_inputs(args.snapshot,game)
                # A provisional schedule QB who is OUT cannot be a forecast starter.
                for side in ['home','away']:
                    team=game[side];roster=game.get('rosters',{}).get(team,[])
                    if any(p['player_id']==game.get(side+'_qb_id') and p['status']=='out' for p in roster):game[side+'_qb_id']=None;issues.append(team+': scheduled QB OUT; unknown-QB prior used')
            else:issues=[]
            # CLI always uses the actual clock, never a caller's backdated as_of.
            game['as_of_utc']=now()
            if datetime.fromisoformat(game['kickoff_utc'].replace('Z','+00:00'))<=datetime.now(timezone.utc):raise ValueError('Started event filtered before inference')
            result,samples=run(bundle,game,players,teams,n=args.draws,seed=args.seed+i)
            result['warnings']+=issues
            result['model_sha256']=sha(args.model)
            qs=[q for q in quotes if q['event_id']==game['event_id']]
            result['market_comparison']=compare(samples,qs,game['event_id'],game['as_of_utc']) if qs else []
            result['quotes_status']='CALLER_SNAPSHOT' if qs else 'MISSING: model outputs still shown; no live Novig verification'
            target=output/(game['event_id']+'.json')
            if args.freeze:freeze(target,result,game,lambda:status_receipt(game['event_id']))
            else:
                payload={'prediction':result,'input_data':game,'code_hashes':code_hashes(),'recorded_at_utc':now(),'evidence_class':'RESEARCH_TIME_UNVERIFIED','model_sha256':sha(args.model)}
                import hashlib
                write(target,{'payload':payload,'sha256':hashlib.sha256(canonical(payload)).hexdigest()},exclusive=True)
            receipts.append({'event_id':game['event_id'],'status':'SUCCESS','output':target.name,'p_home':result['game']['home_win'],'total':result['game']['total']['mean'],'home_margin':result['game']['home_margin']['mean']})
            print('FORECAST',game['event_id'],flush=True)
        except (ValueError,KeyError,OSError,TypeError) as exc:
            receipts.append({'event_id':game.get('event_id'),'status':'FAILED','reason':str(exc)});print('FAILED',game.get('event_id'),str(exc),flush=True)
    write(output/'run_receipt.json',{'created_at':now(),'events':receipts,'success_count':sum(x['status']=='SUCCESS' for x in receipts),'failure_count':sum(x['status']=='FAILED' for x in receipts),'model_sha256':sha(args.model)},exclusive=True)
    if any(x['status']=='FAILED' for x in receipts):raise ValueError('Some fixtures failed; completed results preserved in run_receipt.json')


def main():
    try:execute(parser().parse_args());return 0
    except (ValueError,KeyError,OSError,TypeError) as exc:print('ERROR:',str(exc),file=sys.stderr);return 2
