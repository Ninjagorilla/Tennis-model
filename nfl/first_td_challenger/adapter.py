"""Read-only audit bridge to the actual v9.1 saved JSON research snapshots.

ATD statistics are exposed as archived context only. They are never converted
into first-TD probabilities or passed to the new hazard estimator implicitly.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
from .core import canonical


def audit_v91_snapshot(path: str | Path, player_name: str, *, expected_event_id: str | None = None) -> dict:
    path = Path(path)
    artifact = json.loads(path.read_text())
    payload = artifact["payload"]
    actual_hash = sha256(canonical(payload)).hexdigest()
    if actual_hash != artifact["sha256"]:
        raise ValueError("Archived snapshot payload hash mismatch")
    prediction, inputs = payload["prediction"], payload["input_data"]
    if prediction["version"] != "NFL-v9.1-integrated-1":
        raise ValueError("Unexpected model identity; do not relabel another implementation")
    if inputs["event_id"] != prediction["event_id"]:
        raise ValueError("Archived input/prediction event mismatch")
    if expected_event_id is not None and expected_event_id != prediction["event_id"]:
        raise ValueError("Requested game differs from the archived game")
    matches = [(team, row) for team, roster in inputs["rosters"].items()
               for row in roster if row["name"] == player_name]
    if len(matches) != 1:
        raise ValueError("Name lookup is missing or ambiguous; resolve stable player ID")
    team, player = matches[0]
    stats = prediction["players"][team][player["player_id"]]
    return {"model_version": prediction["version"], "player": player_name,
            "player_id": player["player_id"], "team": team,
            "archived_event_id": prediction["event_id"], "kickoff_utc": inputs["kickoff_utc"],
            "recorded_at_utc": payload["recorded_at_utc"],
            "data_as_of": prediction["fit_protocol"]["as_of"],
            "payload_hash_verified": True, "payload_sha256": actual_hash,
            "archived_anytime_td_probability": stats["atd"],
            "first_td_probability": None,
            "comparison_status": "BLOCKED_UNSUPPORTED_FIRST_TD_MARKET",
            "limits": ["An archived read is not a fresh engine execution",
                       "A hash verifies integrity, not source truth or forecast skill",
                       "Archived anytime-TD probabilities cannot price this first-TD selection"]}
