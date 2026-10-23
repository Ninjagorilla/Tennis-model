import json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from v2_phase12_pipeline import (scoped_fixture_identity,tournament_location,
    parse_espn_completed,collect_completed,partial_observed_workload)

NOW="2026-10-19T20:00:00+00:00"
FUTURE="2026-10-20T05:30:00+00:00"
def fixture(**kwargs):
    return {"source_match_id":"12345","source_event_id":"event-22","tour":"WTA",
            "tournament_key":"osaka","tournament":"Japan Open",
            "name_a":"Kimberly Birrell","name_b":"Kayla Day",
            "source_player_ids":["72","99"],"starts_at":FUTURE,
            "surface":"Hard","court_enclosure":"Outdoor",
            "surface_source":"https://www.tennis.com/tournaments/osaka",**kwargs}
def result(mid="543",a="72",b="99",start="2026-10-17T16:00:00Z",state="STATUS_FINAL",complete=True):
    return {"id":mid,"startDate":start,
            "status":{"type":{"name":state,"state":"post","completed":complete}},
            "competitors":[{"id":a,"athlete":{"displayName":"Kimberly Birrell"},"winner":True},
                           {"id":b,"athlete":{"displayName":"Kayla Day"},"winner":False}]}
def feed(*items):
    return {"events":[{"name":"Osaka",
                        "groupings":[{"grouping":{"slug":"womens-singles"},
                                      "competitions":list(items)}]}]}
