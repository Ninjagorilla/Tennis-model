import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from settlement_health import assess

F=[{"fixture_id":"a"}]
OBS=[{"provider":"espn","event_id":"7","source_sha256":"a"*64,"url":"https://site.api.espn.com/match","winner":"a"},
     {"provider":"tenniscom","event_id":"sr:sport_event:8","source_sha256":"b"*64,"url":"https://www.tennis.com/match","winner":"a"}]
def report(settled=True,providers=True):
    return {"health":[{"provider":"espn","status":"ok"},
                      {"provider":"tenniscom","status":"ok" if providers else "unavailable"}],
            "settlements":[{"fixture_id":"a","winner":"a","observations":OBS}] if settled else [],
            "exclusions":{},
            "graded_research":{"reconciliation":{"verified_fixtures":1 if settled else 0},
                               "metrics_by_tour":{"ATP":{"champion":{"n":1,"brier":0.1}}}}}
class SettlementAcceptanceTests(unittest.TestCase):
    def test_verified_result_requires_two_feeds_and_archived_receipt(self):
        d=assess(F,report(),{"remote_verified":True})
        self.assertEqual(d["status"],"verified_results")
        self.assertFalse(d["alert"])
        self.assertEqual(d["settled_count"],1)
        self.assertFalse(d["promotion_authorized"])
    def test_no_verified_result_is_pending_not_loss(self):
        d=assess(F,report(settled=False),{"remote_verified":True})
        self.assertEqual(d["status"],"awaiting_verified_results")
        self.assertEqual(d["settled_count"],0)
        self.assertFalse(d["alert"])
    def test_one_provider_outage_alerts(self):
        d=assess(F,report(providers=False),{"remote_verified":True})
        self.assertEqual(d["status"],"degraded")
        self.assertTrue(d["alert"])
    def test_missing_result_archive_alerts(self):
        self.assertTrue(assess(F,report(),None)["alert"])
    def test_report_missing_fails_closed(self):
        self.assertEqual(assess(F,None,None)["status"],"blocked")
    def test_unauthenticated_claim_of_two_sources_fails_closed(self):
        r=report()
        r["settlements"][0]["observations"]=[{"provider":"espn"},{"provider":"espn"}]
        self.assertEqual(assess(F,r,{"remote_verified":True})["status"],"blocked")
    def test_invalid_provider_hash_is_not_accepted(self):
        r=report()
        r["settlements"][0]["observations"]=[dict(OBS[0]),dict(OBS[1],source_sha256="fake")]
        self.assertEqual(assess(F,r,{"remote_verified":True})["status"],"blocked")
    def test_grade_count_mismatch_fails_closed(self):
        r=report()
        r["graded_research"]["reconciliation"]["verified_fixtures"]=0
        self.assertEqual(assess(F,r,{"remote_verified":True})["reason"],"GRADE_COUNT_DISAGREEMENT")
if __name__=="__main__":unittest.main()
