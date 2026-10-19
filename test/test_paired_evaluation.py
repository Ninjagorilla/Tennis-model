import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from paired_evaluation import paired

def forecast(fid,experimental=True):
 return {"fixture_id":fid,"tour":"ATP","results":{
 "champion":{"status":"ok","p_a":0.7},
 "challenger":{"status":"ok","p_a":0.6},
 "experimental":{"status":"ok","p_a":0.8} if experimental else {"status":"unavailable"}}}
class PairedTests(unittest.TestCase):
 def test_same_sample_only(self):
  result=paired([forecast("a"),forecast("b",False)],[{"fixture_id":"a","winner":"a"},{"fixture_id":"b","winner":"b"}])
  self.assertEqual(result["paired_by_tour"]["ATP"]["paired_fixtures"],1)
  self.assertEqual(result["paired_by_tour"]["ATP"]["models"]["champion"]["brier"],0.09)
  self.assertFalse(result["promotion_authorized"])
 def test_empty_sample_abstains(self):
  self.assertEqual(paired([forecast("a",False)],[{"fixture_id":"a","winner":"a"}])["paired_by_tour"],{})
if __name__=="__main__":unittest.main()
