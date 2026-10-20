"""Experimental-only matchup intelligence V2: reproducible, missing-aware features.

Never interprets absent medical/weather/style data as healthy, calm or neutral.
Research adjustments are opt-in and must not replace the registered v3.4-A score.
Every fact needs an observed time strictly before the scheduled match start.
"""
import hashlib,json,math
from datetime import datetime,timezone

FEATURES=("surface","indoor","style","h2h","fatigue","injury","weather","physical")
LIMITS={"surface":0.045,"indoor":0.015,"style":0.035,"h2h":0.025,
        "fatigue":0.030,"injury":0.035,"weather":0.015,"physical":0.015}

def timestamp(value):
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None:raise ValueError("TIMEZONE_MISSING")
    return dt.astimezone(timezone.utc)

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def checked_feature(name,entry,match_start):
    """Scores must be derived by a verifiable adapter, not user-supplied opinions."""
    if not isinstance(entry,dict) or entry.get("status")!="verified":return None,"MISSING_OR_UNVERIFIED"
    if name not in FEATURES:return None,"UNSUPPORTED_FEATURE"
    allowed={"source_url","source_sha256","observed_at","match_id","raw","evidence_type","status"}
    if set(entry)-allowed:return None,"UNRECOGNIZED_FIELDS"
    try:
        observed=timestamp(entry["observed_at"])
        if observed>=match_start:return None,"POST_START_EVIDENCE"
        if not str(entry["source_url"]).startswith(("https://www.atptour.com/","https://www.wtatennis.com/","https://www.tennis.com/","https://site.api.espn.com/","https://api.open-meteo.com/","https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/",
    "https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/83733587353df8a41f2fd4f516147d5aa83f5a8d/","https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/","https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/")):
            return None,"SOURCE_NOT_ALLOWLISTED"
        if len(str(entry["source_sha256"]))!=64 or any(c not in "0123456789abcdef" for c in entry["source_sha256"].lower()):
            return None,"BAD_PROVENANCE"
        raw=entry["raw"]
        if not isinstance(raw,dict) or set(raw)!={"a","b","effective_n"}:
            return None,"INVALID_RAW"
        a,b,n=(raw[k] for k in ("a","b","effective_n"))
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (a,b,n)):
            return None,"NONFINITE"
        if not -1<=a<=1 or not -1<=b<=1 or n<(3 if name=="h2h" else 20):
            return None,"UNSUPPORTED_RANGE_OR_SAMPLE"
        if not isinstance(entry.get("match_id"),str) or not entry["match_id"]:
            return None,"MISSING_FIXTURE_ID"
        # The scorer is intentionally a conservative candidate feature; its
        # interpretation is documented and measured in shadow only.
        shrink=n/(n+200)
        return max(-LIMITS[name],min(LIMITS[name],(a-b)*LIMITS[name]*shrink)),None
    except (KeyError,ValueError,TypeError,OverflowError):
        return None,"INVALID_EVIDENCE"

def shadow(base_probability,scheduled_at,fixture_id,evidence):
    """Return research-only diagnostic, never a calibrated or registered forecast."""
    if type(base_probability) not in (float,int) or not math.isfinite(base_probability) or not 0<base_probability<1:
        raise ValueError("INVALID_BASE_PROBABILITY")
    start=timestamp(scheduled_at)
    evidence=evidence or {}
    if not isinstance(evidence,dict):raise ValueError("INVALID_EVIDENCE_COLLECTION")
    corrections={};missing={};measures={}
    for name in FEATURES:
        entry=evidence.get(name)
        if entry is not None and (not isinstance(entry,dict) or entry.get("match_id")!=fixture_id):
            missing[name]="FIXTURE_MISMATCH";continue
        value,reason=checked_feature(name,entry,start)
        if reason:missing[name]=reason
        else:
            corrections[name]=value
            measures[name]={"a":entry["raw"]["a"],"b":entry["raw"]["b"],"effective_n":entry["raw"]["effective_n"],"source_sha256":entry["source_sha256"],"evidence_type":entry["evidence_type"]}
    # Evidence values are displayed, but no arbitrary untrained combination
    # can become a probability until properly fitted and prospectively validated.
    return {"version":"MATCHUP_INTELLIGENCE_V2_SHADOW_0_1","status":"research_only",
            "registered_prediction_unchanged":True,"baseline_p_a":float(base_probability),
            "candidate_delta_pp":None,"uncalibrated_diagnostic_only":True,
            "observed_feature_measures":measures,
            "verified_features":sorted(corrections),"missing_features":missing,
            "evidence_digest":digest(evidence),"eligible_for_promotion":False}
