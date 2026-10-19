import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from result_reconciliation import grade

def evidence():
 f={"fixture_id":"case1","tour":"WTA","name_a":"A","name_b":"B",
    "issued_at":"2026-10-19T00:00:00Z","starts_at":"2026-10-20T00:00:00Z",
    "results":{"champion":{"status":"ok","p_a":0.7},"challenger":{"status":"unavailable"},"experimental":{"status":"unavailable"}}}
 o={"fixture_id":"case1","tour":"WTA","name_a":"A","name_b":"B",
    "winner":"a","result_type":"completed","source_count":2,"source_agreement":True,
    "completed_at":"2026-10-20T02:00:00Z","recorded_at":"2026-10-20T03:00:00Z"}
 o["observations"]=[{"provider":provider,"event_id":provider+"-42","winner":"a","result_type":"completed","name_a":"A","name_b":"B","observed_at":"2026-10-20T03:00:00Z"} for provider in ("espn","tenniscom")]
 return f,o

class ReconciliationTests(unittest.TestCase):
 def test_confirmed(self):
  f,o=evidence();r=grade([f],[o])
  self.assertEqual(r["reconciliation"]["verified_fixtures"],1)
  self.assertEqual(r["metrics_by_tour"]["WTA"]["champion"]["n"],1)
  self.assertFalse(r["promotion_authorized"])
 def test_one_source_not_enough(self):
  f,o=evidence();o["observations"]=o["observations"][:1]
  self.assertEqual(grade([f],[o])["reconciliation"]["rejected"]["case1"],"INDEPENDENT_CONFIRMATION_REQUIRED")
 def test_forged_source_flags_rejected(self):
  f,o=evidence();o.pop("observations")
  self.assertEqual(grade([f],[o])["reconciliation"]["rejected"]["case1"],"INDEPENDENT_CONFIRMATION_REQUIRED")
 def test_duplicate_provider_is_not_independent(self):
  f,o=evidence();o["observations"][1]["provider"]="espn"
  self.assertEqual(grade([f],[o])["reconciliation"]["rejected"]["case1"],"INDEPENDENT_CONFIRMATION_REQUIRED")
 def test_disagreeing_observations_are_rejected(self):
  f,o=evidence();o["observations"][1]["winner"]="b"
  self.assertEqual(grade([f],[o])["reconciliation"]["rejected"]["case1"],"INDEPENDENT_CONFIRMATION_REQUIRED")
 def test_opponent_swap_rejected(self):
  f,o=evidence();o["name_a"],o["name_b"]="B","A"
  for obs in o["observations"]:obs["name_a"],obs["name_b"]="B","A"
  self.assertEqual(grade([f],[o])["reconciliation"]["rejected"]["case1"],"PLAYER_ORIENTATION_MISMATCH")
 def test_retirement_rejected(self):
  f,o=evidence();o["result_type"]="retired"
  for obs in o["observations"]:obs["result_type"]="retired"
  self.assertEqual(grade([f],[o])["reconciliation"]["rejected"]["case1"],"NONSTANDARD_RESULT")
 def test_no_invented_settlement(self):
  f,_=evidence()
  self.assertEqual(grade([f],[])["reconciliation"]["verified_fixtures"],0)
if __name__=="__main__":unittest.main()
