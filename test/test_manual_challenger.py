import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import manual_challenger

class ManualChallengerTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,21,12,tzinfo=timezone.utc)
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"fixtures.json"
        self.patcher=patch.object(manual_challenger,"PATH",self.path)
        self.patcher.start()
    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()
    def row(self):
        return {"source_match_id":"manual:123","source_event_id":"manual:event","tour":"ATP","tournament":"Verified Challenger Event","tournament_key":"city","regime":"challenger","surface":"Hard","name_a":"Player Alpha","name_b":"Player Beta","source_player_ids":["p1","p2"],"starts_at":(self.now+timedelta(hours=5)).isoformat(),"round":"Round 1","event_source":"https://www.atptour.com/","surface_source":"https://www.atptour.com/","format_source":"https://www.atptour.com/","reviewed_at":self.now.isoformat(),"reviewer":"researcher"}
    def test_empty_ledger_fails_closed(self):
        self.assertEqual(manual_challenger.load(self.now)[0],[])
    def test_verified_manual_fixture(self):
        self.path.write_text(json.dumps([self.row()]))
        rows,health=manual_challenger.load(self.now)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["source_provenance"],"MANUAL_VERIFIED")
        self.assertEqual(health["accepted"],1)
    def test_stale_review_rejected(self):
        row=self.row();row["reviewed_at"]=(self.now-timedelta(days=2)).isoformat()
        self.path.write_text(json.dumps([row]))
        self.assertEqual(manual_challenger.load(self.now)[1]["rejected"],1)
    def test_duplicate_rejected(self):
        row=self.row();self.path.write_text(json.dumps([row,row]))
        self.assertEqual(manual_challenger.load(self.now)[1]["rejected"],1)
    def test_non_challenger_rejected(self):
        row=self.row();row["regime"]="main"
        self.path.write_text(json.dumps([row]))
        self.assertEqual(manual_challenger.load(self.now)[0],[])
if __name__=="__main__":unittest.main()
