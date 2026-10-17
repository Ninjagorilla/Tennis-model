"""Grade immutable pregame player-stat ladder events, not sportsbook contracts."""
import argparse,json,math
from pathlib import Path
from collections import defaultdict
import pandas as pd
from nfl.paper import read_freeze
from nfl.research import save
STATS=('passing_yards','pass_attempts','completions','passing_tds','rushing_yards','carries','receiving_yards','receptions','targets','rushing_tds','receiving_tds')
COLS='game_id play_id home_team away_team total_home_score total_away_score pass_attempt complete_pass passing_yards receiving_yards rushing_yards passer_player_id receiver_player_id rusher_player_id rush_attempt touchdown pass_touchdown rush_touchdown td_player_id play_type play_deleted two_point_attempt extra_point_attempt sack posteam'.split()
def valid(f):return f[~f.play_deleted.eq(1)&~f.play_type.eq('no_play')&~f.two_point_attempt.eq(1)&~f.extra_point_attempt.eq(1)]
def actuals(pbp,home,away,scores):
 if pbp.empty or pbp.play_id.duplicated().any():raise ValueError('Missing or duplicate plays')
 if set(pbp.home_team.dropna())!={home} or set(pbp.away_team.dropna())!={away}:raise ValueError('Team mismatch')
 last=pbp.iloc[-1]
 if (float(last.total_home_score),float(last.total_away_score))!=tuple(float(v) for v in scores):raise ValueError('Final-score mismatch')
 values=defaultdict(lambda:{k:0. for k in STATS});played=set()
 def add(team,pid,stat,v):
  if pd.isna(pid) or pd.isna(team) or team not in (home,away):return
  key=str(team)+'|'+str(pid);played.add(key);values[key][stat]+=float(v)
 for r in valid(pbp).itertuples(index=False):
  t=r.posteam
  if t not in (home,away):continue
  if r.pass_attempt==1 and r.sack!=1:
   add(t,r.passer_player_id,'pass_attempts',1)
   if r.complete_pass==1:add(t,r.passer_player_id,'completions',1)
   add(t,r.passer_player_id,'passing_yards',r.passing_yards if pd.notna(r.passing_yards) else 0)
   if pd.notna(r.receiver_player_id):
    add(t,r.receiver_player_id,'targets',1)
    if r.complete_pass==1:
     add(t,r.receiver_player_id,'receptions',1)
     add(t,r.receiver_player_id,'receiving_yards',r.receiving_yards if pd.notna(r.receiving_yards) else 0)
   if r.pass_touchdown==1:
    add(t,r.passer_player_id,'passing_tds',1);add(t,r.td_player_id,'receiving_tds',1)
  if r.rush_attempt==1:
   add(t,r.rusher_player_id,'carries',1)
   add(t,r.rusher_player_id,'rushing_yards',r.rushing_yards if pd.notna(r.rushing_yards) else 0)
   if r.rush_touchdown==1:add(t,r.td_player_id,'rushing_tds',1)
 return dict(values),played
def threshold(prob,actual,line):
 if isinstance(line,bool) or not isinstance(line,(int,float)) or not math.isfinite(line):raise ValueError('line')
 if not isinstance(prob,(int,float)) or not math.isfinite(prob) or not 0<=prob<=1:raise ValueError('probability')
 hit=int(actual>=line);return {'probability':float(prob),'hit':hit,'brier':(prob-hit)**2,'log_loss':-math.log(max(prob if hit else 1-prob,1e-15))}
