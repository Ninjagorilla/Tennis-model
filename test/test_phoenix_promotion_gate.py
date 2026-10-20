"""Regression tests for the three-sport Champion promotion evidence gate."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import math
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from phoenix_promotion_gate import evaluate

WINDOWS = dict(fit_end_utc="2024-12-30T00:00:00Z",
    calibration_start_utc="2025-01-01T00:00:00Z",
    calibration_end_utc="2025-12-30T00:00:00Z",
    holdout_start_utc="2026-01-01T00:00:00Z",
    holdout_end_utc="2027-01-01T00:00:00Z")


def fixture(i, sport="Tennis", target="ATP_MATCH"):
    event = datetime(2026, 2, 1, tzinfo=timezone.utc) + timedelta(minutes=i)
    fmt = lambda d: d.isoformat().replace("+00:00", "Z")
    return dict(sport=sport, target=target, event_id=str(i),
        champion_id="frozen_champion_v1", challenger_id="research_challenger_v2",
        event_start_utc=fmt(event), forecast_asof_utc=fmt(event - timedelta(hours=2)),
        source_released_utc=fmt(event - timedelta(hours=3)),
        frozen_at_utc=fmt(event - timedelta(hours=1)),
        outcome_released_utc=fmt(event + timedelta(hours=4)),
        forecast_sha256="a"*64, source_vintage_sha256="b"*64,
        champion_p=0.2, challenger_p=0.8, outcome=1)


class GateTests(unittest.TestCase):
    def run_gate(self, rows, **changes):
        return evaluate(rows, resamples=250, **{**WINDOWS, **changes})

    def test_no_data_is_insufficient(self):
        r = self.run_gate([])
        self.assertEqual(r["status"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(r["promotion_authorized"])

    def test_n_199_never_promotes(self):
        r = self.run_gate([fixture(i) for i in range(199)])
        self.assertEqual(r["n"], 199)
        self.assertEqual(r["status"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(r["statistical_gate_pass"])

    def test_n_250_strong_pair_can_clear_statistical_gate_only(self):
        r = self.run_gate([fixture(i) for i in range(250)])
        self.assertTrue(r["statistical_gate_pass"])
        self.assertLess(r["delta_brier_ci"][1], 0)
        self.assertLess(r["delta_log_loss_ci"][1], 0)
        self.assertFalse(r["promotion_authorized"])
        self.assertIn("UNVERIFIED", r["source_authenticity"])

    def test_equal_predictions_do_not_earn_champion(self):
        rows = [fixture(i) for i in range(250)]
        for r in rows:
            r["challenger_p"] = r["champion_p"]
        result = self.run_gate(rows)
        self.assertEqual(result["delta_brier_ci"], [0, 0])
        self.assertEqual(result["status"], "NO_PROMOTION")

    def test_bad_probabilities_fail_closed(self):
        for bad in (math.nan, math.inf, None, -1, 1, "0.8"):
            with self.subTest(bad=bad):
                r = fixture(0); r["challenger_p"] = bad
                with self.assertRaises(ValueError):
                    self.run_gate([r])

    def test_duplicate_event_is_never_silently_overwritten(self):
        r = fixture(1)
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            self.run_gate([r, dict(r)])

    def test_same_event_observation_is_leakage(self):
        r = fixture(0)
        r["source_released_utc"] = r["event_start_utc"]
        with self.assertRaisesRegex(ValueError, "POINT_IN_TIME"):
            self.run_gate([r])

    def test_forecast_at_start_is_leakage(self):
        r = fixture(0)
        r["frozen_at_utc"] = r["event_start_utc"]
        with self.assertRaises(ValueError):
            self.run_gate([r])

    def test_result_must_be_released_after_event(self):
        r = fixture(0)
        r["outcome_released_utc"] = r["forecast_asof_utc"]
        with self.assertRaises(ValueError):
            self.run_gate([r])

    def test_disjoint_fit_calibration_holdout(self):
        with self.assertRaisesRegex(ValueError, "WINDOWS_OVERLAP"):
            self.run_gate([fixture(0)], calibration_end_utc="2026-02-15T00:00:00Z")

    def test_unpaired_sports_or_targets_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNPAIRED_COHORTS"):
            self.run_gate([fixture(0), fixture(1, sport="NFL")])

    def test_malformed_receipt_rejected(self):
        r = fixture(0); r["forecast_sha256"] = "unknown"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.run_gate([r])

    def test_missing_identity_rejected(self):
        r = fixture(0); del r["event_id"]
        with self.assertRaisesRegex(ValueError, "MISSING_FIELDS"):
            self.run_gate([r])

    def test_deterministic_intervals(self):
        rows = [fixture(i) for i in range(250)]
        self.assertEqual(self.run_gate(rows), self.run_gate(rows))

    def test_both_metrics_required(self):
        rows = [fixture(i) for i in range(250)]
        for i, r in enumerate(rows):
            if i % 2:
                r["outcome"] = 0
        result = self.run_gate(rows)
        self.assertEqual(result["status"], "NO_PROMOTION")
        self.assertFalse(result["statistical_gate_pass"])


if __name__ == "__main__":
    unittest.main()
