"""Strict reconciliation of immutable forecasts and independent outcome evidence.

Refuses mismatched players, retired/walkover matches, and unverified sources.
This module neither fetches results nor fabricates settlement.
"""
import json
from prospective_grade import evaluate, timestamp

def reconcile(forecasts, outcomes):
    by_fixture={}
    for o in outcomes:
        fid=o["fixture_id"]
        if fid in by_fixture:raise ValueError("DUPLICATE_SETTLEMENT")
        by_fixture[fid]=o
    matched=[];settled=[];errors={}
    seen=set()
    for f in forecasts:
        fid=f["fixture_id"]
        if fid in seen:
            errors[fid]="DUPLICATE_FORECAST"
            continue
        seen.add(fid)
        o=by_fixture.get(fid)
        if not o:
            errors[fid]="NO_VERIFIED_SETTLEMENT";continue
        if o.get("source_count",0)<2 or not o.get("source_agreement",False):
            errors[fid]="INDEPENDENT_CONFIRMATION_REQUIRED";continue
        if (f["tour"],f["name_a"],f["name_b"]) != (o.get("tour"),o.get("name_a"),o.get("name_b")):
            errors[fid]="PLAYER_ORIENTATION_MISMATCH";continue
        if o.get("result_type")!="completed":
            errors[fid]="NONSTANDARD_RESULT";continue
        if o.get("winner") not in ("a","b"):
            errors[fid]="WINNER_UNVERIFIED";continue
        if timestamp(f["issued_at"]) >= timestamp(f["starts_at"]):
            errors[fid]="FORECAST_AFTER_START";continue
        if timestamp(o["completed_at"])<timestamp(f["starts_at"]):
            errors[fid]="IMPOSSIBLE_COMPLETION";continue
        if timestamp(o["recorded_at"])<timestamp(o["completed_at"]):
            errors[fid]="PREMATURE_SETTLEMENT";continue
        matched.append(f)
        settled.append({k:o[k] for k in ("fixture_id","tour","winner","completed_at","recorded_at")})
    return matched,settled,errors

def grade(forecasts,outcomes):
    matched,settled,errors=reconcile(forecasts,outcomes)
    report=evaluate(matched,settled)
    report["reconciliation"]={"verified_fixtures":len(matched),"rejected":errors}
    report["promotion_authorized"]=False
    return report
