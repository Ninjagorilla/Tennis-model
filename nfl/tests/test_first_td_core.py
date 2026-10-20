from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
from hashlib import sha256

from first_td_challenger.core import predict, score_distribution, NO_TD, canonical
from first_td_challenger.markets import (break_even, decimal_odds, expected_net_per_unit,
                                        independent_joint_probability, quoted_parlay_arithmetic)
from first_td_challenger.settlement import grade, first_scorers, normalize_nflverse_row
from first_td_challenger.adapter import audit_v91_snapshot


def example():
    entities = [
        {"id": "A_RB", "name": "Synthetic A runner", "team": "A", "kind": "player", "status": "active"},
        {"id": "B_WR", "name": "Synthetic B receiver", "team": "B", "kind": "player", "status": "active"},
        {"id": "A_UNKNOWN", "name": "A unmodeled scorer", "team": "A", "kind": "unknown", "status": "active"},
        {"id": "B_UNKNOWN", "name": "B unmodeled scorer", "team": "B", "kind": "unknown", "status": "active"},
    ]
    return {"event_id": "SYNTHETIC_A_B", "kind": "SYNTHETIC", "market": "GAME_FIRST_TD",
            "target_team": None, "include_overtime": True,
            "kickoff_utc": "2026-10-18T17:00:00Z", "data_as_of_utc": "2026-10-16T00:00:00Z",
            "parameter_model_id": "SYNTHETIC_HAND_SPECIFIED_NOT_FITTED",
            "source_refs": ["Synthetic arithmetic fixture; not NFL observations"], "entities": entities,
            "scenarios": [{"id": "fixed_path", "weight": 1.0, "hazard_conditioning": "GAME_FIRST_TD",
                           "horizon_complete": True, "active_entities": [e["id"] for e in entities],
                           "intervals": [{"index": 0, "hazards": {"A_RB": 0.2, "A_UNKNOWN": 0.1}},
                                         {"index": 1, "hazards": {"B_WR": 0.3, "B_UNKNOWN": 0.1}}]}]}


def play(sequence, scorer, team="A", **overrides):
    row = {"event_id": "g", "sequence": sequence, "period": 1, "touchdown": True,
           "no_play": False, "conversion_attempt": False, "scoring_team": team, "scorer_id": scorer}
    row.update(overrides)
    return row


def selection(**overrides):
    row = {"event_id": "g", "market": "GAME_FIRST_TD", "target_team": None,
           "entity_id": "A_RB", "include_overtime": True, "dnp_policy": "VOID",
           "no_td_policy": "LOSE", "rules_verified": True}
    row.update(overrides)
    return row


def event(**overrides):
    row = {"event_id": "g", "status": "FINAL", "complete_play_log": True,
           "participation": {"A_RB": True, "B_WR": True}, "source_refs": ["Synthetic final game log"]}
    row.update(overrides)
    return row


