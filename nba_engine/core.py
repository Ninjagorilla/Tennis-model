"""NBA pregame baseline, experimental and adversarial forecast models.

Inputs must be point-in-time snapshots. No fabricated injury, market or player data.
Probabilities are research estimates until calibrated on out-of-sample NBA results.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from math import exp, sqrt, isfinite
from typing import Optional
import json

@dataclass(frozen=True)
class Team:
    name: str
    offensive_rating: float
    defensive_rating: float
    pace: float
    net_rating_recent: float = 0.0
    rest_days: int = 2
    unavailable_impact: float = 0.0
    projected_minutes_confirmed: bool = False

@dataclass(frozen=True)
class Game:
    game_id: str
    tipoff_utc: str
    home: Team
    away: Team
    asof_utc: str
    market_home_probability: Optional[float] = None
    market_total: Optional[float] = None
    market_home_spread: Optional[float] = None

def _sigmoid(x):
    return 1 / (1 + exp(-max(-40, min(40, x))))

def _validate(g):
    tip = datetime.fromisoformat(g.tipoff_utc.replace("Z","+00:00"))
    asof = datetime.fromisoformat(g.asof_utc.replace("Z","+00:00"))
    if tip.tzinfo is None or asof.tzinfo is None or asof >= tip:
        raise ValueError("Require timezone-aware asof < tipoff")
    if g.home.name == g.away.name or not g.game_id:
        raise ValueError("Invalid fixture identity")
    for t in (g.home, g.away):
        if not all(isfinite(v) for v in (t.pace, t.offensive_rating, t.defensive_rating, t.net_rating_recent, t.unavailable_impact)):
            raise ValueError('Non-finite team inputs')
        if not (65 <= t.pace <= 120 and 75 <= t.offensive_rating <= 145 and 75 <= t.defensive_rating <= 145):
            raise ValueError("Implausible team input; reject rather than silently guess")
        if t.rest_days < 0 or t.unavailable_impact < 0:
            raise ValueError("Invalid rest or unavailable impact")
    if g.market_home_probability is not None and (not isfinite(g.market_home_probability) or not 0 < g.market_home_probability < 1):
        raise ValueError("Invalid market probability")

def scan(g):
    _validate(g)
    possessions = (g.home.pace + g.away.pace) / 2
    home_pp100 = (g.home.offensive_rating + g.away.defensive_rating) / 2
    away_pp100 = (g.away.offensive_rating + g.home.defensive_rating) / 2
    baseline_margin = (home_pp100 - away_pp100) * possessions / 100 + 2.0
    baseline_total = (home_pp100 + away_pp100) * possessions / 100
    # Research-scale spread SD; must be empirically fitted before promotion.
    champion = _sigmoid(baseline_margin / 11.5 * 1.702)
    rest_edge = max(-3, min(3, g.home.rest_days - g.away.rest_days)) * 0.65
    availability_edge = g.away.unavailable_impact - g.home.unavailable_impact
    recent_edge = max(-12, min(12, g.home.net_rating_recent - g.away.net_rating_recent)) * 0.20
    experimental_margin = baseline_margin + rest_edge + availability_edge + recent_edge
    experimental = _sigmoid(experimental_margin / 11.5 * 1.702)
    # Conservative adversary attacks whichever side experimental favors.
    stress = 4.0 if not (g.home.projected_minutes_confirmed and g.away.projected_minutes_confirmed) else 2.0
    devil_margin = experimental_margin - stress if experimental_margin >= 0 else experimental_margin + stress
    devil = _sigmoid(devil_margin / 11.5 * 1.702)
    data_quality = "lineup_unconfirmed" if stress == 4 else "lineup_confirmed"
    return {
        "game_id":g.game_id, "asof_utc":g.asof_utc, "tipoff_utc":g.tipoff_utc,
        "home":g.home.name, "away":g.away.name, "status":"UNCALIBRATED_RESEARCH",
        "champion":{"home_win_probability":round(champion,4),"home_margin":round(baseline_margin,2),"total":round(baseline_total,2)},
        "experimental":{"home_win_probability":round(experimental,4),"home_margin":round(experimental_margin,2),"total":round(baseline_total,2)},
        "devils_advocate":{"home_win_probability":round(devil,4),"home_margin":round(devil_margin,2)},
        "market_home_probability":g.market_home_probability,
        "market_total":g.market_total,"market_home_spread":g.market_home_spread,
        "quality":data_quality,
        "caution":"No bet recommendation: historical calibration and point-in-time validation required"
    }

def scan_json(payload):
    def team(obj): return Team(**obj)
    g=Game(**{**payload,"home":team(payload["home"]),"away":team(payload["away"])})
    return scan(g)
