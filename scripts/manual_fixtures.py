"""Manually reviewed offline singles fixtures for every tennis tour.

Default discovery source. Network access is deliberately absent.
Only signed-off official order-of-play entries may enter inference.
"""
import json
import re
from datetime import timedelta
from pathlib import Path
from collect import key, timestamp

PATH = Path("data/manual_fixtures.json")
REQUIRED = ("source_match_id", "source_event_id", "tour", "tournament",
            "tournament_key", "regime", "surface", "name_a", "name_b",
            "starts_at", "round", "event_source", "surface_source",
            "format_source", "source_player_ids", "reviewed_at", "reviewer")
TOURS = {("ATP", "main"), ("WTA", "main"), ("ATP", "challenger"),
         ("WTA", "wta125"), ("ATP", "main_qualifying"),
         ("WTA", "main_qualifying")}

def load(now, path=PATH, horizon_hours=48):
    if not path.is_file():
        return [], {"status": "missing", "accepted": 0, "rejected": 0}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("EXPECTED_LIST")
    except (OSError, ValueError):
        return [], {"status": "invalid", "accepted": 0, "rejected": 0}
    accepted, rejected, seen = [], 0, set()
    for row in rows:
        try:
            if not isinstance(row, dict) or any(not row.get(k) for k in REQUIRED):
                raise ValueError("REQUIRED_FIELD_MISSING")
            if (row["tour"], row["regime"]) not in TOURS:
                raise ValueError("UNKNOWN_TOUR_REGIME")
            if row["surface"] not in ("Hard", "Clay", "Grass"):
                raise ValueError("UNKNOWN_SURFACE")
            if not isinstance(row["source_player_ids"], list) or len(row["source_player_ids"]) != 2 or len(set(map(str, row["source_player_ids"]))) != 2:
                raise ValueError("INVALID_PLAYER_IDENTITIES")
            if not all(isinstance(row[k], str) and 3 <= len(row[k]) <= 160 for k in ("name_a", "name_b", "tournament")):
                raise ValueError("INVALID_NAMES")
            if key(row["name_a"]) == key(row["name_b"]):
                raise ValueError("DUPLICATE_PLAYERS")
            if not all(isinstance(row[k], str) and row[k].startswith("https://") for k in ("event_source", "surface_source", "format_source")):
                raise ValueError("OFFICIAL_SOURCE_REQUIRED")
            if not re.fullmatch(r"[a-zA-Z0-9:_-]{3,120}", str(row["source_match_id"])):
                raise ValueError("INVALID_MATCH_ID")
            start, review = timestamp(row["starts_at"]), timestamp(row["reviewed_at"])
            if not now < start <= now + timedelta(hours=horizon_hours):
                raise ValueError("OUTSIDE_SCAN_HORIZON")
            if not now - timedelta(hours=24) <= review <= now:
                raise ValueError("REVIEW_EXPIRED")
            identity = (row["tour"], row["source_match_id"])
            if identity in seen:
                raise ValueError("DUPLICATE_MATCH")
            seen.add(identity)
            a, b = row["name_a"], row["name_b"]
            accepted.append({k: row[k] for k in (
                "source_match_id", "source_event_id", "tour", "tournament",
                "tournament_key", "regime", "surface", "name_a", "name_b",
                "starts_at", "round", "event_source", "surface_source",
                "format_source", "source_player_ids")} | {
                "player_a": row["tour"] + ":" + key(a),
                "player_b": row["tour"] + ":" + key(b),
                "court_enclosure": row.get("court_enclosure", "Unknown"),
                "start_verified": True, "event_scope": "singles",
                "source_state": "scheduled", "best_of": 3,
                "deciding_tiebreak_target": 7, "format_verified": True,
                "timing_kind": "HUMAN_REVIEWED_OFFICIAL_ORDER_OF_PLAY",
                "source_provenance": "MANUAL_VERIFIED"})
        except (KeyError, ValueError, TypeError):
            rejected += 1
    return accepted, {"status": "manual_only", "accepted": len(accepted),
                      "rejected": rejected, "ledger_path": str(path)}
