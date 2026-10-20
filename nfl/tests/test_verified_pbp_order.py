"""Synthetic first-TD order regressions; not a fitted first-TD hazard test."""
import unittest
from verified_pbp_order import normalize_verified_order
from first_td_challenger.settlement import first_scorers


def sample(seq, play_id, scorer, qtr=1, game_id="g"):
    return {"game_id":game_id,"play_id":play_id,"order_sequence":seq,
        "qtr":qtr,"touchdown":1,"play_type":"pass",
        "two_point_attempt":0,"extra_point_attempt":0,
        "td_team":"A" if scorer=="A_RB" else "B","td_player_id":scorer}


class VerifiedPbpOrderTests(unittest.TestCase):
    def test_authoritative_order_not_play_id(self):
        later = sample(2, 100, "B_WR")
        earlier = sample(1, 900, "A_RB")
        out = normalize_verified_order([later, earlier], event_id="g")
        self.assertEqual([p["sequence"] for p in out["plays"]], [1,2])
        self.assertEqual(first_scorers(out["plays"],event_id="g",include_overtime=True)
                         ["game_first"]["scorer_id"], "A_RB")
        self.assertIn("UNVERIFIED", out["chronology_status"])

    def test_missing_order_abstains(self):
        x = sample(1, 10, "A_RB")
        del x["order_sequence"]
        with self.assertRaisesRegex(ValueError, "order_sequence"):
            normalize_verified_order([x], event_id="g")

    def test_duplicate_order_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            normalize_verified_order([sample(1, 10, "A_RB"), sample(1, 11, "B_WR")], event_id="g")

    def test_mixed_game_rejected(self):
        with self.assertRaises(ValueError):
            normalize_verified_order([sample(1, 10, "A_RB",game_id="other")], event_id="g")

    def test_order_must_match_quarters(self):
        with self.assertRaisesRegex(ValueError, "Chronology"):
            normalize_verified_order([sample(1, 10, "A_RB",qtr=4),sample(2, 11, "B_WR",qtr=1)],event_id="g")

    def test_missing_or_noninteger_order_fails_closed(self):
        for invalid in (None,1.0,True,-1):
            with self.subTest(invalid=invalid):
                x=sample(1,10,"A_RB")
                x["order_sequence"]=invalid
                with self.assertRaises(ValueError):
                    normalize_verified_order([x],event_id="g")


if __name__ == "__main__":
    unittest.main()
