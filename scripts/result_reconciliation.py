"""Strict reconciliation of immutable forecasts and independent outcome evidence.

Refuses mismatched players, retired/walkover matches, and unverified sources.
This module neither fetches results nor fabricates settlement.
"""
import json
import hashlib
from prospective_grade import evaluate, timestamp

def independently_verified(outcome):
    """Require two distinct source observations agreeing on the same result.

    A count/boolean supplied by a caller cannot establish source independence.
    """
    evidence=outcome.get("observations")
    if not isinstance(evidence,list) or len(evidence)<2:
        return False
    providers=set()
    for e in evidence:
        if not isinstance(e,dict):
            return False
        provider=e.get("provider")
        source_id=e.get("event_id")
        if not isinstance(provider,str) or not provider.strip() or not isinstance(source_id,str) or not source_id.strip():
            return False
        if provider in providers:
            continue
        if e.get("winner")!=outcome.get("winner") or e.get("result_type")!=outcome.get("result_type"):
            return False
        if e.get("name_a")!=outcome.get("name_a") or e.get("name_b")!=outcome.get("name_b"):
            return False
        if not isinstance(e.get("observed_at"),str):
            return False
        try:
            if timestamp(e["observed_at"])<timestamp(outcome["completed_at"]):
                return False
        except (KeyError,ValueError,TypeError):
            return False
        providers.add(provider)
    return len(providers)>=2

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
        if not independently_verified(o):
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
