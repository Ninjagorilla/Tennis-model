import sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from manual_fixture_review import validate
from reconcile_fixture_coverage import reconcile
NOW="2026-10-20T09:00:00+00:00"
def fixture():
 return {"source_match_id":"manual-reviewed-001","tour":"ATP","regime":"challenger",
 "tournament_key":"fort-worth","surface":"Hard","best_of":3,
 "deciding_tiebreak_target":7,"name_a":"Alpha Player","name_b":"Beta Player",
 "starts_at":"2026-10-20T19:00:00+00:00",
 "independent_receipts":[
 {"url":"https://www.atptour.com/en/scores/current-challenger/","sha256":"a"*64,"fetched_at":NOW,"fixture_and_surface_confirmed":True},
 {"url":"https://en.tennistemple.com/matches/2026-10-20","sha256":"b"*64,"fetched_at":NOW,"fixture_and_surface_confirmed":True}]}
class ReviewedFixtureTests(unittest.TestCase):
 def test_two_source_fixture(self):
  self.assertEqual(validate(fixture(),NOW)["player_a"],"ATP:alpha player")
 def test_one_source_rejected(self):
  m=fixture();m["independent_receipts"]=m["independent_receipts"][:1]
  with self.assertRaises(ValueError):validate(m,NOW)
 def test_same_host_rejected(self):
  m=fixture();m["independent_receipts"][1]["url"]="https://www.atptour.com/en/scores/current-challenger/"
  with self.assertRaises(ValueError):validate(m,NOW)
 def test_withdrawn_or_started_not_scored(self):
  m=fixture();m["starts_at"]=NOW
  with self.assertRaises(ValueError):validate(m,NOW)
 def test_unknown_surface_rejected(self):
  m=fixture();m["surface"]="Unknown"
  with self.assertRaises(ValueError):validate(m,NOW)
 def test_ambiguous_player_rejected(self):
  m=fixture();m["name_b"]=m["name_a"]
  with self.assertRaises(ValueError):validate(m,NOW)
 def test_missing_receipt_hash_rejected(self):
  m=fixture();m["independent_receipts"][0]["sha256"]="invalid"
  with self.assertRaises(ValueError):validate(m,NOW)
 def test_coverage_gap_detected_without_fabricated_matches(self):
  probe={"sources":{"tennistemple":{"status":"fetched_unverified_markup","mentions":{"fort_worth":True}}}}
  r=reconcile({"matches":[]},probe)
  self.assertEqual(r["tournaments"]["fort_worth"]["status"],"GAP_REQUIRES_REVIEW")
  self.assertFalse(r["complete_all_tours"])
 def test_invalid_manual_inputs_preserved_as_rejections(self):
  x=fixture();x["surface"]="Unknown"
  r=reconcile({"matches":[]},{"sources":{}},{"matches":[x]},NOW)
  self.assertEqual(r["reviewed_valid"],0)
  self.assertEqual(r["reviewed_rejected"][0]["error"],"UNKNOWN_SURFACE")
if __name__=="__main__":unittest.main()