class ProbabilityCoreTests(unittest.TestCase):
    def test_exact_ordered_probabilities(self):
        p = predict(example())["probabilities"]
        self.assertAlmostEqual(p["A_RB"], .2)
        self.assertAlmostEqual(p["B_WR"], .21)
        self.assertAlmostEqual(p[NO_TD], .42)
        self.assertAlmostEqual(sum(p.values()), 1)

    def test_reverse_order_changes_first_td(self):
        req = example(); req["scenarios"][0]["intervals"].reverse()
        for i, step in enumerate(req["scenarios"][0]["intervals"]): step["index"] = i
        self.assertAlmostEqual(predict(req)["probabilities"]["A_RB"], .12)

    def test_weighted_scenarios(self):
        req = example(); s1 = req["scenarios"][0]; s1["weight"] = .4
        s2 = deepcopy(s1); s2["id"] = "second"; s2["weight"] = .6
        s2["intervals"] = [{"index": 0, "hazards": {"B_WR": 1.0}}]
        req["scenarios"].append(s2)
        self.assertAlmostEqual(predict(req)["probabilities"]["B_WR"], .4 * .21 + .6)

    def test_full_survival_no_td(self):
        req = example(); req["scenarios"][0]["intervals"] = [{"index": 0, "hazards": {}}]
        self.assertEqual(predict(req)["probabilities"][NO_TD], 1)

    def test_first_certain_absorbs_later(self):
        req = example(); req["scenarios"][0]["intervals"][0]["hazards"] = {"A_RB": 1.0}
        self.assertEqual(predict(req)["probabilities"]["B_WR"], 0)

    def test_out_player_rejected(self):
        req = example(); req["entities"][0]["status"] = "out"
        with self.assertRaises(ValueError): predict(req)

    def test_inactive_positive_hazard_rejected(self):
        req = example(); req["scenarios"][0]["active_entities"].remove("A_RB")
        with self.assertRaises(ValueError): predict(req)

    def test_out_zero_allocation_allowed(self):
        req = example(); req["entities"][0]["status"] = "out"
        req["scenarios"][0]["active_entities"].remove("A_RB")
        req["scenarios"][0]["intervals"][0]["hazards"]["A_RB"] = 0
        self.assertEqual(predict(req)["probabilities"]["A_RB"], 0)

    def test_unknown_bucket_preserved(self):
        p = predict(example())["probabilities"]
        self.assertAlmostEqual(p["A_UNKNOWN"], .1)
        self.assertAlmostEqual(p["B_UNKNOWN"], .07)

    def test_unknown_bucket_required(self):
        req = example(); req["entities"].pop()
        with self.assertRaises(ValueError): predict(req)

    def test_wrong_market_rejected(self):
        req = example(); req["market"] = "ATD"
        with self.assertRaises(ValueError): predict(req)

    def test_team_first_requires_own_risk_set(self):
        req = example(); req["market"] = "TEAM_FIRST_TD"; req["target_team"] = "A"
        with self.assertRaises(ValueError): predict(req)

    def test_valid_team_first(self):
        req = example(); req["market"] = "TEAM_FIRST_TD"; req["target_team"] = "A"
        req["entities"] = [e for e in req["entities"] if e["team"] == "A"]
        s = req["scenarios"][0]; s["hazard_conditioning"] = "TEAM_FIRST_TD"
        s["active_entities"] = [e["id"] for e in req["entities"]]; s["intervals"].pop()
        self.assertAlmostEqual(predict(req)["probabilities"]["A_RB"], .2)

    def test_no_reuse_of_game_first_conditioning(self):
        req = example(); req["scenarios"][0]["hazard_conditioning"] = "TEAM_FIRST_TD"
        with self.assertRaises(ValueError): predict(req)

    def test_overfull_hazards_rejected(self):
        req = example(); req["scenarios"][0]["intervals"][0]["hazards"]["A_RB"] = .95
        with self.assertRaises(ValueError): predict(req)

    def test_weights_not_silently_normalized(self):
        req = example(); req["scenarios"][0]["weight"] = .7
        with self.assertRaises(ValueError): predict(req)

    def test_bad_hazards(self):
        for v in (float("nan"), float("inf"), -.1, True, "0.2"):
            with self.subTest(value=v):
                req = example(); req["scenarios"][0]["intervals"][0]["hazards"]["A_RB"] = v
                with self.assertRaises(ValueError): predict(req)

    def test_unordered_intervals_rejected(self):
        req = example(); req["scenarios"][0]["intervals"].reverse()
        with self.assertRaises(ValueError): predict(req)

    def test_market_input_rejected(self):
        req = example(); req["american_odds"] = 1300
        with self.assertRaises(ValueError): predict(req)

    def test_nested_market_input_rejected(self):
        req = example(); req["scenarios"][0]["intervals"][0]["odds"] = 1300
        with self.assertRaises(ValueError): predict(req)

    def test_truncated_horizon_rejected(self):
        req = example(); req["scenarios"][0]["horizon_complete"] = False
        with self.assertRaises(ValueError): predict(req)

    def test_duplicate_id_rejected(self):
        req = example(); req["entities"].append(deepcopy(req["entities"][0]))
        with self.assertRaises(ValueError): predict(req)

    def test_no_future_or_post_event_input(self):
        req = example(); req["data_as_of_utc"] = req["kickoff_utc"]
        with self.assertRaises(ValueError): predict(req)

    def test_naive_timestamp_rejected(self):
        req = example(); req["data_as_of_utc"] = "2026-10-16T12:00:00"
        with self.assertRaises(ValueError): predict(req)

    def test_research_no_backdating(self):
        req = example(); req["kind"] = "RESEARCH"
        with self.assertRaises(ValueError): predict(req, now=datetime(2026, 10, 19, tzinfo=timezone.utc))

    def test_research_no_future_data(self):
        req = example(); req["kind"] = "RESEARCH"
        with self.assertRaises(ValueError): predict(req, now=datetime(2026, 10, 15, tzinfo=timezone.utc))

    def test_research_remains_uncalibrated(self):
        req = example(); req["kind"] = "RESEARCH"
        out = predict(req, now=datetime(2026, 10, 17, tzinfo=timezone.utc))
        self.assertEqual(out["status"], "RESEARCH_UNCALIBRATED")

    def test_250_random_conservation_cases(self):
        rng = random.Random(16102026)
        for _ in range(250):
            req = example(); intervals = []
            for j in range(25):
                raw = [rng.random() for k in req["entities"]]; scale = rng.random() / sum(raw)
                intervals.append({"index": j, "hazards": {e["id"]: x * scale for e, x in zip(req["entities"], raw)}})
            req["scenarios"][0]["intervals"] = intervals
            p = predict(req)["probabilities"]
            self.assertAlmostEqual(sum(p.values()), 1)
            self.assertTrue(all(0 <= v <= 1 for v in p.values()))


