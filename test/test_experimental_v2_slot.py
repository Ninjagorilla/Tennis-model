import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from scan import project,NAMES

class ExperimentalV2SlotTests(unittest.TestCase):
 def test_label_is_v2(self):
  self.assertIn("V2",NAMES["experimental"])
 def test_public_projection_keeps_score_and_evidence(self):
  ready={"version":"MATCHUP_INTELLIGENCE_V2_SHADOW_0_1",
         "registered_prediction_unchanged":True,"verified_features":[],
         "missing_features":{"style":"MISSING_OR_UNVERIFIED"}}
  row={"model":"experimental","result":{"p_a":0.61,"p_b":0.39,
       "model_id":"EXPERIMENTAL_MATCHUP_INTELLIGENCE_V2_0_1",
       "state_date":"2026-10-10","artifact_sha256":"a"*64,
       "research_only":True,"explanation":{},"v2_readiness":ready}}
  out=project(row)
  self.assertEqual(out["model_id"],"EXPERIMENTAL_MATCHUP_INTELLIGENCE_V2_0_1")
  self.assertEqual(out["p_a"],0.61)
  self.assertEqual(out["v2_readiness"],ready)
 def test_prior_registered_scores_remain_valid(self):
  row={"model":"champion","result":{"p_a":0.61,"p_b":0.39,
       "model_id":"WTA_CHAMPION_SRELO_1_0","state_date":"2026-10-05",
       "artifact_sha256":"b"*64,"research_only":True,"explanation":{}}}
  self.assertEqual(project(row)["p_a"],0.61)
if __name__=="__main__":unittest.main()
