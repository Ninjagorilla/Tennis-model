"""NFL Champion v9.0: an explicit-input, team-conserving TD probability kernel.

This is an implemented component, not a trained full NFL forecasting engine.
Inputs are scenario-specific team means and player opportunity weights. No market
odds, arbitrary 'backup penalty', or invented injury effect is used. Parameters
must come from a separately fitted upstream model or disclosed assumptions.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from itertools import combinations
from math import exp, expm1, isfinite, log1p
from typing import Any

CHANNELS = ("rush", "receive", "other_score")
VERSION = "NFL-Champion-9.0/TD-core-1.0"
TARGET = "touchdowns_scored_not_passing_credit"


def number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: expected a finite number")
    value = float(value)
    if not isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{label}: expected {'positive' if positive else 'nonnegative'} finite number")
    return value


def identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: expected a nonempty string")
    return value


def strict_keys(d: dict, required: set[str], optional: set[str] | None = None) -> None:
    if not isinstance(d, dict):
        raise ValueError("Expected JSON object")
    optional = optional or set()
    if missing := required - d.keys():
        raise ValueError(f"Missing required fields: {sorted(missing)}")
    if extra := d.keys() - required - optional:
        raise ValueError(f"Unsupported fields, including market inputs: {sorted(extra)}")


def vector(d: dict, label: str) -> dict[str, float]:
    strict_keys(d, set(CHANNELS))
    return {c: number(d[c], f"{label}.{c}") for c in CHANNELS}


def zero_probability(mean: float, shape: float | None) -> float:
    """P(N=0), where Var(N)=mean+mean**2/shape; None is Poisson."""
    mean = number(mean, "mean")
    if shape is not None:
        shape = number(shape, "dispersion_shape", positive=True)
    return exp(-mean if shape is None else -shape * log1p(mean / shape))


def count_probabilities(mean: float, shape: float | None) -> dict[str, float]:
    mean = number(mean, "mean")
    if shape is not None:
        shape = number(shape, "dispersion_shape", positive=True)
    if mean == 0:
        return {"expected_tds": 0.0, "zero": 1.0, "exactly_one": 0.0,
                "atd": 0.0, "two_plus": 0.0, "variance": 0.0}
    log_p0 = -mean if shape is None else -shape * log1p(mean / shape)
    p0 = exp(log_p0)
    p1 = p0 * mean if shape is None else p0 * shape * (mean / (shape + mean))
    atd = -expm1(log_p0)
    return {"expected_tds": mean, "zero": p0, "exactly_one": p1,
            "atd": atd, "two_plus": max(0.0, atd - p1),
            "variance": mean if shape is None else mean + mean * mean / shape}


def fair_american(p: float) -> float | None:
    """Null at 0/1, where finite fair odds do not exist. No clipping certainty."""
    p = number(p, "probability")
    if p > 1:
        raise ValueError("probability exceeds 1")
    if p in (0.0, 1.0):
        return None
    return -100 * p / (1 - p) if p >= 0.5 else 100 * (1 - p) / p


@dataclass(frozen=True)
class Player:
    player_id: str
    name: str
    status: str


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    probability: float
    team_means: dict[str, float]
    weights: dict[str, dict[str, float]]  # presence means active in this scenario
    unallocated_weights: dict[str, float]
    dispersion_shape: float | None
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class TDRequest:
    team: str
    event_id: str
    kind: str
    players: tuple[Player, ...]
    scenarios: tuple[Scenario, ...]

    @classmethod
    def from_dict(cls, d: dict) -> TDRequest:
        strict_keys(d, {"team", "event_id", "kind", "players", "scenarios"})
        if d["kind"] not in {"TEST_ONLY", "RESEARCH"}:
            raise ValueError("kind must be TEST_ONLY or RESEARCH; no live certification is implied")
        if not isinstance(d["players"], list) or not d["players"]:
            raise ValueError("Nonempty player list required")
        players = []
        for p in d["players"]:
            strict_keys(p, {"player_id", "name", "status"})
            if p["status"] not in {"active", "questionable", "out", "unknown"}:
                raise ValueError("Unrecognized player status")
            players.append(Player(identity(p["player_id"], "player_id"),
                                  identity(p["name"], "name"), p["status"]))
        ids = {p.player_id for p in players}
        if len(ids) != len(players):
            raise ValueError("Duplicate player ID; join by stable ID, not display name")
        if "__unallocated__" in ids:
            raise ValueError("Reserved player ID")
        out_ids = {p.player_id for p in players if p.status == "out"}
        if not isinstance(d["scenarios"], list) or not d["scenarios"]:
            raise ValueError("Nonempty scenario list required")
        scenarios = []
        for s in d["scenarios"]:
            strict_keys(s, {"scenario_id", "probability", "team_means", "weights",
                            "unallocated_weights", "dispersion_shape", "source_refs"})
            prob = number(s["probability"], "scenario probability", positive=True)
            if prob > 1:
                raise ValueError("Scenario probability exceeds 1")
            if not isinstance(s["weights"], dict):
                raise ValueError("weights must be keyed by player ID")
            if set(s["weights"]) - ids:
                raise ValueError("Unknown player ID in scenario")
            if set(s["weights"]) & out_ids:
                raise ValueError("OUT player cannot be active in any scenario")
            means = vector(s["team_means"], "team_means")
            weights = {pid: vector(v, pid) for pid, v in s["weights"].items()}
            other = vector(s["unallocated_weights"], "unallocated_weights")
            for c in CHANNELS:
                total = other[c] + sum(w[c] for w in weights.values())
                if means[c] > 0 and total <= 0:
                    raise ValueError(f"No allocation for positive team mean in {c}")
            shape = s["dispersion_shape"]
            if shape is not None:
                shape = number(shape, "dispersion_shape", positive=True)
            refs = s["source_refs"]
            if not isinstance(refs, list) or not refs:
                raise ValueError("Each scenario requires explicit source/assumption references")
            refs = tuple(identity(v, "source_ref") for v in refs)
            scenarios.append(Scenario(identity(s["scenario_id"], "scenario_id"), prob,
                                      means, weights, other, shape, refs))
        if len({s.scenario_id for s in scenarios}) != len(scenarios):
            raise ValueError("Duplicate scenario ID")
        if abs(sum(s.probability for s in scenarios) - 1) > 1e-10:
            raise ValueError("Scenario probabilities must sum to 1; no silent normalization")
        return cls(identity(d["team"], "team"), identity(d["event_id"], "event_id"),
                   d["kind"], tuple(players), tuple(scenarios))


def allocate(request: TDRequest, s: Scenario) -> dict[str, dict[str, float]]:
    """Allocate each team TD channel once, including an explicit unmodeled bucket."""
    amounts = {p.player_id: {c: 0.0 for c in CHANNELS} for p in request.players}
    amounts["__unallocated__"] = {c: 0.0 for c in CHANNELS}
    for c in CHANNELS:
        denominator = s.unallocated_weights[c] + sum(w[c] for w in s.weights.values())
        if denominator == 0:
            if s.team_means[c] != 0:
                raise ValueError("Positive mean without allocation")
            continue
        for pid, w in s.weights.items():
            amounts[pid][c] = s.team_means[c] * w[c] / denominator
        amounts["__unallocated__"][c] = s.team_means[c] * s.unallocated_weights[c] / denominator
    return amounts


def predict(request: TDRequest) -> dict:
    """Exact scenario-mixture marginal probabilities; no Monte Carlo needed."""
    # Validate direct dataclass construction as well as parsed JSON requests.
    serialized = asdict(request)
    serialized["players"] = list(serialized["players"])
    serialized["scenarios"] = list(serialized["scenarios"])
    for item in serialized["scenarios"]:
        item["source_refs"] = list(item["source_refs"])
    request = TDRequest.from_dict(serialized)
    fields = ("expected_tds", "zero", "exactly_one", "atd", "two_plus")
    ids = [p.player_id for p in request.players] + ["__unallocated__"]
    result = {pid: {f: 0.0 for f in fields} for pid in ids}
    for pid in ids:
        result[pid].update({"active_probability": 0.0, "second_moment": 0.0})
        result[pid]["channel_expected_tds"] = {c: 0.0 for c in CHANNELS}
    joint = {pair: 0.0 for pair in combinations(ids[:-1], 2)}
    scenario_report = []
    for s in request.scenarios:
        amounts = allocate(request, s)
        lambdas = {pid: sum(v.values()) for pid, v in amounts.items()}
        team_mean = sum(s.team_means.values())
        allocated = sum(lambdas.values())
        if abs(allocated - team_mean) > 1e-9 * max(1, team_mean):
            raise ArithmeticError("Team TD conservation failed")
        for pid, mean in lambdas.items():
            distribution = count_probabilities(mean, s.dispersion_shape)
            for f in fields:
                result[pid][f] += s.probability * distribution[f]
            result[pid]["second_moment"] += s.probability * (distribution["variance"] + mean ** 2)
            result[pid]["active_probability"] += s.probability * float(pid in s.weights or pid == "__unallocated__")
            for c in CHANNELS:
                result[pid]["channel_expected_tds"][c] += s.probability * amounts[pid][c]
        for i, j in joint:
            # Shared scoring environment G: conditional independent Poisson counts.
            both = (1 - zero_probability(lambdas[i], s.dispersion_shape)
                    - zero_probability(lambdas[j], s.dispersion_shape)
                    + zero_probability(lambdas[i] + lambdas[j], s.dispersion_shape))
            joint[i, j] += s.probability * max(0.0, both)
        scenario_report.append({"scenario_id": s.scenario_id, "probability": s.probability,
                                "team_td_mean": team_mean, "allocated_td_mean": allocated,
                                "unallocated_td_mean": lambdas["__unallocated__"],
                                "source_refs": list(s.source_refs)})
    player_meta = {p.player_id: p for p in request.players}
    for pid, r in result.items():
        r["variance"] = max(0.0, r.pop("second_moment") - r["expected_tds"] ** 2)
        r["fair_american_atd"] = fair_american(min(1.0, r["atd"]))
        r["fair_american_two_plus"] = fair_american(min(1.0, r["two_plus"]))
        r["p_atd_given_active"] = r["atd"] / r["active_probability"] if r["active_probability"] > 0 else None
        r["p_two_plus_given_active"] = r["two_plus"] / r["active_probability"] if r["active_probability"] > 0 else None
        if pid in player_meta:
            r.update({"player_id": pid, "name": player_meta[pid].name, "status": player_meta[pid].status})
        # These are scenario sensitivity ranges, not calibrated confidence intervals.
        conditional = [count_probabilities(sum(allocate(request, s)[pid].values()), s.dispersion_shape)
                       for s in request.scenarios]
        r["scenario_atd_range"] = [min(v["atd"] for v in conditional), max(v["atd"] for v in conditional)]
    team_mean = sum(s.probability * sum(s.team_means.values()) for s in request.scenarios)
    rows = sorted((r for pid, r in result.items() if pid != "__unallocated__"),
                  key=lambda r: (-r["atd"], r["player_id"]))
    return {"model": VERSION, "designation": "CHAMPION_BY_USER_OVERRIDE", "kind": request.kind,
            "runtime_scope": "TD_COMPONENT_ONLY", "target": TARGET, "team": request.team,
            "event_id": request.event_id, "calibration": "NOT_FITTED_OR_VALIDATED",
            "live_data_connected": False, "team_td_mean": team_mean, "players": rows,
            "unallocated": result["__unallocated__"], "scenarios": scenario_report,
            "joint_atd": [{"player_ids": [i, j], "probability_both_score": p} for (i, j), p in joint.items()],
            "warnings": ["Input-dependent research probabilities, not validated hit rates.",
                         "Team scoring means, role weights and scenario probabilities are supplied, not fitted here.",
                         "Unconditional nonparticipation probability differs from sportsbook void rules; active-conditional values are separate.",
                         "Other-score mean must cover return/recovery TDs to represent full scored-TD scope.",
                         "No winner, spread, points-total or yardage model is integrated in this component."]}