class SettlementTests(unittest.TestCase):
    def test_first_of_game_not_first_of_team(self):
        plays = [play(2, "A_RB"), play(1, "B_WR", "B")]
        self.assertEqual(grade(selection(), event(), plays)["grade"], "LOSS")
        self.assertEqual(grade(selection(market="TEAM_FIRST_TD", target_team="A"), event(), plays)["grade"], "WIN")

    def test_field_goal_does_not_settle(self):
        plays = [play(1, None, touchdown=False), play(2, "A_RB")]
        self.assertEqual(grade(selection(), event(), plays)["grade"], "WIN")

    def test_nullified_td_excluded(self):
        plays = [play(1, "B_WR", "B", no_play=True), play(2, "A_RB")]
        self.assertEqual(grade(selection(), event(), plays)["grade"], "WIN")

    def test_conversion_excluded(self):
        plays = [play(1, "B_WR", "B", conversion_attempt=True), play(2, "A_RB")]
        self.assertEqual(grade(selection(), event(), plays)["grade"], "WIN")

    def test_defense_return_can_be_first_td(self):
        plays = [play(1, "B_DEFENDER", "B"), play(2, "A_RB")]
        self.assertEqual(grade(selection(), event(), plays)["grade"], "LOSS")

    def test_no_td_explicit_lose(self):
        self.assertEqual(grade(selection(), event(), [])["grade"], "LOSS")

    def test_no_td_explicit_void(self):
        self.assertEqual(grade(selection(no_td_policy="VOID"), event(), [])["grade"], "VOID")

    def test_no_td_selection_wins(self):
        self.assertEqual(grade(selection(entity_id=NO_TD), event(), [])["grade"], "WIN")

    def test_no_td_selection_loses_on_td(self):
        self.assertEqual(grade(selection(entity_id=NO_TD), event(), [play(1, "A_RB")])["grade"], "LOSS")

    def test_overtime_switch(self):
        plays = [play(1, "A_RB", period=5)]
        self.assertEqual(grade(selection(), event(), plays)["grade"], "WIN")
        self.assertEqual(grade(selection(include_overtime=False), event(), plays)["grade"], "LOSS")

    def test_dnp_void(self):
        self.assertEqual(grade(selection(), event(participation={"A_RB": False}), [])["grade"], "VOID")

    def test_missing_participation_not_assumed_dnp(self):
        self.assertEqual(grade(selection(), event(participation={}), [])["grade"], "PENDING")

    def test_unknown_rules_pending(self):
        self.assertEqual(grade(selection(rules_verified=False), event(), [])["grade"], "PENDING")

    def test_partial_log_pending(self):
        self.assertEqual(grade(selection(), event(complete_play_log=False), [])["grade"], "PENDING")

    def test_live_game_pending(self):
        self.assertEqual(grade(selection(), event(status="IN_PROGRESS"), [])["grade"], "PENDING")

    def test_missing_scorer_not_false_loss(self):
        self.assertEqual(grade(selection(), event(), [play(1, None)])["grade"], "PENDING")

    def test_duplicate_sequence_rejected(self):
        with self.assertRaises(ValueError): grade(selection(), event(), [play(1, "A_RB"), play(1, "B_WR", "B")])

    def test_event_mismatch_rejected(self):
        with self.assertRaises(ValueError): grade(selection(event_id="other"), event(), [])

    def test_missing_event_identity_rejected(self):
        with self.assertRaises(ValueError): grade(selection(event_id=None), event(event_id=None), [])

    def test_conflicting_dnp_evidence_pending(self):
        self.assertEqual(grade(selection(), event(participation={"A_RB": False}), [play(1, "A_RB")])["grade"], "PENDING")

    def test_pass_touchdown_credit_is_receiver_not_passer(self):
        source = {"game_id": "g", "play_id": 1.0, "order_sequence": 1.0, "qtr": 1.0, "touchdown": 1.0, "play_type": "pass",
                  "two_point_attempt": 0.0, "extra_point_attempt": 0.0, "td_team": "A",
                  "td_player_id": "A_RB", "passer_player_id": "A_QB"}
        out = normalize_nflverse_row(source)
        self.assertEqual(out["scorer_id"], "A_RB")
        source["td_player_id"] = None
        self.assertIsNone(normalize_nflverse_row(source)["scorer_id"])

    def test_authoritative_order_sequence_overrides_play_id(self):
        early = {"game_id": "g", "play_id": 900, "order_sequence": 1,
                 "qtr": 1, "touchdown": 1, "play_type": "pass",
                 "two_point_attempt": 0, "extra_point_attempt": 0,
                 "td_team": "A", "td_player_id": "A_RB"}
        late = dict(early, play_id=100, order_sequence=2,
                    td_team="B", td_player_id="B_WR")
        plays = [normalize_nflverse_row(late), normalize_nflverse_row(early)]
        self.assertEqual(grade(selection(), event(), plays)["grade"], "WIN")
        with self.assertRaises(ValueError):
            normalize_nflverse_row({k:v for k,v in early.items() if k!="order_sequence"})

    def test_pbp_missing_flag_rejected(self):
        with self.assertRaises(ValueError): normalize_nflverse_row({"game_id": "g"})


