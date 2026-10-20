import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from quality import identity,deduplicate,challenge,cross_source_opponent_conflicts
def fixture(name="Caty McNally",source="tc:1",start="2026-10-19T04:00:00+00:00"):
 return dict(tour="WTA",name_a=name,name_b="Sinja Kraus",source_match_id=source,tournament_key="osaka",regime="main",starts_at=start,surface="Hard",best_of=3,deciding_tiebreak_target=7)
def results(a=.53,b=.54,c=.55):
 return {k:{"status":"ok","p_a":p,"p_b":1-p} for k,p in zip(("champion","challenger","experimental"),(a,b,c))}
class QualityTests(unittest.TestCase):
 def test_verified_aliases(self):
  self.assertEqual(identity("WTA","Catherine McNally"),identity("WTA","Caty McNally"))
  self.assertEqual(identity("WTA","Shi Han"),identity("WTA","Han Shi"))
  self.assertNotEqual(identity("ATP","Han Shi"),identity("WTA","Han Shi"))
 def test_duplicate_merge(self):
  rows,meta=deduplicate([fixture("Catherine McNally","tc:1"),fixture("Caty McNally","123")])
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]["source_match_id"],"123")
  self.assertEqual(meta["duplicates_collapsed"],1)
 def test_conflicting_schedule_fails_closed(self):
  rows,meta=deduplicate([fixture(),fixture("Catherine McNally","123","2026-10-19T07:00:00+00:00")])
  self.assertEqual(rows,[]);self.assertEqual(meta["identity_conflicts"],1)
 def test_challenger_no_fabrication(self):
  row=fixture();row["results"]=results()
  before=str(row["results"]);d=challenge(row)
  self.assertEqual(d["status"],"complete");self.assertEqual(d["pick"],"Caty McNally")
  self.assertIn("FRAGILE_FAVORITE",d["flags"]);self.assertEqual(str(row["results"]),before)
 def test_missing_experimental_is_not_imputed(self):
  row=fixture();row["results"]=results();row["results"]["experimental"]={"status":"unavailable","reason":"PLAYER_HISTORY_MISSING"}
  d=challenge(row);self.assertEqual(d["status"],"partial")
  self.assertEqual(d["missing_models"],["experimental"]);self.assertIn("INCOMPLETE_MODEL_COVERAGE",d["flags"])
 def test_cross_provider_contradictory_opponent_fails_closed(self):
  a=fixture("Kimberly Birrell","tc:sr:sport_event:1");a["name_b"]="Kayla Day"
  b=fixture("Kimberly Birrell","555");b["name_b"]="Sofia Kenin"
  rows,n=cross_source_opponent_conflicts([a,b])
  self.assertEqual(rows,[]);self.assertEqual(n,2)
 def test_other_match_and_distant_schedule_are_preserved(self):
  a=fixture("Kimberly Birrell","tc:sr:sport_event:1");a["name_b"]="Kayla Day"
  b=fixture("Kimberly Birrell","555","2026-10-20T20:00:00+00:00");b["name_b"]="Sofia Kenin"
  rows,n=cross_source_opponent_conflicts([a,b])
  self.assertEqual(len(rows),2);self.assertEqual(n,0)
 def test_disagreement(self):
  row=fixture();row["results"]=results(.7,.66,.4)
  d=challenge(row);self.assertIn("MODEL_DISAGREEMENT",d["flags"])
  self.assertIn("HIGH_PROBABILITY_SPREAD",d["flags"])
if __name__=="__main__":unittest.main()
