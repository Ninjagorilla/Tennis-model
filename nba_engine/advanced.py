"""WNBA-inspired opportunity allocation and NBA predictive priors.

Research utilities; coefficients require NBA-specific walk-forward calibration.
"""
from dataclasses import dataclass
from math import exp

@dataclass(frozen=True)
class RotationPlayer:
    player_id: str
    minutes: float
    usage: float
    available: bool = True

def allocate_minutes(players, total=240):
    """Allocate 240 regulation team minutes with explicit available rotation.
    Caller-supplied minute weights must be nonnegative; fail closed if empty.
    """
    if total <= 0: raise ValueError("Invalid total")
    ids=[p.player_id for p in players]
    if len(ids)!=len(set(ids)): raise ValueError("Duplicate identity")
    weights=[p.minutes if p.available else 0 for p in players]
    if any(p.minutes<0 or p.usage<0 for p in players): raise ValueError("Negative input")
    denom=sum(weights)
    if denom<=0: raise ValueError("No available minutes")
    return {p.player_id:total*w/denom for p,w in zip(players,weights)}

def usage_shares(players, minutes):
    """Redistribute available opportunity as a single shared possession pie."""
    w={p.player_id:minutes[p.player_id]*p.usage for p in players if p.available}
    total=sum(w.values())
    if total<=0: raise ValueError("No offensive opportunities")
    return {k:v/total for k,v in w.items()}

def recency_projection(observations, asof, half_life_days=35, prior=None, prior_weight=5):
    """Time-decayed observations: (ISO date, value), strictly earlier than asof."""
    from datetime import datetime
    t=datetime.fromisoformat(asof.replace("Z","+00:00"))
    if t.tzinfo is None or half_life_days<=0: raise ValueError("Invalid asof/decay")
    numerator=0.;denominator=0.
    for date,value in observations:
        d=datetime.fromisoformat(date.replace("Z","+00:00"))
        if d.tzinfo is None or d>=t: raise ValueError("Lookahead or invalid observation")
        age=(t-d).total_seconds()/86400
        w=exp(-0.6931471805599453*age/half_life_days)
        numerator+=w*value;denominator+=w
    if prior is not None:
        if prior_weight<0: raise ValueError("Negative prior weight")
        numerator+=prior_weight*prior;denominator+=prior_weight
    if denominator==0: raise ValueError("No historical evidence")
    return numerator/denominator

def matchup_pace(home_pace,away_pace,league_pace,shrinkage=.25):
    """Geometric pace with shrinkage to league, avoiding arithmetic overprojection."""
    if min(home_pace,away_pace,league_pace)<=0 or not 0<=shrinkage<=1:
        raise ValueError("Invalid pace")
    pace=(home_pace*away_pace)**.5
    return (1-shrinkage)*pace+shrinkage*league_pace

def four_factors(efg,tov,orb,ftr):
    """Four-factor descriptive composite. Never stack on overlapping ORtg inputs."""
    if any(not 0<=x<=1 for x in (efg,tov,orb,ftr)): raise ValueError("Invalid factors")
    return .42*efg-.30*tov+.17*orb+.12*ftr
