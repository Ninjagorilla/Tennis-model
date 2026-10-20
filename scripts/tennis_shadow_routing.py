"""Serving safeguards: WTA SR-Elo blend remains shadow-only.

This changes public routing without changing registered model files, weights,
source hashes or historic snapshots. A missing SR Challenger is NO_FORECAST.
"""
from copy import deepcopy


def apply_wta_shadow_guard(match):
    if match.get("tour") != "WTA":
        return match
    results = match["results"]
    champion = deepcopy(results.get("champion") or {"status": "unavailable", "reason": "NO_CHAMPION_OUTPUT"})
    match["wta_blend_shadow"] = {**champion, "role": "SHADOW",
        "not_for_action": True, "historical_metrics_citable": False}
    results["champion"] = {"status": "unavailable", "reason": "WTA_BLEND_DEMOTED_TO_SHADOW"}
    sr = results.get("challenger") or {"status": "unavailable", "reason": "NO_SR_CHALLENGER"}
    if sr.get("status") == "ok":
        p = sr.get("p_a")
        q = sr.get("p_b")
        from math import isfinite
        if (type(p) not in (int, float) or type(q) not in (int, float)
                or not isfinite(p) or not isfinite(q) or not 0 <= p <= 1
                or not 0 <= q <= 1 or abs(p + q - 1) > 1e-9):
            sr = {"status": "unavailable", "reason": "INVALID_SR_PROBABILITY"}
    good = sr.get("status") == "ok"
    match["wta_selected"] = {
        "role": "SR_CHALLENGER_RESEARCH" if good else "NO_FORECAST",
        "status": "ok" if good else "unavailable",
        "selection_reason": "WTA_BLEND_DEMOTED_TO_SHADOW",
        "research_only": True,
        "model_id": sr.get("model_id") if good else None,
        "p_a": sr.get("p_a") if good else None,
        "p_b": sr.get("p_b") if good else None,
        "reason": None if good else sr.get("reason", "SR_CHALLENGER_UNAVAILABLE")}
    return match
