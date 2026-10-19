import base64
import hashlib
import json
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from seven_day_tennis_audit import build,verified_results
from tennis_result_sources import diagnose_exclusions

NOW=datetime(2026,10,19,18,tzinfo=timezone.utc)
def forecast(fid="f",tour="ATP"):
    return {"fixture_id":fid,"tour":tour,"name_a":"One","name_b":"Two",
        "starts_at":"2026-10-19T12:00:00Z","issued_at":"2026-10-19T10:00:00Z",
        "results":{k:{"status":"ok","p_a":p} for k,p in
                   (("champion",0.7),("challenger",0.6),("experimental",0.8))}}
def outcome(fid="f",winner="a"):
    return {"fixture_id":fid,"tour":"ATP","name_a":"One","name_b":"Two",
        "winner":winner,"result_type":"completed",
        "completed_at":"2026-10-19T15:00:00Z",
        "recorded_at":"2026-10-19T15:00:00Z",
        "observations":[{"provider":p,"event_id":i,"winner":winner,
                         "result_type":"completed","name_a":"One","name_b":"Two",
                         "observed_at":"2026-10-19T15:00:00Z",
                         "url":u,"source_sha256":sha*64}
                         for p,i,u,sha in (
                             ("espn","11","https://site.api.espn.com/score","a"),
                             ("tenniscom","sr:sport_event:12","https://www.tennis.com/score","b"))]}
def receipt(outcomes):
    return {"schema_version":1,"settlements":outcomes,"exclusions":{}}

class Fake:
    def __init__(self,raw,branch_missing=False,corrupt=False):
        self.raw=raw;self.branch_missing=branch_missing;self.corrupt=corrupt
        self.digest=hashlib.sha256(raw).hexdigest()
        self.path="evidence/results/2026/10/19/123/"+self.digest+".json"
    def api(self,method,route):
        if "/git/trees/" in route:
            if self.branch_missing and "tennis-evidence" in route:return {"truncated":False,"tree":[]}
            return {"truncated":False,"tree":[{"path":self.path,"type":"blob"}]}
        if "/contents/" in route:
            return {"encoding":"base64","content":base64.b64encode(b"corrupt" if self.corrupt else self.raw).decode()}
        raise ValueError(route)

class SevenDayAuditTests(unittest.TestCase):
    def test_deduplicates_result_receipts_and_preserves_champion(self):
        d=build([forecast()], [receipt([outcome()]),receipt([outcome()])],NOW)
        self.assertEqual(d["verified_settlements"],1)
        self.assertEqual(d["paired"]["paired_by_tour"]["ATP"]["paired_fixtures"],1)
        self.assertEqual(d["model_decisions"]["champion"]["correct"],1)
        self.assertFalse(d["promotion_authorized"])
        self.assertTrue(d["champion_frozen"])
        self.assertIsNone(d["model_decisions"]["champion"]["market_upsets_correct"])
    def test_conflicting_result_is_quarantined(self):
        d=build([forecast()], [receipt([outcome(winner="a")]),receipt([outcome(winner="b")])],NOW)
        self.assertEqual(d["verified_settlements"],0)
        self.assertEqual(d["result_conflicts_quarantined"],1)
        self.assertEqual(d["exclusion_reasons"]["CONFLICTING_ARCHIVED_RESULTS"],1)
    def test_missing_result_is_pending_not_loss(self):
        d=build([forecast()],[],NOW)
        self.assertEqual(d["unresolved"],1)
        self.assertIsNone(d["model_decisions"]["champion"]["accuracy"])
    def test_does_not_count_same_fixture_twice(self):
        d=build([forecast(),forecast()], [receipt([outcome()])],NOW)
        self.assertEqual(d["forecast_fixtures"],1)
    def test_rejects_unverified_source_claim(self):
        o=outcome()
        o["observations"][1]["source_sha256"]="fake"
        d=build([forecast()],[receipt([o])],NOW)
        self.assertEqual(d["verified_settlements"],0)
    def test_sha_verified_receipt(self):
        raw=json.dumps(receipt([outcome()])).encode()
        r=verified_results(Fake(raw),NOW)
        self.assertEqual(r["files_verified"],1)
        self.assertEqual(r["source"],"sha_verified_union")
    def test_corrupt_both_branches_fails_closed(self):
        raw=json.dumps(receipt([outcome()])).encode()
        with self.assertRaisesRegex(RuntimeError,"UNVERIFIABLE_RESULT_RECEIPT"):
            verified_results(Fake(raw,corrupt=True),NOW)
    def test_exclusion_diagnosis_identifies_missing_tenniscom(self):
        f={**forecast(),"source_match_id":"11"}
        obs={"provider":"espn","tour":"ATP","event_id":"11","name_a":"One","name_b":"Two",
             "scheduled_at":"2026-10-19T12:00:00Z"}
        d=diagnose_exclusions([f],[obs],{"f":"SOURCE_MISSING_OR_AMBIGUOUS"},
           [{"provider":"espn","status":"ok"},{"provider":"tenniscom","status":"ok"}])
        self.assertEqual(d["f"]["diagnosis"],"MISSING_ONE_INDEPENDENT_PROVIDER")
if __name__=="__main__":unittest.main()
