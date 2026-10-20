"""Coherent possession-level NBA simulation research challenger.

One possession produces at most one terminal basket; assists accompany makes,
rebounds accompany misses, and usage is shared across teammates. Provisional
parameters must be calibrated on NBA play-by-play before betting use.
"""
from dataclasses import dataclass
from random import Random
from collections import defaultdict
from math import isfinite

@dataclass(frozen=True)
class Actor:
    player_id: str
    minutes: float
    usage: float
    two_pct: float
    three_pct: float
    three_rate: float
    assist_share: float
    rebound_weight: float
    turnover_rate: float = .12

def _pick(rng, actors, weights):
    s=sum(weights)
    if s<=0: raise ValueError("No eligible opportunity")
    v=rng.random()*s
    for a,w in zip(actors,weights):
        v-=w
        if v<0: return a
    return actors[-1]

def _validate(roster):
    if len(roster)<5 or len({a.player_id for a in roster})!=len(roster):
        raise ValueError("Need >=5 distinct player IDs")
    for a in roster:
        vals=(a.minutes,a.usage,a.two_pct,a.three_pct,a.three_rate,
              a.assist_share,a.rebound_weight,a.turnover_rate)
        if not all(isfinite(x) for x in vals): raise ValueError("Nonfinite input")
        if not 0<=a.minutes<=48 or a.usage<0 or a.rebound_weight<0 or a.assist_share<0:
            raise ValueError("Invalid role")
        if any(not 0<=v<=1 for v in (a.two_pct,a.three_pct,a.three_rate,a.turnover_rate)):
            raise ValueError("Invalid rate")
    if abs(sum(a.minutes for a in roster)-240)>1e-5:
        raise ValueError("Regulation rotation must sum to 240 minutes")

def simulate_game(home,away,possessions=100,iterations=1000,seed=42):
    _validate(home);_validate(away)
    if not 40<=possessions<=140 or not 1<=iterations<=100000:
        raise ValueError("Invalid game configuration")
    rng=Random(seed)
    outcomes=[]
    for _ in range(iterations):
        stats={a.player_id:defaultdict(int) for a in home+away}
        score=[0,0]
        for team,roster in enumerate((home,away)):
            # This is a minutes-weighted approximation of on-court participation.
            active=[a for a in roster if a.minutes>0]
            usage=[a.minutes*a.usage for a in active]
            for _pos in range(possessions):
                shooter=_pick(rng,active,usage)
                s=stats[shooter.player_id]
                if rng.random()<shooter.turnover_rate:
                    s["turnovers"]+=1
                    continue
                is_three=rng.random()<shooter.three_rate
                made=rng.random()<(shooter.three_pct if is_three else shooter.two_pct)
                if made:
                    points=3 if is_three else 2
                    s["points"]+=points
                    score[team]+=points
                    if is_three:s["threes"]+=1
                    assisters=[a for a in active if a.player_id!=shooter.player_id]
                    if assisters and rng.random()<.55:
                        assister=_pick(rng,assisters,[a.minutes*a.assist_share for a in assisters])
                        stats[assister.player_id]["assists"]+=1
                else:
                    # Rebound assignment is a team-level approximation;
                    # opponent rebounds are handled by the opposing roster.
                    rebound_roster=(away if team==0 else home)
                    rebound_active=[a for a in rebound_roster if a.minutes>0]
                    rebounder=_pick(rng,rebound_active,[a.minutes*a.rebound_weight for a in rebound_active])
                    stats[rebounder.player_id]["rebounds"]+=1
        outcomes.append({"home_score":score[0],"away_score":score[1],
                         "players":{k:dict(v) for k,v in stats.items()}})
    return outcomes

def summarize(outcomes,lines=None):
    if not outcomes:raise ValueError("Empty simulations")
    lines=lines or {}
    n=len(outcomes)
    result={"iterations":n,"home_win_probability":sum(o["home_score"]>o["away_score"] for o in outcomes)/n,
            "tie_probability":sum(o["home_score"]==o["away_score"] for o in outcomes)/n,
            "mean_home_score":sum(o["home_score"] for o in outcomes)/n,
            "mean_away_score":sum(o["away_score"] for o in outcomes)/n,
            "player_props":{},"status":"UNCALIBRATED_RESEARCH"}
    for pid,markets in lines.items():
        result["player_props"][pid]={}
        for stat,line in markets.items():
            if stat not in ("points","rebounds","assists","threes","turnovers","pra") or not isinstance(line,(int,float)) or not isfinite(line):
                raise ValueError("Invalid prop")
            def value(o):
                p=o["players"].get(pid,{})
                return sum(p.get(k,0) for k in ("points","rebounds","assists")) if stat=="pra" else p.get(stat,0)
            result["player_props"][pid][stat]={"line":line,"over":sum(value(o)>line for o in outcomes)/n,
                 "push":sum(value(o)==line for o in outcomes)/n}
    return result
