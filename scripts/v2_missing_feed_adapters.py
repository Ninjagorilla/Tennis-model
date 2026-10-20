"""Experimental V2 missing-data collector. Read-only; NEVER changes win probabilities.

Weather uses Open-Meteo's free forecast API only for a supplied, verified
court coordinate. Historical weather must NOT be substituted for an archived
pre-match forecast. Workload and availability observations require exact
publication timestamps and explicit provenance; absent reports mean UNKNOWN.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import hashlib,json,math,urllib.request

WEATHER_API="https://api.open-meteo.com/v1/forecast"
WEATHER_VARIABLES=("temperature_2m","relative_humidity_2m","precipitation_probability","wind_speed_10m")
OFFICIAL_SOURCES=("https://www.atptour.com/","https://www.wtatennis.com/",
                  "https://www.tennis.com/","https://site.api.espn.com/")
SUPPORTED_STATUSES={"withdrawn","officially_out","questionable","listed_to_play"}

def moment(value):
    d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError("TIMESTAMP_WITHOUT_TIMEZONE")
    return d.astimezone(timezone.utc)

def finite_number(value,low,high):
    if type(value) not in (float,int) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError("INVALID_NUMERIC_OBSERVATION")
    return float(value)

def source_ok(url):
    return isinstance(url,str) and url.startswith(OFFICIAL_SOURCES)

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def safe_venue(venue,match_start):
    """Require a source-audited *court* location, not an inferred city center."""
    if not isinstance(venue,dict) or venue.get("verification")!="source_checked":
        return None,"VENUE_COORDINATES_UNVERIFIED"
    try:
        lat=finite_number(venue["lat"],-90,90)
        lon=finite_number(venue["lon"],-180,180)
        if not source_ok(venue["source_url"]):return None,"VENUE_SOURCE_UNAPPROVED"
        if not isinstance(venue.get("source_sha256"),str) or len(venue["source_sha256"])!=64 or any(c not in "0123456789abcdef" for c in venue["source_sha256"].lower()):
            return None,"VENUE_RECEIPT_MISSING"
        if moment(venue["verified_at"])>=match_start:return None,"VENUE_VERIFIED_TOO_LATE"
        if venue.get("court_enclosure") not in ("Indoor","Outdoor"):
            return None,"VENUE_ENCLOSURE_UNVERIFIED"
        return {**venue,"lat":lat,"lon":lon},None
    except (KeyError,ValueError,TypeError):
        return None,"VENUE_RECEIPT_INVALID"

def weather_forecast(match,venue,*,fetcher=None,now=None):
    """Observed forecast for the match-hour, not player-specific probabilities."""
    start=moment(match["starts_at"])
    at=moment(now) if now is not None else datetime.now(timezone.utc)
    if not at<start:return {"status":"unavailable","reason":"NO_PREMATCH_FORECAST"}
    verified,error=safe_venue(venue,start)
    if error:return {"status":"unavailable","reason":error}
    if verified["court_enclosure"]=="Indoor":
        return {"status":"not_applicable","reason":"INDOOR_COURT","win_probability_adjustment":None}
    if start-at>timedelta(days=7):
        return {"status":"unavailable","reason":"FORECAST_OUTSIDE_SEVEN_DAY_WINDOW"}
    params={"latitude":str(verified["lat"]),"longitude":str(verified["lon"]),
            "hourly":",".join(WEATHER_VARIABLES),"timezone":"UTC","forecast_days":"8"}
    url=WEATHER_API+"?"+urlencode(params)
    try:
        if fetcher is None:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"TennisModelV2-Research/0.1"}),timeout=12) as resp:
                if resp.url.split("?",1)[0]!=WEATHER_API:raise ValueError("UNEXPECTED_WEATHER_REDIRECT")
                raw=resp.read(1000001)
        else:raw=fetcher(url)
        if not isinstance(raw,bytes) or len(raw)>1000000 or len(raw)<15:raise ValueError("INVALID_WEATHER_PAYLOAD")
        obtained=moment(now) if now is not None else datetime.now(timezone.utc)
        if obtained>=start:raise ValueError("RETRIEVED_AFTER_MATCH_START")
        parsed=json.loads(raw.decode("utf-8"))
        hourly=parsed["hourly"]
        when=hourly["time"]
        if not isinstance(when,list) or len(when)>300:raise ValueError("INVALID_HOURLY_TIMES")
        target=start.replace(minute=0,second=0,microsecond=0)
        indexes=[i for i,t in enumerate(when) if moment(t+"+00:00" if len(t)==16 else t)==target]
        if len(indexes)!=1:raise ValueError("NO_UNIQUE_MATCH_HOUR")
        ix=indexes[0];values={}
        limits={"temperature_2m":(-65,65),"relative_humidity_2m":(0,100),
                "precipitation_probability":(0,100),"wind_speed_10m":(0,250)}
        for k in WEATHER_VARIABLES:
            if not isinstance(hourly[k],list) or len(hourly[k])!=len(when):
                raise ValueError("WEATHER_ARRAY_LENGTH_MISMATCH")
            values[k]=finite_number(hourly[k][ix],*limits[k])
        # Compare location with weather grid output; allows nearby forecast grid
        # cells without pretending forecast coordinates are exact court location.
        if abs(finite_number(parsed["latitude"],-90,90)-verified["lat"])>0.6 or abs(finite_number(parsed["longitude"],-180,180)-verified["lon"])>0.6:
            raise ValueError("WEATHER_GRID_TOO_FAR")
        return {"status":"observed","kind":"PREMATCH_FORECAST_NOT_ACTUAL_WEATHER",
                "match_id":match["source_match_id"],"forecast_hour_utc":target.isoformat(),
                "retrieved_at":obtained.isoformat(),"source_url":url,
                "source_sha256":sha256(raw),"venue_receipt":verified["source_sha256"],
                "values":values,"win_probability_adjustment":None}
    except (ValueError,KeyError,TypeError,UnicodeError,TimeoutError,OSError,json.JSONDecodeError) as exc:
        # No implicit fallback to live/current weather or unspecified city.
        return {"status":"unavailable","reason":"FORECAST_FETCH_OR_VALIDATION_FAILED",
                "failure_type":type(exc).__name__}

def exact_workload(match,records,player_ids,*,as_of):
    """Descriptive counts ONLY for explicitly timestamped, published completed matches."""
    start=moment(match["starts_at"]);observed=moment(as_of)
    if observed>=start:return {"status":"unavailable","reason":"NO_PREMATCH_OBSERVATION"}
    if not isinstance(records,list) or not isinstance(player_ids,dict) or set(player_ids)!={"a","b"} or player_ids["a"]==player_ids["b"]:
        return {"status":"unavailable","reason":"UNVERIFIED_PLAYER_IDENTITIES"}
    if not records:return {"status":"unavailable","reason":"NO_EXACT_COMPLETION_FEED"}
    output={}
    for side,pid in player_ids.items():
        own=[];ids=set()
        for r in records:
            if r.get("player_id")!=pid:continue
            try:
                finished=moment(r["finished_at"]);published=moment(r["published_at"])
                if not finished<=published<=observed or finished>=start:continue
                if not source_ok(r["source_url"]) or r.get("status")!="completed":continue
                n=finite_number(r["duration_minutes"],1,600)
                uid=r["source_match_id"]
                if not isinstance(uid,str) or not uid or uid in ids:raise ValueError("DUPLICATE_OBSERVATION")
                ids.add(uid)
                own.append((finished,n))
            except (ValueError,KeyError,TypeError):
                return {"status":"unavailable","reason":"INVALID_EXACT_MATCH_RECEIPT"}
        if not own:return {"status":"unavailable","reason":"INCOMPLETE_WORKLOAD_COVERAGE","player_side":side}
        last=max(t for t,_ in own)
        output[side]={"observed_matches_7d":sum(start-t<=timedelta(days=7) for t,_ in own),
                      "observed_matches_14d":sum(start-t<=timedelta(days=14) for t,_ in own),
                      "observed_court_minutes_7d":sum(n for t,n in own if start-t<=timedelta(days=7)),
                      "observed_court_minutes_14d":sum(n for t,n in own if start-t<=timedelta(days=14)),
                      "rest_hours_since_last_observed_match":round((start-last).total_seconds()/3600,2)}
    return {"status":"observed_partial_coverage","players":output,
            "coverage_note":"Only supplied, exact-timestamp completed matches. Not a claim that all recent events were found.",
            "win_probability_adjustment":None}

def official_availability(match,notices,player_ids,*,as_of):
    """Report sourced public participation notices only, never diagnose injuries."""
    start=moment(match["starts_at"]);observed=moment(as_of)
    if not observed<start:return {"status":"unavailable","reason":"NO_PREMATCH_OBSERVATION"}
    result={}
    for side in ("a","b"):
        notices_for=[]
        for n in notices or []:
            if n.get("player_id")!=player_ids.get(side):continue
            try:
                when=moment(n["published_at"])
                if when>observed or when>=start:continue
                if n.get("status") not in SUPPORTED_STATUSES or not source_ok(n.get("source_url")):continue
                if n.get("fixture_id")!=match["source_match_id"]:continue
                notices_for.append((when,n))
            except (ValueError,KeyError,TypeError):continue
        if not notices_for:result[side]={"status":"unknown","reason":"NO_VERIFIED_OFFICIAL_NOTICE"}
        else:
            latest=max(notices_for,key=lambda pair:pair[0])[1]
            result[side]={"status":"publicly_reported","reported_availability":latest["status"],
                          "published_at":latest["published_at"],"source_url":latest["source_url"]}
    return {"status":"observed_public_notices","players":result,
            "note":"Public participation reports only; absence of a notice does not mean healthy.",
            "win_probability_adjustment":None}
