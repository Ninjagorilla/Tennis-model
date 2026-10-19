import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from quality import challenge
from verify_scan import verify
def example():
 m={"tour":"WTA","name_a":"Caty McNally","name_b":"Sinja Kraus","starts_at":"2026-10-19T04:00:00+00:00","regime":"main","tournament_key":"osaka"}
 m["results"]={role:{"status":"ok","p_a":.55,"p_b":.45} for role in ("champion","challenger","experimental")}
 m["devils_advocate"]=challenge(m)
 return {"schema_version":2,"prediction_status":"available","matches":[m],
         "models":[{"id":role,"predictions":1} for role in ("champion","challenger","experimental")],
         "coverage":{},"build":{"run_id":"test"}}
class ScanGateTests(unittest.TestCase):
 def test_valid(self):
  errors,report=verify(example(),True);self.assertEqual(errors,[]);self.assertEqual(report["three_model_coverage"],1)
 def test_alias_duplicate(self):
  d=example();m=copy.deepcopy(d["matches"][0]);m["name_a"]="Catherine McNally";m["devils_advocate"]=challenge(m);d["matches"].append(m)
  for model in d["models"]:model["predictions"]=2
  errors,_=verify(d);self.assertIn("DUPLICATE_FIXTURE",errors)
 def test_blocked_rejected(self):
  d=example();d["matches"]=[];d["prediction_status"]="blocked"
  for model in d["models"]:model["predictions"]=0
  errors,_=verify(d);self.assertIn("BLOCKED_SCAN",errors)
 def test_falsified_challenger_rejected(self):
  d=example();d["matches"][0]["devils_advocate"]["pick"]="Wrong Player"
  errors,_=verify(d);self.assertIn("CHALLENGER_MISMATCH",errors)
 def test_missing_model_is_partial_not_imputed(self):
  d=example();m=d["matches"][0];m["results"]["experimental"]={"status":"unavailable","reason":"PLAYER_HISTORY_MISSING"}
  m["devils_advocate"]=challenge(m);d["models"][2]["predictions"]=0
  errors,report=verify(d);self.assertEqual(errors,[]);self.assertEqual(report["three_model_coverage"],0)
 def test_invalid_probability(self):
  d=example();d["matches"][0]["results"]["champion"]["p_a"]=.99
  errors,_=verify(d);self.assertIn("INVALID_PROBABILITY",errors)
 def test_nonfinite_probabilities_fail_closed(self):
  for invalid in (float("nan"),float("inf"),-float("inf")):
   for field in ("p_a","p_b"):
    with self.subTest(value=str(invalid),field=field):
     d=example();d["matches"][0]["results"]["champion"][field]=invalid
     errors,_=verify(d)
     self.assertIn("INVALID_PROBABILITY",errors)
 def test_boolean_probabilities_fail_closed(self):
  d=example();d["matches"][0]["results"]["champion"]["p_a"]=True
  errors,_=verify(d)
  self.assertIn("INVALID_PROBABILITY",errors)
if __name__=="__main__":unittest.main()