def audit(papers,inputs,out):
 inp=Path(inputs);sched=pd.read_csv(inp/'games.csv').set_index('game_id');chosen={}
 for folder in papers:
  for path in sorted(Path(folder).rglob('forecast_*.json')) if Path(folder).exists() else []:
   try:p=read_freeze(path)
   except (ValueError,KeyError,TypeError,AssertionError):continue
   if p is None:continue
   for game in p['games']:
    key=(game['event_id'],p['model_parameter_sha256'],p['first_td_parameter_sha256'])
    if key not in chosen or p['created_at_utc']<chosen[key][0]['created_at_utc']:chosen[key]=(p,game)
 grouped=defaultdict(list)
 for (gid,*_),pair in chosen.items():grouped[gid].append(pair)
 metrics=defaultdict(list);skips=defaultdict(int);graded=set();pending=[]
 for year in sorted({int(gid[:4]) for gid in grouped}):
  ids=[gid for gid in grouped if gid.startswith(str(year)+'_')];path=inp/f'pbp_{year}.parquet'
  if not path.exists():pending.extend(ids);continue
  frames={str(k):g for k,g in pd.read_parquet(path,columns=COLS,filters=[('game_id','in',ids)]).groupby('game_id')}
  for gid in ids:
   if gid not in sched.index or pd.isna(sched.loc[gid,'home_score']) or pd.isna(sched.loc[gid,'away_score']) or gid not in frames:
    pending.append(gid);continue
   row=sched.loc[gid]
   try:stats,played=actuals(frames[gid],row.home_team,row.away_team,(row.home_score,row.away_score))
   except (ValueError,TypeError):skips['source_conflict']+=1;continue
   for freeze,g in grouped[gid]:
    if (g['home'],g['away'])!=(row.home_team,row.away_team):skips['fixture_conflict']+=1;continue
    for team,players in g.get('players',{}).items():
     if team not in (g['home'],g['away']):continue
     for player in players:
      key=team+'|'+str(player['player_id'])
      if key not in played:skips['participation_unverified']+=1;continue
      for market,ladder in player.get('ladders',{}).items():
       if market not in STATS:continue
       for point in ladder:
        try:v=threshold(point['probability'],stats[key][market],point['at_least'])
        except (ValueError,KeyError,TypeError):skips['invalid_threshold']+=1;continue
        metrics[market].append(v);graded.add(gid)
      # The engine's anytime/2+ TD markets represent rushing + receiving scores.
      # They cannot be equated with sportsbook anytime TD including returns/fumbles.
      offensive=stats[key]['rushing_tds']+stats[key]['receiving_tds']
      for market,prob,line in [('offensive_td_1plus',player.get('atd'),1),('offensive_td_2plus',player.get('two_plus_td'),2)]:
       if prob is None:continue
       try:v=threshold(prob,offensive,line)
       except (ValueError,TypeError):skips['invalid_threshold']+=1;continue
       metrics[market].append(v);graded.add(gid)
 report={'schema':'nfl-player-prop-research-1','graded_games':len(graded),'unique_frozen_games':len(grouped),
 'pending_games':len(set(pending)),'participation_unverified':skips['participation_unverified'],
 'source_conflicts':skips['source_conflict']+skips['fixture_conflict'],
 'invalid_thresholds':skips['invalid_threshold'],'publication_approved':False,'settlement_claim':False,
 'limits':['Research at-least threshold events, not sportsbook settlement','No missing-player zero imputation',
 'Participation requires identifiable PBP action; inactive/snap-only players remain ungraded',
 'Touchdown events are rushing/receiving only: returns and fumble recoveries are excluded', 'No push, void, odds, return or ROI inference','No promotion from this report'],'markets':{}}
 for market,vals in sorted(metrics.items()):
  n=len(vals);bins=[]
  for lo in range(0,100,10):
   b=[v for v in vals if lo/100<=v['probability']<(lo+10)/100 or (lo==90 and v['probability']==1)]
   if b:bins.append({'range':str(lo)+'-'+str(lo+10)+'%','n':len(b),'forecast':round(sum(v['probability'] for v in b)/len(b),4),'observed':round(sum(v['hit'] for v in b)/len(b),4)})
  report['markets'][market]={'threshold_events':n,'brier':round(sum(v['brier'] for v in vals)/n,6),
  'log_loss':round(sum(v['log_loss'] for v in vals)/n,6),'observed_hit_rate':round(sum(v['hit'] for v in vals)/n,4),
  'predicted_hit_rate':round(sum(v['probability'] for v in vals)/n,4),'calibration':bins}
 save(out,report);return report
def main():
 p=argparse.ArgumentParser();p.add_argument('--inputs',default='work/nfl/inputs');p.add_argument('--out',default='work/nfl_prop_report.json');p.add_argument('--paper',nargs='+',default=['work/nfl/paper','work/nfl/prior_paper','work/nfl/paper_archive']);args=p.parse_args()
 r=audit(args.paper,args.inputs,args.out);print(json.dumps({'graded_games':r['graded_games'],'markets':list(r['markets'])}))
if __name__=='__main__':main()
