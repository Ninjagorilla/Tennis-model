import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from tennis_grading_audit import audit

def forecast():
    return {"fixture_id":"fixture","tour":"WTA","name_a":"Alpha","name_b":"Beta",
        "starts_at":"2026-10-19T12:00:00+00:00","issued_at":"2026-10-19T10:00:00+00:00",
        "results":{"champion":{"status":"ok","p_a":0.7},
                   "challenger":{"status":"ok","p_a":0.3},
                   "experimental":{"status":"ok","p_a":0.6}}}

def settlement():
    return {"fixture_id":"fixture","tour":"WTA","name_a":"Alpha","name_b":"Beta",
        "winner":"a","result_type":"completed",
        "completed_at":"2026-10-19T15:00:00+00:00",
        "recorded_at":"2026-10-19T15:02:00+00:00",
        "observations":[{"provider":p,"event_id":event,"name_a":"Alpha","name_b":"Beta",
            "winner":"a","result_type":"completed","observed_at":"2026-10-19T15:01:00+00:00"}
            for p,event in (("espn","111"),("tenniscom","sr:sport_event:222"))]}

class AuditTests(unittest.TestCase):
    def test_verified_match_grades_all_three_models(self):
        r=audit([forecast()],{"settlements":[settlement()],"health":[{"status":"ok"},{"status":"ok"}]})
        self.assertEqual(r["two_source_verified"],1)
        self.assertEqual(r["model_metrics_by_tour"]["WTA"]["champion"]["correct"],1)
        self.assertEqual(r["model_metrics_by_tour"]["WTA"]["challenger"]["correct"],0)
        self.assertEqual(r["paired"]["WTA"]["paired_fixtures"],1)
        self.assertFalse(r["promotion_authorized"])
    def test_single_source_is_never_graded(self):
        o=settlement();o["observations"]=o["observations"][:1]
        r=audit([forecast()],{"settlements":[o]})
        self.assertEqual(r["two_source_verified"],0)
        self.assertEqual(r["model_metrics_by_tour"],{})
        self.assertEqual(r["unverified_or_missing"],1)
    def test_disagreement_never_grades(self):
        o=settlement();o["observations"][1]["winner"]="b"
        self.assertEqual(audit([forecast()],{"settlements":[o]})["two_source_verified"],0)
    def test_missing_result_not_counted_as_loss(self):
        r=audit([forecast()],{"settlements":[]})
        self.assertEqual(r["two_source_verified"],0)
        self.assertEqual(r["model_metrics_by_tour"],{})
    def test_no_market_upset_claim(self):
        r=audit([forecast()],{"settlements":[settlement()]})
        self.assertIn("unavailable",r["market_upset_performance"])
if __name__=="__main__":unittest.main()
