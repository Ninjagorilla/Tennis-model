"""Strict, pre-event evaluation of already frozen NBA predictions.

This does not train the source model or authenticate its historical data. Source
vintages and input retrieval times must be audited separately before promotion.
"""
from datetime import datetime, timezone
from math import log, isfinite


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp required")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return t.astimezone(timezone.utc)


def grade(predictions, outcomes):
    truth = {}
    for o in outcomes:
        key = o["game_id"]
        if key in truth:
            raise ValueError("Duplicate outcome identity")
        if type(o.get("home_won")) is not bool and (type(o.get("home_won")) is not int or o["home_won"] not in (0, 1)):
            raise ValueError("Missing or ambiguous outcome")
        truth[key] = o
    joined = []
    seen = set()
    for p in predictions:
        key = p["game_id"]
        if key in seen:
            raise ValueError("Duplicate pregame prediction identity")
        seen.add(key)
        if key not in truth:
            raise ValueError("Missing outcome: do not silently drop unmatched games")
        if not _timestamp(p["asof_utc"]) < _timestamp(p["tipoff_utc"]):
            raise ValueError("Prediction must precede tipoff")
        prob = p["home_win_probability"]
        if type(prob) not in (int, float) or not isfinite(prob) or not 0 < prob < 1:
            raise ValueError("Nonfinite or invalid forecast probability")
        y = int(truth[key]["home_won"])
        joined.append((prob, y))
    if not joined:
        raise ValueError("No matched outcomes")
    n = len(joined)
    return {"n": n, "brier": sum((p-y)**2 for p, y in joined)/n,
            "log_loss": -sum(y*log(p)+(1-y)*log(1-p) for p, y in joined)/n,
            "accuracy": sum((p >= 0.5) == bool(y) for p, y in joined)/n,
            "source_vintage": "UNVERIFIED", "evaluation_type": "PRECOMPUTED_FORECAST_REPLAY"}


def walk_forward(rows, minimum_train=100):
    """Grade provided chronological forecasts, NOT a claim to retrain them.

    Genuine source-vintage, fit/calibration/holdout provenance must be separately
    verified before using this output as a model-promotion study.
    """
    rows = sorted(rows, key=lambda x: _timestamp(x["tipoff_utc"]))
    if len(rows) <= minimum_train or minimum_train < 1:
        raise ValueError("Insufficient future holdout")
    test = rows[minimum_train:]
    return grade([{"game_id": r["game_id"], "tipoff_utc": r["tipoff_utc"],
                   "asof_utc": r["asof_utc"], "home_win_probability": r["probability"]}
                  for r in test], test)
