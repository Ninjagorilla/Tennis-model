from v2_phase12_pipeline import scoped_fixture_identity
"""Aggregate Experimental V2 gap observations; never affect models or published odds.

By default this requires no network access and truthfully reports unavailable
feeds. A reviewed court catalog can opt in to free Open-Meteo point forecasts.
"""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from v2_missing_feed_adapters import (weather_forecast,exact_workload,
                                      official_availability,moment)

def make_report(snapshot,*,venues=None,player_ids=None,match_records=None,
                notices=None,weather_fetch=False,as_of=None,weather_fetcher=None):
    venues=venues or {};player_ids=player_ids or {}
    match_records=match_records or [];notices=notices or []
    current=moment(as_of) if as_of is not None else datetime.now(timezone.utc)
    observations=[]
    counts={"weather_observed":0,"workload_partial":0,"official_notices":0,
            "missing_venue":0,"missing_player_identity":0,"not_yet_started":0}
    for m in snapshot.get("matches",[]):
        if moment(m["starts_at"])<=current:
            counts["not_yet_started"]+=0
            continue
        fid=m["source_match_id"]
        venue=venues.get(fid)
        if weather_fetch and venue is not None:
            weather=weather_forecast(m,venue,fetcher=weather_fetcher,now=current)
        else:
            weather={"status":"unavailable",
                     "reason":"VENUE_COORDINATES_UNVERIFIED" if venue is None else "WEATHER_FETCH_NOT_ENABLED"}
        ids=player_ids.get(fid)
        if ids is None:
            verified=scoped_fixture_identity(m)
            if verified.get("status")=="source_verified":
                ids=verified["players"]
        if not isinstance(ids,dict) or set(ids)!={"a","b"}:
            workload={"status":"unavailable","reason":"UNVERIFIED_PLAYER_IDENTITIES"}
            availability={"status":"unavailable","reason":"UNVERIFIED_PLAYER_IDENTITIES"}
            counts["missing_player_identity"]+=1
        else:
            workload=exact_workload(m,match_records,ids,as_of=current.isoformat())
            availability=official_availability(m,notices,ids,as_of=current.isoformat())
        counts["weather_observed"]+=weather["status"]=="observed"
        counts["workload_partial"]+=workload["status"]=="observed_partial_coverage"
        counts["official_notices"]+=any(v.get("status")=="publicly_reported" for v in availability.get("players",{}).values())
        counts["missing_venue"]+=weather.get("reason")=="VENUE_COORDINATES_UNVERIFIED"
        observations.append({"match_id":fid,"starts_at":m["starts_at"],
                             "weather":weather,"exact_workload":workload,
                             "official_availability":availability})
    return {"schema":"experimental-v2-missing-feeds-0.1","research_only":True,
            "prediction_probabilities_modified":False,
            "as_of":current.isoformat(),"scanned_future_matches":len(observations),
            "counts":counts,"observations":observations,
            "caveats":["A missing injury notice is NOT evidence that a player is healthy.",
                       "A city name is NOT verified stadium coordinates.",
                       "Historical actual weather is NOT a pre-match forecast.",
                       "Workload coverage is partial unless independently reconciled."]}

def read_optional(path):
    return json.loads(Path(path).read_text()) if path else None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("snapshot",help="Current pre-match tennis snapshot JSON")
    p.add_argument("--venues",help="Reviewed per-match exact court catalog JSON")
    p.add_argument("--player-ids",help="Verified internal identities by match ID JSON")
    p.add_argument("--completed-matches",help="Timestamped and attributed finished match receipts JSON")
    p.add_argument("--availability",help="Official published participation notices JSON")
    p.add_argument("--enable-weather-fetch",action="store_true",
                   help="Opt-in only. Calls Open-Meteo when venue catalog is verified")
    p.add_argument("--output",default="work/v2-missing-feeds.json")
    a=p.parse_args()
    if a.enable_weather_fetch and not a.venues:p.error("--enable-weather-fetch requires --venues")
    doc=make_report(json.loads(Path(a.snapshot).read_text()),
                    venues=read_optional(a.venues),
                    player_ids=read_optional(a.player_ids),
                    match_records=read_optional(a.completed_matches),
                    notices=read_optional(a.availability),
                    weather_fetch=a.enable_weather_fetch)
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(doc,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":"RESEARCH_GAP_REPORT","matches":doc["scanned_future_matches"],
                      "counts":doc["counts"],"published_probabilities_changed":False}))
if __name__=="__main__":main()
