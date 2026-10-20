"""Conservative grading of normalized, verified scoring-play records.

This is not a live feed. The caller must certify final status, feed completeness,
participation and event/rules identity. Missing evidence produces PENDING.
"""
from __future__ import annotations
from .core import MARKETS, NO_TD, keys, text


def first_scorers(plays: list[dict], *, event_id: str, include_overtime: bool) -> dict:
    if not isinstance(plays, list) or type(include_overtime) is not bool:
        raise ValueError("Expected play list and explicit overtime rule")
    first_game, first_team = None, {}
    seen = set()
    validated = []
    for play in plays:
        keys(play, {"event_id", "sequence", "period", "touchdown", "no_play",
                    "conversion_attempt", "scoring_team", "scorer_id"})
        if play["event_id"] != event_id:
            raise ValueError("Scoring-play event identity mismatch")
        sequence, period = play["sequence"], play["period"]
        if (isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0
                or isinstance(period, bool) or not isinstance(period, int) or period < 1):
            raise ValueError("Invalid play order or period")
        if sequence in seen:
            raise ValueError("Duplicate play sequence requires source reconciliation")
        seen.add(sequence)
        for field in ("touchdown", "no_play", "conversion_attempt"):
            if type(play[field]) is not bool:
                raise ValueError(f"{field} must be an explicit boolean")
        validated.append(play)
    for play in sorted(validated, key=lambda p: p["sequence"]):
        if not play["touchdown"] or play["no_play"] or play["conversion_attempt"]:
            continue
        if not include_overtime and play["period"] > 4:
            continue
        team = text(play["scoring_team"], "scoring team")
        scorer = play["scorer_id"]
        if scorer is not None:
            text(scorer, "scorer ID")
        outcome = {"scorer_id": scorer, "team": team, "sequence": play["sequence"]}
        if first_game is None:
            first_game = outcome
        if team not in first_team:
            first_team[team] = outcome
    return {"game_first": first_game, "team_first": first_team}


def grade(selection: dict, event: dict, plays: list[dict]) -> dict:
    keys(selection, {"event_id", "market", "target_team", "entity_id", "include_overtime",
                     "dnp_policy", "no_td_policy", "rules_verified"})
    keys(event, {"event_id", "status", "complete_play_log", "participation", "source_refs"})
    if not isinstance(event["participation"], dict):
        raise ValueError("Participation must be keyed by stable player ID")
    text(selection["event_id"], "selection event ID")
    text(event["event_id"], "result event ID")
    if selection["event_id"] != event["event_id"]:
        raise ValueError("Selection and game identity do not match")
    if selection["market"] not in MARKETS:
        raise ValueError("Unsupported market; no ATD to first-TD substitution")
    target = selection["target_team"]
    if selection["market"] == "TEAM_FIRST_TD":
        text(target, "target_team")
    elif target is not None:
        raise ValueError("Game-first market cannot have a target team")
    if selection["dnp_policy"] not in {"VOID", "ACTION"}:
        raise ValueError("Unknown nonparticipant rule")
    if selection["no_td_policy"] not in {"VOID", "LOSE"}:
        raise ValueError("Unknown no-TD rule")
    text(selection["entity_id"], "entity_id")
    if type(selection["include_overtime"]) is not bool:
        raise ValueError("Explicit overtime rule required")
    if selection["rules_verified"] is not True:
        return {"grade": "PENDING", "reason": "Book and exact contract rules unverified"}
    if not event["source_refs"] or not isinstance(event["source_refs"], list):
        return {"grade": "PENDING", "reason": "No event-result source evidence"}
    for ref in event["source_refs"]:
        text(ref, "result source")
    if event["status"] != "FINAL" or event["complete_play_log"] is not True:
        return {"grade": "PENDING", "reason": "Final result and complete play log required"}
    entity_id = selection["entity_id"]
    participated = event["participation"].get(entity_id)
    if entity_id != NO_TD:
        if participated is not None and type(participated) is not bool:
            raise ValueError("Participation must be true, false or unknown")
        if selection["dnp_policy"] == "VOID" and participated is None:
            return {"grade": "PENDING", "reason": "Participation evidence missing"}
    scorers = first_scorers(plays, event_id=event["event_id"], include_overtime=selection["include_overtime"])
    first = (scorers["game_first"] if selection["market"] == "GAME_FIRST_TD"
             else scorers["team_first"].get(target))
    # Reconcile scorer and participation evidence before returning a DNP void.
    if participated is False and first and first["scorer_id"] == entity_id:
        return {"grade": "PENDING", "reason": "Scorer and participation evidence conflict"}
    if entity_id != NO_TD and participated is False and selection["dnp_policy"] == "VOID":
        return {"grade": "VOID", "reason": "Verified nonparticipant; explicit DNP rule"}
    if first is None:
        if entity_id == NO_TD:
            return {"grade": "WIN", "reason": "No touchdown in the requested scope"}
        return {"grade": "VOID" if selection["no_td_policy"] == "VOID" else "LOSS",
                "reason": "No touchdown; applied explicitly supplied book rule"}
    if entity_id == NO_TD:
        return {"grade": "LOSS", "reason": "A touchdown occurred in the requested scope"}
    if first["scorer_id"] is None:
        return {"grade": "PENDING", "reason": "First TD occurred but scorer identity is unresolved"}
    return {"grade": "WIN" if first["scorer_id"] == entity_id else "LOSS", "first_touchdown": first}


def normalize_nflverse_row(row: dict) -> dict:
    """Normalize selected nflverse fields without guessing the scorer.

    Touchdown-player ID must be the actual scorer, never passer_player_id.
    Full source validation/completeness and final-status checks remain external.
    This accepts JSON numeric binary flags, not ambiguous CSV strings or NaN.
    """
    required = {"game_id", "play_id", "order_sequence", "qtr", "touchdown", "play_type", "two_point_attempt",
                "extra_point_attempt", "td_team", "td_player_id"}
    if not required <= row.keys():
        raise ValueError(f"Missing required PBP fields: {sorted(required - row.keys())}")
    def binary(field: str) -> bool:
        value = row[field]
        if isinstance(value, (int, float, bool)) and value in (0, 1):
            return bool(value)
        raise ValueError(f"Unresolved binary PBP field: {field}")
    def integer(field: str) -> int:
        value = row[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value).is_integer():
            raise ValueError(f"Invalid integer PBP field: {field}")
        return int(value)
    scorer = row["td_player_id"]
    if scorer == "":
        scorer = None
    if scorer is not None and not isinstance(scorer, str):
        raise ValueError("Invalid touchdown scorer ID; resolve missing data upstream")
    # play_id is an identifier, not authoritative chronological ordering.\n    integer("play_id")  # retain source validation, but never sort on this ID\n    play_type = text(row["play_type"], "play_type")
    return {"event_id": text(row["game_id"], "game_id"), "sequence": integer("order_sequence"),
            "period": integer("qtr"), "touchdown": binary("touchdown"),
            "no_play": play_type == "no_play",
            "conversion_attempt": binary("two_point_attempt") or binary("extra_point_attempt"),
            "scoring_team": row["td_team"], "scorer_id": scorer}
