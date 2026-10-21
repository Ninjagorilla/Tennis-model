import json,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from manual_challenger import load
class ManualFixtureTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,20,12,tzinfo=timezone.utc)
  self.row=dict(name_a="John Smith",name_b="James Jones",source_match_id="abc123",source_event_id="event1",tournament="Test Challenger",tournament_key="test",starts_at=(self.now+timedelta(hours=3)).isoformat(),surface="Hard",source_url="https://www.atptour.com/en/scores/current",source_checked_at=self.now.isoformat(),source_player_ids=["11","22"])
 def check(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"fixtures.json";p.write_text(json.dumps({"schema_version":1,"fixtures":[self.row]}))
   return load(p,self.now)
 def test_valid(self):self.assertEqual(len(self.check()),1)
 def test_reject_untrusted_source(self):
  self.row["source_url"]="https://not-atptour.com/event"
  with self.assertRaises(ValueError):self.check()
 def test_reject_stale(self):
  self.row["source_checked_at"]=(self.now-timedelta(hours=3)).isoformat()
  with self.assertRaises(ValueError):self.check()
 def test_reject_missing_ids(self):
  self.row["source_player_ids"]=["","22"]
  with self.assertRaises(ValueError):self.check()
if __name__=="__main__":unittest.main()
