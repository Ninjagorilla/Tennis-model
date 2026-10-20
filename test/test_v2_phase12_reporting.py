import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from run_v2_phase12 import report
from run_v2_missing_feeds import make_report
from test_v2_phase12_pipeline import fixture,NOW

class Phase12ReportTests(unittest.TestCase):
 def test_real_fixture_ids_enter_research_report(self):
    m=fixture()
    completed=[{"tour":"WTA","match_id":"recent-1","player_ids":["72","801"],
        "scheduled_start_at":"2026-10-18T11:00:00+00:00",
        "first_observed_final_at":NOW}]
    health={"requested_sources":30,"successful_sources":28,"failed_sources":2,"feeds":[]}
    data=report({"matches":[m]},as_of=NOW,completed=completed,feed_health=health)
    counts=data["counts"]
    self.assertEqual(counts["fixture_count"],1)
    self.assertEqual(counts["provider_ids_verified"],1)
    self.assertEqual(counts["source_scoped_espn"],1)
    self.assertEqual(counts["tournament_city_known"],1)
    self.assertEqual(counts["exact_court_coordinates"],0)
    self.assertEqual(counts["workload_player_sides_with_observed_14d_matches"],1)
    self.assertFalse(data["published_probabilities_modified"])
    self.assertIsNone(data["matches"][0]["observed_workload"]["players"]["b"]["court_minutes"] if "court_minutes" in data["matches"][0]["observed_workload"]["players"]["b"] else None)
    self.assertEqual(data["feed_health"]["failed_sources"],2)
 def test_missing_feeds_reuses_source_ids_without_hallucinations(self):
    r=make_report({"matches":[fixture()]},as_of=NOW)
    self.assertEqual(r["counts"]["missing_player_identity"],0)
    self.assertEqual(r["counts"]["missing_venue"],1)
    self.assertEqual(r["counts"]["weather_observed"],0)
    self.assertEqual(r["counts"]["workload_partial"],0)
    self.assertEqual(r["observations"][0]["exact_workload"]["reason"],"NO_EXACT_COMPLETION_FEED")
 def test_unproven_ids_remain_missing(self):
    missing=fixture();missing.pop("source_player_ids")
    r=make_report({"matches":[missing]},as_of=NOW)
    self.assertEqual(r["counts"]["missing_player_identity"],1)
    self.assertEqual(r["observations"][0]["official_availability"]["reason"],"UNVERIFIED_PLAYER_IDENTITIES")
if __name__=="__main__":unittest.main()
