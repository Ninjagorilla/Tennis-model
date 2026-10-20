import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from v2_missing_feed_adapters import (weather_forecast,exact_workload,official_availability)
from run_v2_missing_feeds import make_report

MATCH={"source_match_id":"fixture-4","starts_at":"2026-10-20T05:30:00+00:00",
       "surface":"Hard","tour":"WTA","name_a":"A","name_b":"B"}
NOW="2026-10-19T20:00:00+00:00"
VENUE={"verification":"source_checked","lat":34.7,"lon":135.5,
       "source_url":"https://www.wtatennis.com/tournaments/example",
       "source_sha256":"a"*64,"verified_at":"2026-10-19T19:00:00+00:00",
       "court_enclosure":"Outdoor"}
def weather_payload():
    return json.dumps({"latitude":34.69,"longitude":135.51,"hourly":{
        "time":["2026-10-20T04:00","2026-10-20T05:00","2026-10-20T06:00"],
        "temperature_2m":[17,19,20],"relative_humidity_2m":[60,65,70],
        "precipitation_probability":[10,20,35],"wind_speed_10m":[5,11,13]}}).encode()
def receipt(pid,mid,finished,minutes=70,published=None):
    return {"player_id":pid,"source_match_id":mid,"status":"completed",
            "source_url":"https://www.wtatennis.com/matches/example",
            "finished_at":finished,"published_at":published or finished,
            "duration_minutes":minutes}

class MissingFeedTests(unittest.TestCase):
 def test_weather_missing_venue_fails_closed(self):
    r=weather_forecast(MATCH,None,now=NOW)
    self.assertEqual(r["reason"],"VENUE_COORDINATES_UNVERIFIED")
 def test_indoor_never_fetches_weather(self):
    v={**VENUE,"court_enclosure":"Indoor"}
    r=weather_forecast(MATCH,v,now=NOW,fetcher=lambda _:self.fail("called weather API"))
    self.assertEqual(r["status"],"not_applicable")
 def test_verified_outdoor_forecast_is_only_observation(self):
    r=weather_forecast(MATCH,VENUE,now=NOW,fetcher=lambda url:weather_payload())
    self.assertEqual(r["status"],"observed")
    self.assertEqual(r["values"]["wind_speed_10m"],11)
    self.assertEqual(r["forecast_hour_utc"],"2026-10-20T05:00:00+00:00")
    self.assertEqual(len(r["source_sha256"]),64)
    self.assertIsNone(r["win_probability_adjustment"])
 def test_weather_rejects_mismatched_grid_and_missing_hour(self):
    wrong=json.loads(weather_payload())
    wrong["latitude"]=35.9
    r=weather_forecast(MATCH,VENUE,now=NOW,fetcher=lambda _:json.dumps(wrong).encode())
    self.assertEqual(r["status"],"unavailable")
    wrong=json.loads(weather_payload());wrong["hourly"]["time"][1]="2026-10-20T07:00"
    r=weather_forecast(MATCH,VENUE,now=NOW,fetcher=lambda _:json.dumps(wrong).encode())
    self.assertEqual(r["status"],"unavailable")
 def test_weather_rejects_late_or_unverified_geo(self):
    self.assertEqual(weather_forecast(MATCH,VENUE,now=MATCH["starts_at"])["reason"],"NO_PREMATCH_FORECAST")
    self.assertEqual(weather_forecast(MATCH,{**VENUE,"verification":"unknown"},now=NOW)["reason"],"VENUE_COORDINATES_UNVERIFIED")
    self.assertEqual(weather_forecast(MATCH,{**VENUE,"verified_at":MATCH["starts_at"]},now=NOW)["reason"],"VENUE_VERIFIED_TOO_LATE")
 def test_weather_never_uses_arbitrary_url_or_mismatched_array(self):
    self.assertEqual(weather_forecast(MATCH,{**VENUE,"source_url":"https://untrusted.example.com"},now=NOW)["reason"],"VENUE_SOURCE_UNAPPROVED")
    raw=json.loads(weather_payload());raw["hourly"]["wind_speed_10m"]=[]
    self.assertEqual(weather_forecast(MATCH,VENUE,now=NOW,fetcher=lambda _:json.dumps(raw).encode())["status"],"unavailable")
 def test_workload_observed_count_only_not_complete_coverage(self):
    records=[
        receipt("A","a1","2026-10-17T18:00:00+00:00",100),
        receipt("A","a2","2026-10-18T18:00:00+00:00",90),
        receipt("B","b1","2026-10-18T17:00:00+00:00",120)]
    r=exact_workload(MATCH,records,{"a":"A","b":"B"},as_of=NOW)
    self.assertEqual(r["status"],"observed_partial_coverage")
    self.assertEqual(r["players"]["a"]["observed_court_minutes_7d"],190)
    self.assertEqual(r["players"]["b"]["observed_matches_14d"],1)
    self.assertIsNone(r["win_probability_adjustment"])
 def test_no_exact_finished_data_does_not_invent_rest(self):
    r=exact_workload(MATCH,[],{"a":"A","b":"B"},as_of=NOW)
    self.assertEqual(r["reason"],"NO_EXACT_COMPLETION_FEED")
    r=exact_workload(MATCH,[receipt("A","a1","2026-10-18T18:00:00+00:00")],{"a":"A","b":"B"},as_of=NOW)
    self.assertEqual(r["reason"],"INCOMPLETE_WORKLOAD_COVERAGE")
 def test_invalid_duplicated_or_poststart_record_is_rejected(self):
    dup=receipt("A","dup","2026-10-18T18:00:00+00:00")
    b=receipt("B","b1","2026-10-18T18:00:00+00:00")
    self.assertEqual(exact_workload(MATCH,[dup,dup,b],{"a":"A","b":"B"},as_of=NOW)["reason"],"INVALID_EXACT_MATCH_RECEIPT")
 def test_official_availability_unknown_is_not_healthy(self):
    r=official_availability(MATCH,[],{"a":"A","b":"B"},as_of=NOW)
    self.assertEqual(r["players"]["a"]["status"],"unknown")
    self.assertEqual(r["players"]["b"]["status"],"unknown")
    self.assertIsNone(r["win_probability_adjustment"])
 def test_official_notice_is_reported_not_used_in_probability(self):
    r=official_availability(MATCH,[
        {"player_id":"A","fixture_id":"fixture-4","status":"withdrawn",
         "source_url":"https://www.wtatennis.com/news/example",
         "published_at":"2026-10-19T18:00:00+00:00"}],
        {"a":"A","b":"B"},as_of=NOW)
    self.assertEqual(r["players"]["a"]["reported_availability"],"withdrawn")
    self.assertEqual(r["players"]["b"]["status"],"unknown")
 def test_report_is_safe_with_zero_inputs(self):
    snap={"matches":[MATCH],"generated_at":NOW}
    r=make_report(snap,as_of=NOW)
    self.assertEqual(r["counts"]["missing_venue"],1)
    self.assertEqual(r["counts"]["missing_player_identity"],1)
    self.assertFalse(r["prediction_probabilities_modified"])
    self.assertEqual(r["observations"][0]["exact_workload"]["status"],"unavailable")
if __name__=="__main__":unittest.main()
