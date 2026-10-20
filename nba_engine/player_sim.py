"""Deterministic Monte Carlo player prop research simulator.

Rates and minutes are explicit external inputs; no synthetic roster or injury claims.
Independent Poisson draws are a provisional limitation, not calibrated betting odds.
"""
from dataclasses import dataclass
from math import exp
from random import Random

@dataclass(frozen=True)
class Player:
    player_id: str
    name: str
    minutes: float
    points_per36: float
    rebounds_per36: float
    assists_per36: float
    threes_per36: float
    minutes_sd: float = 3.0

def simulate(players, lines, iterations=10000, seed=42):
    if not 100 <= iterations <= 100000: raise ValueError("Invalid iteration count")
    ids=[p.player_id for p in players]
    if len(set(ids))!=len(ids): raise ValueError("Duplicate player ID")
    rng=Random(seed)
    output={}
    for p in players:
        if not p.player_id or not p.name or not 0<=p.minutes<=48 or not 0<=p.minutes_sd<=20:
            raise ValueError("Invalid player/minutes")
        rates=(p.points_per36,p.rebounds_per36,p.assists_per36,p.threes_per36)
        if any(x<0 or x>65 for x in rates): raise ValueError("Invalid per36 rate")
        thresholds=lines.get(p.player_id,{})
        valid={"points","rebounds","assists","threes","pra"}
        if not set(thresholds).issubset(valid): raise ValueError("Unknown market")
        counts={k:0 for k in thresholds}
        sums={k:0 for k in valid}
        for _ in range(iterations):
            mins=max(0,min(48,rng.gauss(p.minutes,p.minutes_sd)))
            vals={}
            for name,rate in zip(("points","rebounds","assists","threes"),rates):
                lam=rate*mins/36
                # Poisson by interarrival for reproducible dependency-free sampling
                t=0.0;n=0
                while True:
                    t+=rng.expovariate(1)
                    if t>lam: break
                    n+=1
                vals[name]=n
            vals["pra"]=vals["points"]+vals["rebounds"]+vals["assists"]
            for k,v in vals.items(): sums[k]+=v
            for k,line in thresholds.items():
                if not isinstance(line,(int,float)) or line<0: raise ValueError("Invalid line")
                counts[k]+=vals[k]>line
        output[p.player_id]={"name":p.name,"mean":{k:round(v/iterations,3) for k,v in sums.items()},
            "over_probability":{k:round(v/iterations,4) for k,v in counts.items()},
            "status":"UNCALIBRATED_RESEARCH"}
    return output
