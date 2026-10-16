"""Point-faithful tennis scoring, exact dynamic programming, and actual Monte Carlo.

Completion-conditional, standard advantage games, 6-6 7-point set tiebreak.
Alternate match-tiebreak formats and short sets deliberately blocked.
"""
from __future__ import annotations
from functools import lru_cache
from math import sqrt
import numpy as np
try:
    from numba import njit
except ImportError:
    def njit(*args, **kwargs):
        def decorator(fn): return fn
        return decorator


def service_game(p: float) -> float:
    if not 0 <= p <= 1: raise ValueError('invalid service-point probability')
    q=1-p
    deuce=20*p**3*q**3
    continuation=(p*p/(p*p+q*q)) if (p*p+q*q) else 0.5
    return p**4*(1+4*q+10*q*q)+deuce*continuation


def tiebreak(s_a: float, s_b: float, first_server: int, target: int=7) -> float:
    """Exact A-win tiebreak probability with 1,2,2,2 ... service rotation."""
    if target != 7: raise ValueError('only 7-point tiebreak is currently validated')
    if first_server not in (0,1): raise ValueError('server must be 0 or 1')
    def server_at(point_idx: int) -> int:
        return first_server if point_idx == 0 or ((point_idx-1)//2)%2 else 1-first_server
    # After 6-6, every consecutive 2-point cycle contains one service point
    # from each player, so an analytic absorbing-state expression is exact.
    pair_win=s_a*(1-s_b)
    pair_lose=(1-s_a)*s_b
    deuce_win=pair_win/(pair_win+pair_lose) if (pair_win+pair_lose)>0 else 0.5
    @lru_cache(None)
    def f(a: int,b: int) -> float:
        if a==6 and b==6: return deuce_win
        if a>=7 and a-b>=2: return 1.0
        if b>=7 and b-a>=2: return 0.0
        server=server_at(a+b)
        p=s_a if server==0 else 1-s_b
        return p*f(a+1,b)+(1-p)*f(a,b+1)
    return f(0,0)


@lru_cache(maxsize=4096)
def set_distribution(s_a: float, s_b: float, first_server: int) -> dict[tuple, float]:
    """(games_a,games_b,next_set_first_server,had_tiebreak) -> probability."""
    hold_a=service_game(s_a)
    hold_b=service_game(s_b)
    @lru_cache(None)
    def rec(a: int,b: int) -> dict[tuple,float]:
        if a==6 and b==6:
            t=tiebreak(s_a,s_b,first_server)
            return {(7,6,1-first_server,True):t,
                    (6,7,1-first_server,True):1-t}
        if (a>=6 or b>=6) and abs(a-b)>=2:
            next_server=first_server if (a+b)%2==0 else 1-first_server
            return {(a,b,next_server,False):1.0}
        server=first_server if (a+b)%2==0 else 1-first_server
        p=hold_a if server==0 else 1-hold_b
        out={}
        for key,v in rec(a+1,b).items(): out[key]=out.get(key,0)+p*v
        for key,v in rec(a,b+1).items(): out[key]=out.get(key,0)+(1-p)*v
        return out
    return rec(0,0)


def exact_match(s_a: float, s_b: float, best_of: int=3, first_server: int | None=None) -> dict:
    if not (0<s_a<1 and 0<s_b<1): raise ValueError('service probabilities require 0 < p < 1')
    if best_of not in (3,5): raise ValueError('best_of must be 3 or 5')
    if first_server not in (None,0,1): raise ValueError('invalid first server')
    wins_needed=best_of//2+1
    active={(0,0,sv,0,False):weight for sv,weight in
            ([(0,0.5),(1,0.5)] if first_server is None else [(first_server,1.0)])}
    scorelines={}
    games_dist={}
    p_tb=0.0
    p_deciding=0.0
    for _ in range(best_of):
        following={}
        for (a_sets,b_sets,start,total,had_tb),prior in active.items():
            for (ga,gb,next_start,set_tb),sp in set_distribution(s_a,s_b,start).items():
                x=a_sets+(ga>gb)
                y=b_sets+(gb>ga)
                g=total+ga+gb
                tb=had_tb or set_tb
                mass=prior*sp
                if x==wins_needed or y==wins_needed:
                    key=f'{x}-{y}'
                    scorelines[key]=scorelines.get(key,0)+mass
                    games_dist[g]=games_dist.get(g,0)+mass
                    p_tb+=mass*tb
                    p_deciding+=mass*(x+y==best_of)
                else:
                    key=(x,y,next_start,g,tb)
                    following[key]=following.get(key,0)+mass
        active=following
    if active: raise ArithmeticError('match DP did not terminate')
    mass=sum(scorelines.values())
    if abs(mass-1)>1e-9: raise ArithmeticError(f'non-normalized DP: {mass}')
    p_a=sum(v for k,v in scorelines.items() if int(k.split('-')[0])==wins_needed)
    average=sum(g*p for g,p in games_dist.items())
    median=next(g for g in sorted(games_dist) if sum(v for gg,v in games_dist.items() if gg<=g)>=.5)
    return {'p_a':p_a, 'p_b':1-p_a,'scorelines':dict(sorted(scorelines.items())),
            'games':dict(sorted(games_dist.items())), 'expected_games':average,
            'median_games':median,'p_tiebreak':p_tb,'p_deciding_set':p_deciding}


def mix_exact(sr: dict, elo: dict, elo_weight: float) -> dict:
    if not 0<=elo_weight<=1: raise ValueError('invalid mixture weight')
    w=elo_weight
    games={k:(1-w)*sr['games'].get(k,0)+w*elo['games'].get(k,0)
           for k in sr['games'].keys()|elo['games'].keys()}
    scores={k:(1-w)*sr['scorelines'].get(k,0)+w*elo['scorelines'].get(k,0)
            for k in sr['scorelines'].keys()|elo['scorelines'].keys()}
    median=next(g for g in sorted(games) if sum(v for gg,v in games.items() if gg<=g)>=.5)
    p_a=(1-w)*sr['p_a']+w*elo['p_a']
    return {'p_a':p_a,'p_b':1-p_a,'scorelines':dict(sorted(scores.items())),
            'games':dict(sorted(games.items())),
            'expected_games':(1-w)*sr['expected_games']+w*elo['expected_games'],
            'median_games':median,
            'p_tiebreak':(1-w)*sr['p_tiebreak']+w*elo['p_tiebreak'],
            'p_deciding_set':(1-w)*sr['p_deciding_set']+w*elo['p_deciding_set']}


def logit(p:float)->float:
    import math
    return math.log(p/(1-p))


def expit(x:float)->float:
    import math
    if x>=0: return 1/(1+math.exp(-x))
    y=math.exp(x)
    return y/(1+y)


def elo_service_bridge(p_match_a:float, common_service:float,
                       best_of:int=3) -> tuple[float,float]:
    """Reconstructed bridge, NOT the unavailable original registered conversion.

    Numerically invert exact match DP for a symmetric logit contrast.
    """
    if not 0<p_match_a<1: raise ValueError('invalid target')
    base=logit(common_service)
    lo,hi=-16.,16.
    for _ in range(43):
        middle=(lo+hi)*.5
        sa=expit(base+middle*.5)
        sb=expit(base-middle*.5)
        got=exact_match(sa,sb,best_of)['p_a']
        if got<p_match_a: lo=middle
        else: hi=middle
    shift=(lo+hi)*.5
    return expit(base+shift*.5),expit(base-shift*.5)


@njit(cache=True)
def _simulate(n:int, seed:int, sra:float, srb:float, ela:float, elb:float,
              w:float, best_of:int):
    np.random.seed(seed)
    score_a=np.empty(n,np.int8)
    score_b=np.empty(n,np.int8)
    total_games=np.empty(n,np.int16)
    tb_arr=np.empty(n,np.int8)
    for i in range(n):
        if np.random.random()<w: sa,sb=ela,elb
        else: sa,sb=sra,srb
        start=0 if np.random.random()<0.5 else 1
        need=best_of//2+1
        sets_a=0;sets_b=0;total=0;had_tb=0
        while sets_a<need and sets_b<need:
            ga=0;gb=0
            while True:
                if ga==6 and gb==6:
                    pa=0;pb=0;index=0
                    while True:
                        if index==0 or ((index-1)//2)%2==1: server=start
                        else: server=1-start
                        p=sa if server==0 else 1-sb
                        if np.random.random()<p: pa+=1
                        else: pb+=1
                        index+=1
                        if (pa>=7 or pb>=7) and abs(pa-pb)>=2: break
                    if pa>pb: ga+=1
                    else: gb+=1
                    had_tb=1
                    break
                if (ga>=6 or gb>=6) and abs(ga-gb)>=2: break
                server=start if (ga+gb)%2==0 else 1-start
                p=sa if server==0 else 1-sb
                a_pts=0;b_pts=0
                while True:
                    if np.random.random()<p: a_pts+=1
                    else: b_pts+=1
                    if (a_pts>=4 or b_pts>=4) and abs(a_pts-b_pts)>=2: break
                if a_pts>b_pts: ga+=1
                else: gb+=1
            if ga>gb: sets_a+=1
            else: sets_b+=1
            total+=ga+gb
            if (ga+gb)%2: start=1-start
        score_a[i]=sets_a;score_b[i]=sets_b;total_games[i]=total;tb_arr[i]=had_tb
    return score_a,score_b,total_games,tb_arr


def simulate(sra:float,srb:float,ela:float,elb:float,elo_weight:float,
             best_of:int=3,n:int=100000,seed:int=42)->dict:
    if n<1: raise ValueError('n must be >= 1')
    for x in (sra,srb,ela,elb):
        if not 0<x<1: raise ValueError('invalid scenario probabilities')
    if best_of not in (3,5) or not 0<=elo_weight<=1: raise ValueError('invalid configuration')
    # True point-level matches, mixture component selected once per entire match.
    a,b,g,t=_simulate(n,seed,sra,srb,ela,elb,elo_weight,best_of)
    needed=best_of//2+1
    pa=float(np.mean(a==needed))
    scores={f'{x}-{y}':int(np.count_nonzero((a==x)&(b==y))) for x,y in
            ([(2,0),(2,1),(0,2),(1,2)] if best_of==3 else
             [(3,0),(3,1),(3,2),(0,3),(1,3),(2,3)])}
    count=np.bincount(g.astype(np.int32))
    games={int(i):int(v) for i,v in enumerate(count) if v}
    return {'n':n,'seed':seed, 'wins_a':int(np.count_nonzero(a==needed)),
            'wins_b':int(np.count_nonzero(b==needed)), 'p_a':pa,'p_b':1-pa,
            'mc_se':sqrt(pa*(1-pa)/n),'scoreline_counts':scores,
            'games_counts':games,'expected_games':float(np.mean(g)),
            'median_games':float(np.median(g)),
            'p_tiebreak':float(np.mean(t)),'p_deciding_set':float(np.mean(a+b==best_of))}
