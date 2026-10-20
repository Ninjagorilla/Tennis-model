"""Conservative paired promotion evidence gate for NBA, NFL and Tennis.

This component NEVER rewrites a Champion registry or frozen forecast. It tests
statistical superiority, not the authenticity of externally supplied data.
"""
from datetime import datetime, timezone
import json
import math
import random
import sys

MIN_PAIRED = 200


def _utc(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field}: required timestamp")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}: invalid timestamp") from exc
    if t.tzinfo is None:
        raise ValueError(f"{field}: timezone required")
    return t.astimezone(timezone.utc)


def _hash(value, field):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{field}: requires lowercase SHA-256 receipt")
    return value


def _prob(value, field):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value < 1:
        raise ValueError(f"{field}: finite probability strictly inside (0,1) required")
    return float(value)


def _percentile(sorted_values, fraction):
    h = (len(sorted_values) - 1) * fraction
    lo = int(h)
    return sorted_values[lo] * (1 - (h - lo)) + sorted_values[min(lo + 1, len(sorted_values) - 1)] * (h - lo)


def _paired_interval(deltas, rng, draws, alpha):
    n = len(deltas)
    samples = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(draws))
    return [_percentile(samples, alpha / 2), _percentile(samples, 1 - alpha / 2)]


def evaluate(rows, *, fit_end_utc, calibration_start_utc, calibration_end_utc,
             holdout_start_utc, holdout_end_utc, resamples=4000,
             seed=20261020, alpha=0.05):
    """Score EXACTLY the same frozen holdout events, refusing ambiguous inputs.

    Row fields: sport, target, event_id, champion_id, challenger_id,
    event_start_utc, forecast_asof_utc, source_released_utc,
    frozen_at_utc, outcome_released_utc, forecast_sha256,
    source_vintage_sha256, champion_p, challenger_p, outcome (0/1).

    Model fit/source vintage truth and external freeze-receipt authenticity
    remain UNVERIFIED until independently audited. Statistical success alone
    is NOT authorization to replace any production Champion.
    """
    fit_end = _utc(fit_end_utc, "fit_end_utc")
    cal_start = _utc(calibration_start_utc, "calibration_start_utc")
    cal_end = _utc(calibration_end_utc, "calibration_end_utc")
    hold_start = _utc(holdout_start_utc, "holdout_start_utc")
    hold_end = _utc(holdout_end_utc, "holdout_end_utc")
    if not (fit_end < cal_start < cal_end < hold_start < hold_end):
        raise ValueError("FIT_CALIBRATION_HOLDOUT_WINDOWS_OVERLAP_OR_REVERSED")
    if type(resamples) is not int or not 200 <= resamples <= 50000:
        raise ValueError("INVALID_BOOTSTRAP_REPETITIONS")
    if type(alpha) is not float or not 0 < alpha < 1:
        raise ValueError("INVALID_INTERVAL_ALPHA")
    if type(seed) is not int:
        raise ValueError("INVALID_BOOTSTRAP_SEED")
    rows = list(rows)
    if not rows:
        return {"status": "INSUFFICIENT_EVIDENCE", "n": 0, "required_n": MIN_PAIRED,
                "promotion_authorized": False, "source_authenticity": "UNVERIFIED"}
    seen = set()
    cohorts = set()
    loss_before_brier, loss_after_brier = [], []
    loss_before_log, loss_after_log = [], []
    for i, r in enumerate(rows):
        required = ("sport", "target", "event_id", "champion_id", "challenger_id",
                    "event_start_utc", "forecast_asof_utc", "source_released_utc",
                    "frozen_at_utc", "outcome_released_utc", "forecast_sha256",
                    "source_vintage_sha256", "champion_p", "challenger_p", "outcome")
        absent = [k for k in required if k not in r]
        if absent:
            raise ValueError(f"MISSING_FIELDS row={i} fields={absent}")
        for k in ("sport", "target", "event_id", "champion_id", "challenger_id"):
            if not isinstance(r[k], str) or not r[k].strip():
                raise ValueError(f"INVALID_ID: {k} row={i}")
        if r["champion_id"] == r["challenger_id"]:
            raise ValueError("MODELS_ARE_NOT_DISTINCT")
        cohorts.add((r["sport"], r["target"], r["champion_id"], r["challenger_id"]))
        identity = (r["sport"], r["target"], r["event_id"])
        if identity in seen:
            raise ValueError("DUPLICATE_EVENT_OR_OVERWRITTEN_FORECAST")
        seen.add(identity)
        event = _utc(r["event_start_utc"], "event_start_utc")
        asof = _utc(r["forecast_asof_utc"], "forecast_asof_utc")
        source = _utc(r["source_released_utc"], "source_released_utc")
        frozen = _utc(r["frozen_at_utc"], "frozen_at_utc")
        outcome_time = _utc(r["outcome_released_utc"], "outcome_released_utc")
        if not (hold_start <= event < hold_end):
            raise ValueError("EVENT_OUTSIDE_PREDECLARED_HOLDOUT")
        if not (source < asof <= frozen < event < outcome_time):
            raise ValueError("POINT_IN_TIME_OR_FREEZE_INTEGRITY_FAILURE")
        _hash(r["forecast_sha256"], "forecast_sha256")
        _hash(r["source_vintage_sha256"], "source_vintage_sha256")
        if type(r["outcome"]) is not int or r["outcome"] not in (0, 1):
            raise ValueError("INVALID_RESULT_LABEL")
        y = r["outcome"]
        p = _prob(r["champion_p"], "champion_p")
        q = _prob(r["challenger_p"], "challenger_p")
        loss_before_brier.append((p - y)**2)
        loss_after_brier.append((q - y)**2)
        loss_before_log.append(-math.log(p if y else 1 - p))
        loss_after_log.append(-math.log(q if y else 1 - q))
    if len(cohorts) != 1:
        raise ValueError("UNPAIRED_COHORTS_MUST_BE_EVALUATED_SEPARATELY")
    n = len(rows)
    def avg(a):
        return sum(a) / len(a)
    base = {"brier": avg(loss_before_brier), "log_loss": avg(loss_before_log)}
    challenger = {"brier": avg(loss_after_brier), "log_loss": avg(loss_after_log)}
    out = {"status": "INSUFFICIENT_EVIDENCE" if n < MIN_PAIRED else "NO_PROMOTION",
           "n": n, "required_n": MIN_PAIRED, "cohort": list(next(iter(cohorts))),
           "champion": base, "challenger": challenger,
           "source_authenticity": "UNVERIFIED_EXTERNAL_LEDGER_AND_MODEL_VINTAGE",
           "promotion_authorized": False,
           "statistical_gate_pass": False,
           "delta_definition": "challenger_minus_champion"}
    if n < MIN_PAIRED:
        return out
    rng = random.Random(seed)
    db = [a - b for a, b in zip(loss_after_brier, loss_before_brier)]
    dl = [a - b for a, b in zip(loss_after_log, loss_before_log)]
    ci_b = _paired_interval(db, rng, resamples, alpha)
    ci_l = _paired_interval(dl, rng, resamples, alpha)
    success = ci_b[1] < 0 and ci_l[1] < 0
    out.update({"delta_brier": avg(db), "delta_log_loss": avg(dl),
                "delta_brier_ci": ci_b, "delta_log_loss_ci": ci_l,
                "bootstrap_draws": resamples, "seed": seed,
                "statistical_gate_pass": success,
                "status": "STATISTICALLY_FAVORABLE_REQUIRES_SOURCE_AUDIT" if success else "NO_PROMOTION"})
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/phoenix_promotion_gate.py receipt.json")
    payload = json.load(open(sys.argv[1], encoding="utf-8"))
    print(json.dumps(evaluate(**payload), sort_keys=True, indent=2))
