import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from quality import challenge
from verify_scan import verify
from fixture_ledger import window, TOURS
def example():
 m={"tour":"WTA","name_a":"Caty McNally","name_b":"Sinja Kraus","starts_at":"2026-10-19T04:00:00+00:00","regime":"main","tournament_key":"osaka"}
 m["results"]={role:{"status":"ok","p_a":.55,"p_b":.45} for role in ("champion","challenger","experimental")}
 m["devils_advocate"]=challenge(m)
 m['verification']={'providers':['WTA','TENNIS_COM'],'source_urls':['https://www.wtatennis.com/schedule','https://www.tennis.com/schedule']}
 w=window('2026-10-18')
 coverage={'status':'PARTIAL','window':w,'count_tolerance':0,'reasons':['MISSING_SOURCE_SCOPE'],
           'counts':[{'tour':t,'utc_date':day,'source_counts':{'WTA':None,'TENNIS_COM':None},'verified_count':0,'status':'PARTIAL'} for day in w['utc_dates'] for t in TOURS]}
 return {"schema_version":2,"prediction_status":"available","matches":[m],
         "models":[{"id":role,"predictions":1} for role in ("champion","challenger","experimental")],
         "coverage":coverage,"scan_status":"PARTIAL","build":{"run_id":"test"}}
class ScanGateTests(unittest.TestCase):
 def test_valid(self):
  errors,report=verify(example(),True);self.assertEqual(errors,[]);self.assertEqual(report["three_model_coverage"],1)
 def test_missing_coverage_gate_rejected(self):
  d=example();d['coverage']={}
  self.assertTrue(any(e.startswith('UNVERIFIED_LEDGER_COVERAGE') for e in verify(d)[0]))
 def test_same_publisher_verification_rejected(self):
  d=example();d['matches'][0]['verification']={'providers':['WTA'],'source_urls':['https://www.wtatennis.com/a','https://www.wtatennis.com/b']}
  self.assertTrue(any(e.startswith('UNVERIFIED_LEDGER_COVERAGE') for e in verify(d)[0]))
 def test_false_complete_count_gate_rejected(self):
  d=example();d['scan_status']=d['coverage']['status']='COMPLETE'
  self.assertTrue(any(e.startswith('UNVERIFIED_LEDGER_COVERAGE') for e in verify(d)[0]))
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
 def test_rejected_manual_challenger_blocks_scan(self):
  d=example();d["coverage"]={"manual_challenger":{"accepted":1,"rejected":1}}
  errors,_=verify(d)
  self.assertIn("REJECTED_MANUAL_CHALLENGER_FIXTURES",errors)
 def test_empty_available_snapshot_rejected(self):
  d=example();d["matches"]=[]
  for model in d["models"]:model["predictions"]=0
  errors,_=verify(d)
  self.assertIn("AVAILABLE_WITHOUT_FIXTURES",errors)
 def test_malformed_coverage_reports_error(self):
  d=example();d["coverage"]=None
  errors,report=verify(d)
  self.assertIn("MALFORMED_COVERAGE",errors)
  self.assertEqual(report["identity_diagnostics"],{})
 def test_boolean_probabilities_fail_closed(self):
  d=example();d["matches"][0]["results"]["champion"]["p_a"]=True
  errors,_=verify(d)
  self.assertIn("INVALID_PROBABILITY",errors)
if __name__=="__main__":unittest.main()
