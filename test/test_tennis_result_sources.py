import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from tennis_result_sources import espn_observations,tenniscom_observations,resolve

NOW=datetime(2026,10,21,0,tzinfo=timezone.utc)
def fixture():
    return {"fixture_id":"x","tour":"WTA","name_a":"Test One","name_b":"Test Two",
            "starts_at":"2026-10-20T12:00:00Z","source_match_id":"7"}
def completed():
    return {"provider":"espn","tour":"WTA","event_id":"7","name_a":"Test One",
            "name_b":"Test Two","winner_name":"Test One","result_type":"completed",
            "scheduled_at":"2026-10-20T12:00:00Z","observed_at":"2026-10-20T14:00:00Z",
            "url":"https://site.api.espn.com/fixture","source_sha256":"a"*64}

class SourceTests(unittest.TestCase):
    def test_verified_matching_provider_results(self):
        other={**completed(),"provider":"tenniscom","event_id":"sr:sport_event:10",
               "url":"https://www.tennis.com/"}
        rows,excluded=resolve([fixture()],[completed(),other],NOW)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["winner"],"a")
        self.assertEqual(len(rows[0]["observations"]),2)

    def test_disagreement_quarantined(self):
        other={**completed(),"provider":"tenniscom","event_id":"sr:sport_event:10",
               "winner_name":"Test Two"}
        rows,excluded=resolve([fixture()],[completed(),other],NOW)
        self.assertEqual(rows,[])
        self.assertEqual(excluded["x"],"SOURCE_WINNER_DISAGREEMENT")

    def test_provider_event_id_mismatch_rejected(self):
        other={**completed(),"provider":"tenniscom","event_id":"sr:sport_event:10"}
        wrong={**completed(),"event_id":"8"}
        rows,excluded=resolve([fixture()],[wrong,other],NOW)
        self.assertEqual(rows,[])
        self.assertEqual(excluded["x"],"SOURCE_MISSING_OR_AMBIGUOUS")

    def test_conflicting_duplicate_same_provider_event_is_quarantined(self):
        other={**completed(),"provider":"tenniscom","event_id":"sr:sport_event:10"}
        conflict={**completed(),"winner_name":"Test Two"}
        rows,excluded=resolve([fixture()],[completed(),conflict,other],NOW)
        self.assertEqual(rows,[])
        self.assertEqual(excluded["x"],"SOURCE_MISSING_OR_AMBIGUOUS")

    def test_completed_espn_event(self):
        doc={"events":[{"name":"Demo Open","groupings":[{"grouping":{"slug":"womens-singles"},
            "competitions":[{"id":"7","status":{"type":{"state":"post","completed":True,
            "name":"STATUS_FINAL"}},"date":"2026-10-20T12:00:00Z",
            "competitors":[{"id":"1","winner":True,"athlete":{"displayName":"Test One"}},
            {"id":"2","winner":False,"athlete":{"displayName":"Test Two"}}]}]}]}]}
        self.assertEqual(espn_observations(doc,"WTA","2026-10-21T00:00:00Z","https://example.org","a"*64)[0]["winner_name"],"Test One")

    def test_retired_espn_not_graded(self):
        doc={"events":[{"groupings":[{"grouping":{"slug":"womens-singles"},"competitions":[
            {"id":"7","status":{"type":{"state":"post","completed":True,
            "name":"STATUS_FINAL"}},"note":"Retirement",
            "competitors":[{"id":"1","winner":True,"athlete":{"displayName":"Test One"}},
            {"id":"2","winner":False,"athlete":{"displayName":"Test Two"}}]}]}]}]}
        self.assertEqual(espn_observations(doc,"WTA","2026-10-21T00:00:00Z","u","a"*64),[])

if __name__=="__main__":unittest.main()
