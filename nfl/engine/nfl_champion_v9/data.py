"""Hashed, transactional nflverse inputs and PBP-to-game/player adapters."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, tempfile, urllib.request
import numpy as np
import pandas as pd
from .freezing import canonical


def now(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, obj, exclusive=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    b=canonical(obj)+b'\n'
    if exclusive:
        with path.open('xb') as f: f.write(b)
        return
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=path.name+'.')
    try:
        with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def download_snapshot(destination, seasons, optional=True):
    """Stage all required bytes before publishing. Never mutate an existing snapshot."""
    dest=Path(destination)
    if dest.exists():raise ValueError('Choose a new snapshot directory; existing evidence is immutable')
    dest.parent.mkdir(parents=True,exist_ok=True)
    urls={'games.csv':'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'}
    for y in seasons: urls[f'pbp_{y}.parquet']=f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{y}.parquet'
    receipts=[]
    with tempfile.TemporaryDirectory(dir=dest.parent,prefix='nfl-staging-') as temp:
        stage=Path(temp)
        for name,url in urls.items():
            with urllib.request.urlopen(url,timeout=45) as r, (stage/name).open('wb') as out:
                while chunk:=r.read(1024*1024):out.write(chunk)
            # Parse downloaded bytes before accepting an HTTP success as data success.
            if name.endswith('.csv'): pd.read_csv(stage/name,nrows=2)
            else: pd.read_parquet(stage/name,columns=['game_id','play_id'])
            receipts.append({'file':name,'url':url,'retrieved_at':now(),'sha256':sha(stage/name),'bytes':(stage/name).stat().st_size})
        optional_receipts=[]
        if optional:
            year=max(seasons)
            for name,path in [('rosters',f'rosters/roster_{year}'),('injuries',f'injuries/injuries_{year}'),('depth_charts',f'depth_charts/depth_charts_{year}')]:
                url='https://github.com/nflverse/nflverse-data/releases/download/'+path+'.parquet'
                file=stage/(name+'.parquet')
                try:
                    with urllib.request.urlopen(url,timeout=30) as response:file.write_bytes(response.read())
                    pd.read_parquet(file)
                    optional_receipts.append({'name':name,'url':url,'status':'SUCCESS','sha256':sha(file),'retrieved_at':now()})
                except (OSError,ValueError) as exc:
                    if file.exists():file.unlink()
                    optional_receipts.append({'name':name,'url':url,'status':'UNAVAILABLE','error':str(exc)})
        write(stage/'availability_manifest.json',optional_receipts)
        write(stage/'source_manifest.json',receipts)
        os.rename(stage,dest)
    return receipts


def validate_schedule(schedule):
    need={'game_id','season','week','gameday','home_team','away_team','home_score','away_score','game_type'}
    if need-set(schedule):raise ValueError('Missing schedule columns: '+str(sorted(need-set(schedule))))
    if schedule.game_id.isna().any() or schedule.game_id.duplicated().any():raise ValueError('Duplicate/missing game IDs')
    if (schedule.home_team==schedule.away_team).any():raise ValueError('Same team fixture')
    pd.to_datetime(schedule.gameday,errors='raise')
    for _,r in schedule.iterrows():
        if r.game_id!=f'{int(r.season)}_{int(r.week):02d}_{r.away_team}_{r.home_team}':raise ValueError('Fixture ID/team mismatch')
    if (schedule.home_score.notna()!=schedule.away_score.notna()).any():raise ValueError('Partial final scores')
    return schedule


COLS='game_id play_id game_date posteam defteam home_team away_team pass_attempt rush_attempt complete_pass passing_yards receiving_yards rushing_yards receiver_player_id receiver_player_name rusher_player_id rusher_player_name passer_player_id passer_player_name touchdown pass_touchdown rush_touchdown td_team td_player_id td_player_name field_goal_result extra_point_result two_point_conv_result two_point_attempt extra_point_attempt safety sack defensive_two_point_conv return_team total_home_score total_away_score yardline_100'.split()


def aggregate_players(pbp_directory, schedule, output):
    """Real PBP only. No-price features, stable IDs, no-play/2pt exclusion."""
    source=Path(pbp_directory);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    schedule=validate_schedule(schedule)
    completed=schedule[schedule.home_score.notna() & schedule.game_type.isin(['REG','WC','DIV','CON','SB'])]
    lookup=completed.set_index('game_id'); teams=[]; players=[]; receipt=[]
    for year in sorted(completed.season.unique()):
        path=source/f'pbp_{year}.parquet'
        if not path.exists():continue
        p=pd.read_parquet(path,columns=COLS)
        if p.duplicated(['game_id','play_id']).any():raise ValueError('Duplicate PBP keys')
        p=p[p.game_id.isin(lookup.index)].copy()
        p.loc[p.sack.eq(1),'pass_attempt']=0
        for gid,g in p.groupby('game_id',sort=False):
            r=lookup.loc[gid]
            if set(g.home_team.dropna())!={r.home_team} or set(g.away_team.dropna())!={r.away_team}:raise ValueError('PBP fixture mismatch')
            if set(g.game_date.dropna())!={r.gameday}:raise ValueError('PBP date mismatch')
            base={'game_id':gid,'season':int(year),'week':int(r.week),'gameday':r.gameday}
            normal=g[~g.two_point_attempt.eq(1) & ~g.extra_point_attempt.eq(1)]
            for team,opp,score in [(r.home_team,r.away_team,r.home_score),(r.away_team,r.home_team,r.away_score)]:
                o=normal[normal.posteam==team];td=normal[normal.td_team.eq(team)&normal.touchdown.eq(1)]
                t={**base,'team':team,'opponent':opp,'score':int(score)}
                t.update(pass_td=int(td.pass_touchdown.sum()),rush_td=int(td.rush_touchdown.sum()),other_td=int((~td.pass_touchdown.eq(1)&~td.rush_touchdown.eq(1)).sum()),fg=int((g.posteam.eq(team)&g.field_goal_result.eq('made')).sum()),xp_made=int((g.posteam.eq(team)&g.extra_point_result.eq('good')).sum()),two_made=int((g.posteam.eq(team)&g.two_point_conv_result.eq('success')).sum()),safety=int(((g['total_home_score' if team==r.home_team else 'total_away_score'].diff().fillna(0)>0)&g.safety.eq(1)).sum()),defensive_two=int((g.defteam.eq(team)&g.defensive_two_point_conv.eq(1)).sum()),pass_attempts=int(o.pass_attempt.sum()),carries=int(o.rush_attempt.sum()),completions=int(o.complete_pass.sum()),passing_yards=float(o.passing_yards.sum()),rushing_yards=float(o.rushing_yards.sum()))
                # This validates the scoring adapter, rather than trusting event counts.
                t['scoring_residual']=int(score)-(6*(t['pass_td']+t['rush_td']+t['other_td'])+3*t['fg']+t['xp_made']+2*(t['two_made']+t['safety']+t['defensive_two']))
                teams.append(t)
                ids=set(o.receiver_player_id.dropna())|set(o.rusher_player_id.dropna())|set(o.passer_player_id.dropna())|set(td.td_player_id.dropna())
                for pid in sorted(ids):
                    rec=o[o.receiver_player_id.eq(pid)];ru=o[o.rusher_player_id.eq(pid)];pa=o[o.passer_player_id.eq(pid)];scores=td[td.td_player_id.eq(pid)]
                    name=''
                    for frame,col in [(rec,'receiver_player_name'),(ru,'rusher_player_name'),(pa,'passer_player_name'),(scores,'td_player_name')]:
                        if not frame.empty and frame[col].notna().any():name=str(frame[col].dropna().iloc[-1]);break
                    players.append({**base,'team':team,'player_id':pid,'name':name,'targets':int(rec.pass_attempt.sum()),'receptions':int(rec.complete_pass.sum()),'receiving_yards':float(rec.receiving_yards.sum()),'carries':int(ru.rush_attempt.sum()),'rushing_yards':float(ru.rushing_yards.sum()),'pass_attempts':int(pa.pass_attempt.sum()),'completions':int(pa.complete_pass.sum()),'passing_yards':float(pa.passing_yards.sum()),'passing_tds':int(pa.pass_touchdown.sum()),'receiving_tds':int(scores.pass_touchdown.sum()),'rushing_tds':int(scores.rush_touchdown.sum()),'other_tds':int((~scores.pass_touchdown.eq(1)&~scores.rush_touchdown.eq(1)).sum()),'rz_targets':int((rec.yardline_100.le(20)&rec.pass_attempt.eq(1)).sum()),'rz_carries':int((ru.yardline_100.le(20)&ru.rush_attempt.eq(1)).sum())})
        receipt.append({'file':path.name,'sha256':sha(path),'rows':len(p)})
    t=pd.DataFrame(teams);p=pd.DataFrame(players)
    expected=set(completed[completed.season.isin(t.season)].game_id)
    if set(t.game_id)!=expected:raise ValueError('Incomplete historical PBP coverage')
    if t.duplicated(['game_id','team']).any() or p.duplicated(['game_id','player_id']).any():raise ValueError('Duplicate aggregate identities')
    t.to_parquet(out/'team_stats.parquet',index=False);p.to_parquet(out/'player_stats.parquet',index=False)
    write(out/'aggregation_receipt.json',{'created_at':now(),'sources':receipt,'team_rows':len(t),'player_rows':len(p),'scoring_residual_rows':int(t.scoring_residual.ne(0).sum()),'residuals':t[t.scoring_residual.ne(0)][['game_id','team','scoring_residual']].to_dict('records')})
    return t,p