class IdentityLocationAndWorkloadTests(unittest.TestCase):
 def test_espn_fixture_ids_remain_source_scoped_and_oriented(self):
    r=scoped_fixture_identity(fixture())
    self.assertEqual(r["status"],"source_verified")
    self.assertEqual(r["players"]["a"],"WTA:espn:72")
    self.assertEqual(r["players"]["b"],"WTA:espn:99")
    self.assertEqual(r["name_labels"]["b"],"Kayla Day")
 def test_tenniscom_provider_uses_own_namespace(self):
    f=fixture();f["source_match_id"]="tc:sr:sport_event:9944"
    f["source_player_ids"]=["id-one","id-two"]
    r=scoped_fixture_identity(f)
    self.assertEqual(r["players"]["a"],"WTA:tenniscom:id-one")
    self.assertNotEqual(r["players"]["a"],"WTA:espn:id-one")
 def test_missing_duplicate_or_wrong_provider_ids_refused(self):
    f=fixture();f["source_player_ids"]=["72","72"]
    self.assertEqual(scoped_fixture_identity(f)["reason"],"DUPLICATE_ATHLETE_SOURCE_ID")
    f["source_player_ids"]=["abc","def"]
    self.assertEqual(scoped_fixture_identity(f)["reason"],"ESPN_ID_FORMAT_MISMATCH")
    f["source_player_ids"]=[]
    self.assertEqual(scoped_fixture_identity(f)["reason"],"ATHLETE_SOURCE_IDS_MISSING")
    f["source_player_ids"]=["72","99"];f["source_match_id"]="made_up"
    self.assertEqual(scoped_fixture_identity(f)["reason"],"PROVIDER_IDENTITY_UNKNOWN")
 def test_tournament_source_proves_city_context_not_coords(self):
    venue=tournament_location(fixture())
    self.assertEqual(venue["status"],"tournament_city_only")
    self.assertIsNone(venue["exact_court_coordinates"])
    self.assertFalse(venue["weather_eligible"])
    bad=fixture();bad["surface_source"]="https://random.example.com"
    self.assertEqual(tournament_location(bad)["status"],"unavailable")
 def test_completed_matches_have_source_id_not_fake_duration(self):
    readings=parse_espn_completed(feed(result()),"WTA",observed_at=NOW,
                                 source_url="https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard?dates=20261017",
                                 source_sha256="a"*64)
    self.assertEqual(len(readings),1)
    self.assertEqual(readings[0]["player_ids"],["72","99"])
    self.assertIsNone(readings[0]["actual_finished_at"])
    self.assertIsNone(readings[0]["duration_minutes"])
    self.assertEqual(readings[0]["first_observed_final_at"],NOW)
 def test_started_but_not_finished_and_retired_not_counted(self):
    c=result(state="STATUS_IN_PROGRESS",complete=False)
    retired=result(mid="66");retired["score"]="6-4 1-2 RET"
    readings=parse_espn_completed(feed(c,retired),"WTA",observed_at=NOW,
                                 source_url="https://site.api.espn.com/",
                                 source_sha256="a"*64)
    self.assertEqual(readings,[])
 def test_conflicting_same_feed_final_is_withheld(self):
    a=result(mid="811")
    b=result(mid="811")
    b["competitors"][0]["winner"]=False
    b["competitors"][1]["winner"]=True
    out=parse_espn_completed(feed(a,b),"WTA",observed_at=NOW,
          source_url="https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard?dates=20261017",
          source_sha256="c"*64)
    self.assertEqual(out,[])
 def test_no_future_record_or_mixed_tour_data(self):
    readings=parse_espn_completed(feed(result(start="2026-10-20T12:00:00Z")),"WTA",
                                observed_at=NOW,source_url="https://site.api.espn.com/",
                                source_sha256="b"*64)
    self.assertEqual(readings,[])
    m=feed(result());m["events"][0]["groupings"][0]["grouping"]["slug"]="mens-singles"
    self.assertEqual(parse_espn_completed(m,"WTA",observed_at=NOW,source_url="https://site.api.espn.com/",source_sha256="b"*64),[])
 def test_espn_historical_collector_deduplicates_days_and_fails_closed(self):
    raw=json.dumps(feed(result())).encode()
    def reader(url):
        if "atp/" in url:raise OSError("unavailable")
        return raw
    rows,coverage=collect_completed(now=NOW,days=2,reader=reader)
    self.assertEqual(len(rows),1)
    self.assertGreater(coverage["failed_sources"],0)
    self.assertGreater(coverage["successful_sources"],0)
    self.assertEqual(rows[0]["match_id"],"543")
 def test_partial_load_calculates_counts_not_rest_minutes(self):
    f=fixture()
    i=scoped_fixture_identity(f)
    a={"tour":"WTA","match_id":"m1","player_ids":["72","999"],
       "scheduled_start_at":"2026-10-18T12:00:00+00:00","first_observed_final_at":NOW,
       "source_url":"https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard?dates=20261018",
       "source_sha256":"a"*64}
    b={"tour":"WTA","match_id":"m2","player_ids":["99","777"],
       "scheduled_start_at":"2026-10-12T12:00:00+00:00","first_observed_final_at":NOW,
       "source_url":"https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard?dates=20261018",
       "source_sha256":"a"*64}
    out=partial_observed_workload(f,i,[a,b],as_of=NOW)
    self.assertEqual(out["status"],"partial_observed_history")
    self.assertEqual(out["players"]["a"]["completed_starts_7d"],1)
    self.assertEqual(out["players"]["b"]["completed_starts_14d"],1)
    self.assertEqual(out["players"]["b"]["completed_starts_7d"],0)
    self.assertIsNone(out["players"]["a"]["rest_hours"])
    self.assertIsNone(out["players"]["b"]["court_minutes"])
    self.assertIsNone(out["win_probability_adjustment"])
 def test_do_not_conflate_same_name_with_other_athlete_id(self):
    f=fixture()
    i=scoped_fixture_identity(f)
    completed=[{"tour":"WTA","match_id":"m5","player_ids":["72","333"],
        "scheduled_start_at":"2026-10-18T12:00:00+00:00","first_observed_final_at":NOW,
       "source_url":"https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard?dates=20261018",
       "source_sha256":"a"*64}]
    out=partial_observed_workload(f,i,completed,as_of=NOW)
    self.assertEqual(out["players"]["b"]["status"],"no_matching_completed_records")
    self.assertIsNone(out["players"]["b"]["completed_starts_14d"])
 def test_after_start_and_empty_feed_never_look_like_rest(self):
    f=fixture()
    i=scoped_fixture_identity(f)
    self.assertEqual(partial_observed_workload(f,i,[],as_of=NOW)["status"],"unavailable")
    self.assertEqual(partial_observed_workload(f,i,[],as_of=FUTURE)["reason"],"FUTURE_MATCH_ALREADY_STARTED")
if __name__=="__main__":unittest.main()
