"""Prior-only player opportunity estimates; zero-game and unknown-scorer accounting."""
import numpy as np
import pandas as pd


def project(history,team_stats,team,cutoff,priors,roster=None,qb_id=None):
    """Candidate membership defaults to recent observations, never claimed confirmed active."""
    h=history[history.gameday.lt(cutoff)];team_games=team_stats[team_stats.team.eq(team)&team_stats.gameday.lt(cutoff)].sort_values(['gameday','game_id']).tail(8)
    if team_games.empty:raise ValueError('No past team games for player opportunity model')
    gids=team_games.game_id.tolist();weights={g:.8**(len(gids)-1-i) for i,g in enumerate(gids)};den=sum(weights.values())
    recent=h[h.team.eq(team)&h.game_id.isin(gids)]
    latest=h.sort_values(['gameday','game_id']).groupby('player_id',sort=False).tail(1).set_index('player_id')
    if roster is None:
        ids=[p for p in recent.player_id.unique() if latest.loc[p,'team']==team]
        roster=[{'player_id':p,'name':str(latest.loc[p,'name']),'status':'unknown'} for p in ids]
    if len({p['player_id'] for p in roster})!=len(roster):raise ValueError('Duplicate roster IDs')
    stats=[]
    for entry in roster:
        pid=entry['player_id']
        if entry.get('status') not in ['active','out','questionable','unknown']:raise ValueError('Player status required')
        z=h[h.player_id.eq(pid)].sort_values(['gameday','game_id']).tail(12)
        local=recent[recent.player_id.eq(pid)]
        w=local.game_id.map(weights).to_numpy()
        def avg(col):return float(np.dot(local[col],w)/den) if len(local) else 0.
        # Usage is team-specific. New teammates/rookies need explicit scenario opportunity overrides.
        targets=avg('targets');carries=avg('carries');attempts=avg('pass_attempts')
        eff=lambda num,col,base,n:float((z[num].sum()+n*base)/(z[col].sum()+n))
        status=entry['status']
        stats.append({'player_id':pid,'name':entry.get('name',str(latest.loc[pid,'name']) if pid in latest.index else pid),'status':status,'historical_games':len(z),'targets':targets,'carries':carries,'pass_attempts':attempts,'catch_rate':eff('receptions','targets',priors['catch_rate'],20),'ypc':eff('receiving_yards','receptions',priors['yards_per_catch'],20),'ypr':eff('rushing_yards','carries',priors['yards_per_carry'],30),'rush_td_weight':carries+3*avg('rz_carries'),'receive_td_weight':targets+3*avg('rz_targets'),'other_td_weight':avg('other_tds')})
    if qb_id and qb_id not in {x['player_id'] for x in stats}:
        stats.append({'player_id':qb_id,'name':str(latest.loc[qb_id,'name']) if qb_id in latest.index else qb_id,'status':'unknown','historical_games':0,'targets':0.,'carries':0.,'pass_attempts':1.,'catch_rate':priors['catch_rate'],'ypc':priors['yards_per_catch'],'ypr':priors['yards_per_carry'],'rush_td_weight':0.,'receive_td_weight':0.,'other_td_weight':0.})
    total=lambda c:float(np.dot(team_games[c],team_games.game_id.map(weights))/den)
    # Preserve unidentified targets/carries. Out-player reallocation is scenario-specific.
    unknown={'targets':max(total('pass_attempts')-sum(x['targets'] for x in stats),.5),'carries':max(total('carries')-sum(x['carries'] for x in stats),.25)}
    return stats,unknown


def scenario_players(base,unknown,scenario):
    result=[dict(x) for x in base]
    active=set(scenario['active_player_ids'])
    if len(active)!=len(scenario['active_player_ids']):raise ValueError('Duplicate scenario players')
    if active-{x['player_id'] for x in result}:raise ValueError('Unknown scenario player IDs')
    for x in result:
        if x['status']=='out' and x['player_id'] in active:raise ValueError('OUT player cannot be active')
        for k,v in scenario.get('opportunity_overrides',{}).get(x['player_id'],{}).items():
            if k not in ['targets','carries','pass_attempts','rush_td_weight','receive_td_weight','other_td_weight']:raise ValueError('Unknown opportunity override')
            if isinstance(v,bool) or not np.isfinite(v) or v<0:raise ValueError('Invalid opportunity override')
            x[k]=float(v)
        if x['player_id'] not in active:
            for k in ['targets','carries','pass_attempts','rush_td_weight','receive_td_weight','other_td_weight']:x[k]=0.
    if set(scenario.get('opportunity_overrides',{}))-{x['player_id'] for x in result}:raise ValueError('Override contains unknown ID')
    return result,unknown
