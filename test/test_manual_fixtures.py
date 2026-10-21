"""Regression tests for manually reviewed offline fixture records."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from manual_fixtures import load

class ManualFixturesTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 21, 18, tzinfo=timezone.utc)
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "fixtures.json"
        self.row = {
            "source_match_id": "official:match_1", "source_event_id": "official:event_1",
            "tour": "ATP", "regime": "challenger", "tournament": "Example Challenger",
            "tournament_key": "example", "surface": "Hard",
            "name_a": "Example Player One", "name_b": "Example Player Two",
            "source_player_ids": ["p1", "p2"], "starts_at": (self.now + timedelta(hours=28)).isoformat(),
            "reviewed_at": (self.now - timedelta(hours=2)).isoformat(),
            "round": "R16", "reviewer": "human",
            "event_source": "https://www.atptour.com/", "surface_source": "https://www.atptour.com/",
            "format_source": "https://www.atptour.com/"
        }
    def tearDown(self):
        self.tmp.cleanup()
    def write(self, rows):
        self.path.write_text(json.dumps(rows), encoding="utf-8")
    def test_all_tour_categories(self):
        for tour, regime in [("ATP","main"),("WTA","main"),("ATP","challenger"),("WTA","wta125")]:
            x = dict(self.row, tour=tour, regime=regime)
            self.write([x])
            valid, result = load(self.now, self.path)
            self.assertEqual((len(valid), result["rejected"]), (1,0))
    def test_second_day_included(self):
        self.write([self.row])
        self.assertEqual(load(self.now, self.path)[1]["accepted"], 1)
    def test_duplicate_id_rejected(self):
        self.write([self.row,self.row])
        self.assertEqual(load(self.now, self.path)[1]["rejected"], 1)
    def test_expired_review_rejected(self):
        self.write([dict(self.row,reviewed_at=(self.now-timedelta(hours=25)).isoformat())])
        self.assertEqual(load(self.now, self.path)[1]["accepted"], 0)
    def test_missing_source_rejected(self):
        self.write([dict(self.row,event_source="")])
        self.assertEqual(load(self.now, self.path)[1]["accepted"], 0)
    def test_no_synthetic_fixtures(self):
        self.write([])
        self.assertEqual(load(self.now, self.path)[0], [])

if __name__ == "__main__":
    unittest.main()
