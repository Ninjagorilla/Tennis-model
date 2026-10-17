"""Arithmetic after forecasting, kept separate from hazard estimation."""
from __future__ import annotations
import math
from .core import finite, probability


def decimal_odds(american: float) -> float:
    american = finite(american, "American odds")
    if -100 < american < 100:
        raise ValueError("American odds must be <= -100 or >= +100")
    return 1 + (american / 100 if american > 0 else 100 / abs(american))


def break_even(american: float) -> float:
    """Raw price-implied probability; not a no-vig or true-probability estimate."""
    return 1 / decimal_odds(american)


def return_on_stake(american: float, stake: float) -> dict:
    stake = finite(stake, "stake")
    if stake < 0:
        raise ValueError("Stake cannot be negative")
    total = stake * decimal_odds(american)
    return {"stake": stake, "gross_return": total, "net_profit": total - stake}


def quoted_parlay_arithmetic(odds: list[float], stake: float) -> dict:
    """Hypothetical price multiplication, not confirmation a parlay is accepted.

    No assertion of independence or of actual event identities is made here.
    """
    if not odds:
        raise ValueError("At least one quote is required")
    stake = finite(stake, "stake")
    if stake < 0:
        raise ValueError("Stake cannot be negative")
    decimal = math.prod(decimal_odds(o) for o in odds)
    american = 100 * (decimal - 1) if decimal >= 2 else -100 / (decimal - 1)
    return {"status": "HYPOTHETICAL_QUOTE_ARITHMETIC_NOT_EXECUTABLE",
            "decimal_odds": decimal, "american_odds": american,
            "raw_implied_probability": 1 / decimal,
            "stake": stake, "gross_return": stake * decimal, "net_profit": stake * (decimal - 1)}


def independent_joint_probability(legs: list[dict], *, independence_assumption: bool = False) -> dict:
    if independence_assumption is not True:
        raise ValueError("An explicit independence assumption is required")
    if not legs or any(not isinstance(x.get("event_id"), str) or not x["event_id"] for x in legs):
        raise ValueError("Every leg requires a verified event ID")
    event_ids = [x["event_id"] for x in legs]
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("No same-game multiplication; joint/dependence modeling is required")
    return {"probability": math.prod(probability(x["p"], "leg probability") for x in legs),
            "assumption": "INDEPENDENT_DISTINCT_GAMES_NOT_VERIFIED_BY_THIS_FUNCTION"}


def expected_net_per_unit(american: float, p_win: float, p_loss: float, p_void: float = 0) -> float:
    ps = [probability(v, "outcome probability") for v in (p_win, p_loss, p_void)]
    if not math.isclose(math.fsum(ps), 1, abs_tol=1e-12, rel_tol=0):
        raise ValueError("Win/loss/void probabilities must sum to one")
    return ps[0] * (decimal_odds(american) - 1) - ps[1]
