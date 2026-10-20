"""Opt-in NFL first-TD chronology adapter, preserving the pinned archive.

Native nflverse PBP play_id is not an independently verified event sequence
certificate. The caller must supply separately evidenced order_sequence values.
This module verifies consistency, NOT the external truth of those values.
"""
from first_td_challenger.settlement import normalize_nflverse_row


def normalize_verified_order(rows, *, event_id):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Complete, nonempty play sequence required")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("Event identity required")
    seen = set()
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or row.get("game_id") != event_id:
            raise ValueError("Mixed or missing event identity")
        if "order_sequence" not in row:
            raise ValueError("Verified external order_sequence required; cannot infer it from play_id")
        seq = row["order_sequence"]
        if type(seq) is not int or seq < 0:
            raise ValueError("Source order_sequence must be nonnegative integer")
        if seq in seen:
            raise ValueError("Duplicate source event order")
        seen.add(seq)
        play = normalize_nflverse_row(row)
        play["sequence"] = seq
        normalized.append(play)
    normalized.sort(key=lambda r: r["sequence"])
    periods = [p["period"] for p in normalized]
    if any(b < a for a, b in zip(periods, periods[1:])):
        raise ValueError("Chronology conflicts with quarter order")
    return {"event_id": event_id, "plays": normalized,
            "chronology_status": "ORDER_CONSISTENCY_ONLY_SOURCE_AUTHENTICITY_UNVERIFIED",
            "risk": "No original PBP source or signed order receipt included"}
