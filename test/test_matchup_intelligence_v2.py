import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from matchup_intelligence_v2 import shadow,checked_feature

START="2026-10-20T10:00:00Z"
def entry(**changes):
    value={"status":"verified","observed_at":"2026-10-19T10:00:00Z",
           "source_url":"https://www.wtatennis.com/example",
           "source_sha256":"a"*64,"match_id":"case1","evidence_type":"observed",
           "raw":{"a":0.6,"b":0.4,"effective_n":150}}
    value.update(changes)
    return value

class MatchupV2Tests(unittest.TestCase):
    def test_all_missing_explicit_and_champion_unchanged(self):
        result=shadow(.62,START,"case1",{})
        self.assertEqual(result["baseline_p_a"],.62)
        self.assertEqual(len(result["missing_features"]),8)
        self.assertIsNone(result["candidate_delta_pp"])
        self.assertFalse(result["eligible_for_promotion"])

    def test_distinct_evidence_before_start_is_diagnostic_only(self):
        r=shadow(.62,START,"case1",{"style":entry(),"fatigue":entry()})
        self.assertEqual(r["verified_features"],["fatigue","style"])
        self.assertTrue(r["registered_prediction_unchanged"])
        self.assertIsNone(r["candidate_delta_pp"])
        self.assertIn("style",r["observed_feature_measures"])

    def test_injury_without_evidence_never_assumed_healthy(self):
        r=shadow(.6,START,"case1",{"injury":{"status":"unknown"}})
        self.assertEqual(r["missing_features"]["injury"],"FIXTURE_MISMATCH")

    def test_invalid_late_and_low_sample_rejected(self):
        for changes in ({"observed_at":START},
                        {"raw":{"a":0.5,"b":0.4,"effective_n":2}},
                        {"source_sha256":"bad"},
                        {"source_url":"https://fake.example.com"}):
            out=shadow(.6,START,"case1",{"h2h":entry(**changes)})
            self.assertEqual(out["verified_features"],[])

    def test_unsupported_probabilities(self):
        for x in (0,1,float("nan"),-1):
            with self.assertRaises(ValueError):shadow(x,START,"case1",{})
if __name__=="__main__":unittest.main()
