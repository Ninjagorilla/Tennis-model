"""Ordered competing-risk calculation. No real-data parameters are supplied.

Each interval supplies cause probabilities conditional on the absence of the
requested first-TD event. Scenario weights and hazards must be estimated by an
upstream, point-in-time model. This module does not derive them from ATD odds.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any

VERSION = "NFL-First-TD-Challenger-0.1.0"
MARKETS = {"GAME_FIRST_TD", "TEAM_FIRST_TD"}
NO_TD = "__no_touchdown__"


def keys(obj: dict, required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(obj, dict):
        raise ValueError("A JSON object is required")
    missing, extra = required - obj.keys(), obj.keys() - required - optional
    if missing or extra:
        raise ValueError(f"Missing fields {sorted(missing)}; unsupported fields {sorted(extra)}")


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: a nonempty string is required")
    return value


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: a finite number is required")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label}: a finite number is required")
    return result


def probability(value: Any, label: str) -> float:
    result = finite(value, label)
    if not 0 <= result <= 1:
        raise ValueError(f"{label}: probability must be in [0, 1]")
    return result


def timestamp(value: str) -> datetime:
    text(value, "timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return dt.astimezone(timezone.utc)


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate(request: dict, *, now: datetime | None = None) -> dict:
    keys(request, {"event_id", "kind", "market", "target_team", "include_overtime",
                   "kickoff_utc", "data_as_of_utc", "parameter_model_id", "source_refs",
                   "entities", "scenarios"})
    text(request["event_id"], "event_id")
    if request["kind"] not in {"SYNTHETIC", "RESEARCH"}:
        raise ValueError("Only SYNTHETIC or RESEARCH inputs are supported")
    if request["market"] not in MARKETS:
        raise ValueError("Use an explicit GAME_FIRST_TD or TEAM_FIRST_TD market")
    if type(request["include_overtime"]) is not bool:
        raise ValueError("include_overtime must be a boolean")
    if request["market"] == "GAME_FIRST_TD" and request["target_team"] is not None:
        raise ValueError("A game-first market cannot have a target team")
    if request["market"] == "TEAM_FIRST_TD":
        text(request["target_team"], "target_team")
    kickoff, data_as_of = timestamp(request["kickoff_utc"]), timestamp(request["data_as_of_utc"])
    if data_as_of >= kickoff:
        raise ValueError("Pregame inputs cannot contain data at/after kickoff")
    text(request["parameter_model_id"], "parameter_model_id")
    refs = request["source_refs"]
    if not isinstance(refs, list) or not refs:
        raise ValueError("Explicit source or assumption references required")
    for ref in refs:
        text(ref, "source reference")
    if request["kind"] == "RESEARCH":
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError("Timezone-aware clock required")
        if clock >= kickoff:
            raise ValueError("No post-kickoff pregame prediction is allowed")
        if data_as_of > clock:
            raise ValueError("Inputs cannot be dated in the future")
    if not isinstance(request["entities"], list) or not request["entities"]:
        raise ValueError("A nonempty entity list is required")
    entities = {}
    for item in request["entities"]:
        keys(item, {"id", "name", "team", "kind", "status"})
        eid = text(item["id"], "stable entity ID")
        if eid in entities or eid == NO_TD:
            raise ValueError("Duplicate or reserved entity ID")
        text(item["name"], "name"); text(item["team"], "team")
        if item["kind"] not in {"player", "defense_special_teams", "unknown"}:
            raise ValueError("Unknown entity kind")
        if item["status"] not in {"active", "questionable", "out", "unknown"}:
            raise ValueError("Unknown availability status")
        if request["market"] == "TEAM_FIRST_TD" and item["team"] != request["target_team"]:
            raise ValueError("Team-first hazards must be fitted for that team's risk set")
        entities[eid] = item
    if request["market"] == "GAME_FIRST_TD" and len({e["team"] for e in entities.values()}) != 2:
        raise ValueError("Game-first input must represent both competing teams")
    teams = {e["team"] for e in entities.values()}
    for team in teams:
        if not any(e["team"] == team and e["kind"] == "unknown" for e in entities.values()):
            raise ValueError("Each team needs an explicit unknown-scorer bucket")
    scenarios = request["scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("A nonempty scenario list is required")
    seen, weights = set(), []
    for scenario in scenarios:
        keys(scenario, {"id", "weight", "hazard_conditioning", "horizon_complete",
                        "active_entities", "intervals"})
        sid = text(scenario["id"], "scenario ID")
        if sid in seen:
            raise ValueError("Duplicate scenario ID")
        seen.add(sid)
        weights.append(probability(scenario["weight"], "scenario weight"))
        if weights[-1] == 0:
            raise ValueError("Exclude zero-weight scenarios")
        if scenario["hazard_conditioning"] != request["market"]:
            raise ValueError("Hazard risk set and market do not match")
        if scenario["horizon_complete"] is not True:
            raise ValueError("Cannot call truncated-survival mass 'no touchdown'")
        active = scenario["active_entities"]
        if not isinstance(active, list) or any(not isinstance(eid, str) for eid in active):
            raise ValueError("active_entities must be a list of stable IDs")
        if len(active) != len(set(active)) or set(active) - entities.keys():
            raise ValueError("Duplicate or unknown active entity")
        if any(entities[eid]["status"] == "out" for eid in active):
            raise ValueError("An OUT player cannot be active in a scenario")
        intervals = scenario["intervals"]
        if not isinstance(intervals, list) or not intervals:
            raise ValueError("A nonempty full-horizon interval sequence is required")
        previous_index = -1
        for interval in intervals:
            keys(interval, {"index", "hazards"})
            index = interval["index"]
            if isinstance(index, bool) or not isinstance(index, int) or index <= previous_index:
                raise ValueError("Intervals must be strictly ordered by integer index")
            previous_index = index
            hazards = interval["hazards"]
            if not isinstance(hazards, dict) or set(hazards) - entities.keys():
                raise ValueError("Unknown entity in hazards")
            values = []
            for eid, raw in hazards.items():
                hazard = probability(raw, f"hazard for {eid}")
                if hazard > 0 and eid not in active:
                    raise ValueError("Positive TD hazard for an unavailable entity")
                values.append(hazard)
            if math.fsum(values) > 1 + 1e-12:
                raise ValueError("Mutually exclusive interval hazards exceed one")
    if not math.isclose(math.fsum(weights), 1, abs_tol=1e-12, rel_tol=0):
        raise ValueError("Scenario weights must sum to one; no automatic normalization")
    return entities


def predict(request: dict, *, now: datetime | None = None) -> dict:
    entities = validate(request, now=now)
    result = {eid: 0.0 for eid in entities}
    result[NO_TD] = 0.0
    sensitivity = []
    for scenario in request["scenarios"]:
        survival = 1.0
        conditional = {eid: 0.0 for eid in entities}
        for interval in scenario["intervals"]:
            hazards = interval["hazards"]
            for eid, hazard in hazards.items():
                conditional[eid] += survival * hazard
            survival *= max(0.0, 1 - math.fsum(hazards.values()))
        conditional[NO_TD] = survival
        for eid, value in conditional.items():
            result[eid] += scenario["weight"] * value
        sensitivity.append({"scenario_id": scenario["id"], "weight": scenario["weight"],
                            "probabilities": conditional})
    if not math.isclose(math.fsum(result.values()), 1, abs_tol=1e-10, rel_tol=0):
        raise ArithmeticError("First-TD probability conservation failed")
    return {
        "version": VERSION,
        "event_id": request["event_id"],
        "market": request["market"],
        "target_team": request["target_team"],
        "include_overtime": request["include_overtime"],
        "kind": request["kind"],
        "status": "SYNTHETIC_TEST_ONLY" if request["kind"] == "SYNTHETIC" else "RESEARCH_UNCALIBRATED",
        "parameter_model_id": request["parameter_model_id"],
        "input_sha256": sha256(canonical(request)).hexdigest(),
        "probabilities": result,
        "scenario_results": sensitivity,
        "limitations": ["Hazards and scenario weights are external inputs, not fitted by this core",
                        "Input references are not independently certified",
                        "No Champion promotion, sportsbook edge or profit validation"],
    }


def score_distribution(probabilities: dict[str, float], outcome: str) -> dict:
    if not probabilities or outcome not in probabilities:
        raise ValueError("Outcome must belong to the complete predicted distribution")
    ps = {key: probability(p, key) for key, p in probabilities.items()}
    if not math.isclose(math.fsum(ps.values()), 1, abs_tol=1e-10, rel_tol=0):
        raise ValueError("The full mutually exclusive distribution must sum to one")
    p = ps[outcome]
    return {"multiclass_brier_sum": math.fsum((v - (key == outcome)) ** 2 for key, v in ps.items()),
            "log_loss": -math.log(p) if p > 0 else None,
            "infinite_log_loss": p == 0}