class MarketMathTests(unittest.TestCase):
    def test_video_breakeven(self):
        self.assertAlmostEqual(break_even(1300), 1 / 14)
        self.assertAlmostEqual(break_even(1500), 1 / 16)
        self.assertAlmostEqual(break_even(700), 1 / 8)

    def test_video_parlay_payout(self):
        result = quoted_parlay_arithmetic([1300, 1500, 700], 20)
        self.assertEqual(result["gross_return"], 35840)
        self.assertEqual(result["net_profit"], 35820)
        self.assertEqual(result["american_odds"], 179100)

    def test_negative_american(self):
        self.assertEqual(decimal_odds(-200), 1.5)

    def test_bad_american(self):
        for v in (0, 90, -50, float("nan"), True):
            with self.assertRaises(ValueError): decimal_odds(v)

    def test_independence_must_be_explicit(self):
        with self.assertRaises(ValueError): independent_joint_probability([{"event_id": "g", "p": .2}])

    def test_same_game_multiplication_rejected(self):
        with self.assertRaises(ValueError): independent_joint_probability([{"event_id": "g", "p": .2}, {"event_id": "g", "p": .1}], independence_assumption=True)

    def test_independent_games_product(self):
        result = independent_joint_probability([{"event_id": "g1", "p": .2}, {"event_id": "g2", "p": .1}], independence_assumption=True)
        self.assertAlmostEqual(result["probability"], .02)

    def test_void_ev_correct(self):
        self.assertAlmostEqual(expected_net_per_unit(1300, .05, .85, .1), -.2)

    def test_ev_needs_full_distribution(self):
        with self.assertRaises(ValueError): expected_net_per_unit(1300, .1, .1)

    def test_proper_scores(self):
        s = score_distribution({"a": .2, "b": .8}, "a")
        self.assertAlmostEqual(s["multiclass_brier_sum"], 1.28)
        self.assertAlmostEqual(s["log_loss"], -math.log(.2))

    def test_zero_outcome_not_clipped(self):
        s = score_distribution({"a": 0, "b": 1}, "a")
        self.assertIsNone(s["log_loss"]); self.assertTrue(s["infinite_log_loss"])


class ArchiveAdapterTests(unittest.TestCase):
    def artifact(self):
        p = {"prediction": {"version": "NFL-v9.1-integrated-1", "event_id": "g",
                            "fit_protocol": {"as_of": "2026-10-01"},
                            "players": {"A": {"pid": {"atd": .4}}}},
             "input_data": {"event_id": "g", "kickoff_utc": "2026-10-04T17:00:00Z",
                            "rosters": {"A": [{"name": "Synthetic name", "player_id": "pid"}]}},
             "recorded_at_utc": "2026-10-04T16:00:00Z"}
        return {"payload": p, "sha256": sha256(canonical(p)).hexdigest()}

    def run_audit(self, obj, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.json"; path.write_text(json.dumps(obj))
            return audit_v91_snapshot(path, "Synthetic name", **kwargs)

    def test_atd_never_relabels_first_td(self):
        result = self.run_audit(self.artifact())
        self.assertEqual(result["archived_anytime_td_probability"], .4)
        self.assertIsNone(result["first_td_probability"])

    def test_hash_mismatch_blocks(self):
        obj = self.artifact(); obj["sha256"] = "bad"
        with self.assertRaises(ValueError): self.run_audit(obj)

    def test_other_event_blocks(self):
        with self.assertRaises(ValueError): self.run_audit(self.artifact(), expected_event_id="other")

    def test_model_identity_blocks(self):
        obj = self.artifact(); obj["payload"]["prediction"]["version"] = "other"
        obj["sha256"] = sha256(canonical(obj["payload"])).hexdigest()
        with self.assertRaises(ValueError): self.run_audit(obj)


if __name__ == "__main__":
    unittest.main()
