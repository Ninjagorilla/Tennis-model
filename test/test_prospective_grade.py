import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prospective_grade import evaluate

def fixture():
    return {"fixture_id":"wta:example:2026-10-20","tour":"WTA",
            "issued_at":"2026-10-19T12:00:00Z",
            "starts_at":"2026-10-20T12:00:00Z",
            "results":{"champion":{"status":"ok","p_a":0.8},
                       "challenger":{"status":"ok","p_a":0.6},
                       "experimental":{"status":"unavailable","reason":"NO_HISTORY"}}}

def outcome():
    return {"fixture_id":"wta:example:2026-10-20","tour":"WTA",
            "winner":"a","completed_at":"2026-10-20T14:00:00Z",
            "recorded_at":"2026-10-20T15:00:00Z"}

class ProspectiveGradingTests(unittest.TestCase):
    def test_valid_scores_and_missing_model_not_imputed(self):
        report=evaluate([fixture()],[outcome()])
        self.assertEqual(report["metrics_by_tour"]["WTA"]["champion"]["brier"],0.04)
        self.assertEqual(report["metrics_by_tour"]["WTA"]["challenger"]["brier"],0.16)
        self.assertNotIn("experimental",report["metrics_by_tour"]["WTA"])
        self.assertEqual(report["exclusions"]["EXPERIMENTAL_UNAVAILABLE"],1)
        self.assertFalse(report["promotion_authorized"])

    def test_prediction_at_or_after_start_is_excluded(self):
        for issued in ("2026-10-20T12:00:00Z","2026-10-20T13:00:00Z"):
            with self.subTest(issued=issued):
                row=fixture();row["issued_at"]=issued
                report=evaluate([row],[outcome()])
                self.assertEqual(report["exclusions"]["POINT_IN_TIME_VIOLATION"],1)
                self.assertEqual(report["metrics_by_tour"],{})

    def test_future_result_or_early_record_is_excluded(self):
        row=outcome();row["recorded_at"]="2026-10-20T13:00:00Z"
        report=evaluate([fixture()],[row])
        self.assertEqual(report["exclusions"]["POINT_IN_TIME_VIOLATION"],1)

    def test_duplicate_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_FORECAST_ID"):
            evaluate([fixture(),fixture()],[outcome()])
        with self.assertRaisesRegex(ValueError,"DUPLICATE_OUTCOME_ID"):
            evaluate([fixture()],[outcome(),outcome()])

    def test_nonfinite_probability_not_graded(self):
        for value in (float("nan"),float("inf"),True,-0.1):
            row=fixture();row["results"]["champion"]["p_a"]=value
            report=evaluate([row],[outcome()])
            self.assertEqual(report["exclusions"]["CHAMPION_INVALID_PROBABILITY"],1)

    def test_tour_mismatch_rejected(self):
        row=outcome();row["tour"]="ATP"
        report=evaluate([fixture()],[row])
        self.assertEqual(report["exclusions"]["TOUR_MISMATCH"],1)

if __name__=="__main__":
    unittest.main()
