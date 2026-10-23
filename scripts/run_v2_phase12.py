"""Phase 1/2 read-only snapshot enrichment with independent ESPN history.

Only provider-scoped athlete IDs are joined. The historical fetches do not
supply actual completion timestamps, rest or court-minute estimates.
"""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from v2_phase12_pipeline import (utc,scoped_fixture_identity,tournament_location,
                                  collect_completed,partial_observed_workload)

def report(snapshot,*,as_of,completed=None,feed_health=None):
    now=utc(as_of)
    completed=completed or []
    feed_health=feed_health or {"requested_sources":0,"successful_sources":0,
                               "failed_sources":0,"feeds":[]}
    items=[];counts={"fixture_count":0,"provider_ids_verified":0,
        "source_scoped_espn":0,"source_scoped_tenniscom":0,
        "tournament_city_known":0,"exact_court_coordinates":0,
        "workload_player_sides_with_observed_14d_matches":0,
        "workload_player_sides_not_observed":0,
        "observed_completed_matches":len(completed),
        "exact_match_duration_records":0,"exact_finish_time_records":0}
    for m in snapshot.get("matches",[]):
        try:
            if utc(m["starts_at"])<=now:continue
            identity=scoped_fixture_identity(m)
            location=tournament_location(m)
            historical=partial_observed_workload(m,identity,completed,as_of=now.isoformat())
        except (KeyError,ValueError,TypeError):
            continue
        counts["fixture_count"]+=1
        if identity["status"]=="source_verified":
            counts["provider_ids_verified"]+=1
            counts["source_scoped_"+identity["provider"]]+=1
        counts["tournament_city_known"]+=location["status"]=="tournament_city_only"
        if historical.get("players"):
            for row in historical["players"].values():
                counts["workload_player_sides_with_observed_14d_matches"]+=(row.get("completed_starts_14d") or 0)>0
                counts["workload_player_sides_not_observed"]+=row["status"]=="no_matching_completed_records"
        items.append({"match_id":m["source_match_id"],"tournament_key":m.get("tournament_key"),
                      "identity":identity,"location":location,"observed_workload":historical})
    return {"schema":"experimental-v2-phase12-0.1",
            "research_only":True,"published_probabilities_modified":False,
            "point_in_time_observed_at":now.isoformat(),
            "feature_precision":"SOURCE_IDS_AND_MATCH_STARTS_ONLY",
            "counts":counts,"feed_health":feed_health,"matches":items,
            "unavailable_without_independent_sources":{
                "exact_court_coordinates":"Court GPS/venue-specific location not present in currently trusted fixture feed",
                "exact_finish_times":"Scheduled start and first observed final do not equal actual finish",
                "match_durations":"No verified duration field parsed from current ESPN feed",
                "travel":"Requires verified previous and destination stadium coordinates",
                "comprehensive_match_history":"Only confirmed completed records from successfully fetched ESPN day feeds"},
            "win_probability_adjustment":None}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--enable-history-fetch",action="store_true",help="Read recent ESPN finished-match feeds")
    ap.add_argument("--history-days",type=int,default=14)
    ap.add_argument("--output",default="work/v2-phase12-evidence.json")
    args=ap.parse_args()
    snapshot=json.loads(Path(args.snapshot).read_text())
    observed=datetime.now(timezone.utc)
    if args.enable_history_fetch:
        completed,health=collect_completed(now=observed,days=args.history_days)
    else:
        completed=[];health={"requested_sources":0,"successful_sources":0,
                             "failed_sources":0,"feeds":[],"status":"FETCH_NOT_ENABLED"}
    data=report(snapshot,as_of=observed.isoformat(),completed=completed,feed_health=health)
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print(json.dumps({"status":"PHASE12_RESEARCH_ONLY",
                      "counts":data["counts"],
                      "sources":{"success":health["successful_sources"],
                                 "failure":health["failed_sources"]},
                      "production_predictions_modified":False}))
if __name__=="__main__":main()
