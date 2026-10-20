"""Phase 1 identity/location and Phase 2 completed-match workload receipts.

No name-only athlete matching, city-centroid geocoding, inferred finish time,
invented duration, inferred medical information or probability adjustment.
Provider athlete identifiers stay explicitly provider-scoped.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,re,urllib.request
from quality import normalize

ESPN="https://site.api.espn.com/apis/site/v2/sports/tennis"
ALLOWED_TOURS=("ATP","WTA")
MAX_BYTES=4_000_000

def utc(value):
    d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    return d.astimezone(timezone.utc)

def scoped_fixture_identity(match):
    """Verify exactly two source athlete IDs aligned with the supplied names.

    This establishes an authoritative *provider-scoped* ID, NOT a universal ID,
    and does not merge different providers based solely on a similar name.
    """
    tour=match.get("tour")
    if tour not in ALLOWED_TOURS:return {"status":"unavailable","reason":"TOUR_UNKNOWN"}
    ids=match.get("source_player_ids")
    if not isinstance(ids,list) or len(ids)!=2:return {"status":"unavailable","reason":"ATHLETE_SOURCE_IDS_MISSING"}
    if not all(isinstance(x,(int,str)) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}",str(x)) for x in ids):
        return {"status":"unavailable","reason":"ATHLETE_SOURCE_ID_INVALID"}
    if str(ids[0])==str(ids[1]):return {"status":"unavailable","reason":"DUPLICATE_ATHLETE_SOURCE_ID"}
    if normalize(match.get("name_a",""))==normalize(match.get("name_b","")):
        return {"status":"unavailable","reason":"AMBIGUOUS_ATHLETE_NAMES"}
    mid=str(match.get("source_match_id",""))
    if mid.isdecimal():
        if not all(str(x).isdecimal() for x in ids):
            return {"status":"unavailable","reason":"ESPN_ID_FORMAT_MISMATCH"}
        provider="espn"
    elif re.fullmatch(r"tc:sr:sport_event:[0-9]+",mid):
        provider="tenniscom"
    else:return {"status":"unavailable","reason":"PROVIDER_IDENTITY_UNKNOWN"}
    # Tournament and scheduled fixture scope must be known before publishing IDs.
    if not match.get("tournament_key") or not match.get("starts_at"):
        return {"status":"unavailable","reason":"MISSING_EVENT_CONTEXT"}
    try:utc(match["starts_at"])
    except (ValueError,TypeError):return {"status":"unavailable","reason":"INVALID_EVENT_START"}
    return {"status":"source_verified","provider":provider,
            "players":{"a":f"{tour}:{provider}:{ids[0]}",
                       "b":f"{tour}:{provider}:{ids[1]}"},
            "source_athlete_ids":{"a":str(ids[0]),"b":str(ids[1])},
            "name_labels":{"a":match["name_a"],"b":match["name_b"]},
            "verification_scope":"athlete IDs observed in this provider's scheduled singles fixture"}

def tournament_location(match):
    """City/country metadata, NEVER exact venue coordinates."""
    slug=str(match.get("tournament_key",""))
    source=str(match.get("surface_source",""))
    if not slug or not source.startswith(("https://www.tennis.com/tournaments/","https://www.wtatennis.com/","https://www.atptour.com/")):
        return {"status":"unavailable","reason":"TOURNAMENT_METADATA_UNVERIFIED"}
    enclosure=match.get("court_enclosure")
    return {"status":"tournament_city_only","tournament_key":slug,
            "tournament":match.get("tournament"),"source_url":source,
            "court_enclosure":enclosure if enclosure in ("Indoor","Outdoor") else None,
            "exact_court_coordinates":None,
            "weather_eligible":False,"reason":"COURT_COORDINATES_NOT_IN_VERIFIED_FEED"}

def parse_espn_completed(doc,tour,*,observed_at,source_url,source_sha256):
    """Read only completed singles, with stable player IDs and scheduled starts.

    The feed does NOT establish exact match finish or duration, so these values
    intentionally remain null. observed_at is when we *saw* final status.
    """
    observed=utc(observed_at)
    if tour not in ALLOWED_TOURS or not isinstance(doc,dict):
        raise ValueError("INVALID_TOUR_OR_DOCUMENT")
    findings=[];by_id={};conflicting=set()
    slug="mens-singles" if tour=="ATP" else "womens-singles"
    for event in doc.get("events",[]):
        for group in event.get("groupings",[]):
            if group.get("grouping",{}).get("slug")!=slug:continue
            for c in group.get("competitions",[]):
                try:
                    state=c["status"]["type"]
                    if state.get("completed") is not True or state.get("state")!="post":
                        continue
                    if state.get("name") not in ("STATUS_FINAL","STATUS_FULL_TIME"):
                        continue
                    if re.search(r"\b(?:ret|retired|retirement|w/?o|walkover|defaulted|abandoned|cancelled)\b",str(c),re.IGNORECASE):
                        continue
                    start=utc(c.get("startDate") or c["date"])
                    if start>=observed:continue
                    competitors=c["competitors"]
                    if len(competitors)!=2 or sum(p.get("winner") is True for p in competitors)!=1:
                        continue
                    ids=[str(p["id"]) for p in competitors]
                    names=[str(p["athlete"]["displayName"]) for p in competitors]
                    if any(not re.fullmatch(r"[0-9]{1,16}",n) for n in ids):
                        continue
                    if len(set(ids))!=2 or normalize(names[0])==normalize(names[1]):
                        continue
                    match_id=str(c["id"])
                    if not re.fullmatch(r"[0-9]{1,24}",match_id):continue
                    receipt={"match_id":match_id,"tour":tour,"source":"espn",
                             "scheduled_start_at":start.isoformat(),
                             "first_observed_final_at":observed.isoformat(),
                             "source_url":source_url,"source_sha256":source_sha256,
                             "player_ids":ids,"winner_id":ids[0] if competitors[0]["winner"] is True else ids[1],
                             "actual_finished_at":None,"duration_minutes":None,
                             "precision":"SCHEDULED_START_AND_FINAL_OBSERVATION_ONLY"}
                    if match_id in conflicting:continue
                    if match_id in by_id:
                        if {k:v for k,v in by_id[match_id].items() if k not in ("source_sha256","first_observed_final_at")} != {k:v for k,v in receipt.items() if k not in ("source_sha256","first_observed_final_at")}:
                            # One source contradicting itself is never a vote:
                            # withhold that entire event ID, not one arbitrary row.
                            conflicting.add(match_id)
                            del by_id[match_id]
                        continue
                    by_id[match_id]=receipt
                except (KeyError,ValueError,TypeError):
                    continue
    return list(by_id.values())

def fetch_espn_date(tour,day,*,reader=None,now=None):
    """Read a bounded, HTTPS provider snapshot and bind byte-level provenance."""
    if tour not in ALLOWED_TOURS:raise ValueError("INVALID_TOUR")
    stamp=utc(now) if now is not None else datetime.now(timezone.utc)
    url=f"{ESPN}/{tour.lower()}/scoreboard?dates={day:%Y%m%d}"
    if reader is None:
        request=urllib.request.Request(url,headers={"User-Agent":"Courtside-V2-Workload/0.1"})
        with urllib.request.urlopen(request,timeout=18) as response:
            if response.url!=url:raise ValueError("UNEXPECTED_ESPN_REDIRECT")
            raw=response.read(MAX_BYTES+1)
    else:raw=reader(url)
    if not isinstance(raw,bytes) or len(raw)>MAX_BYTES:raise ValueError("INVALID_PROVIDER_RESPONSE")
    digest=hashlib.sha256(raw).hexdigest()
    doc=json.loads(raw)
    return parse_espn_completed(doc,tour,observed_at=stamp.isoformat(),source_url=url,source_sha256=digest)

def collect_completed(now=None,days=14,*,reader=None):
    """Fetch up to 14 days of *observed* ESPN finals; no invented finish times.

    Includes yesterday/day-boundary overlap, deduplicates across day-specific
    feeds, and discards contradictory duplicate match IDs.
    """
    current=utc(now) if now is not None else datetime.now(timezone.utc)
    if not isinstance(days,int) or not 1<=days<=14:raise ValueError("DAYS_RANGE_INVALID")
    start=(current-timedelta(days=days)).date()
    dates=[start+timedelta(days=d) for d in range((current.date()-start).days+1)]
    queries=[(tour,day) for tour in ALLOWED_TOURS for day in dates]
    def one(arg):
        tour,day=arg
        try:
            items=fetch_espn_date(tour,day,reader=reader,now=current)
            return (arg,items,None)
        except (ValueError,TypeError,KeyError,UnicodeError,OSError,TimeoutError,json.JSONDecodeError) as err:
            return (arg,[],type(err).__name__)
    with ThreadPoolExecutor(max_workers=4) as pool:
        received=list(pool.map(one,queries))
    matches={};blocked=set();health=[]
    for (tour,day),items,error in received:
        health.append({"tour":tour,"date":day.isoformat(),"status":"ok" if error is None else "unavailable",
                       "matches":len(items),"error":error})
        for r in items:
            key=(r["tour"],r["match_id"])
            if key in blocked:continue
            prev=matches.get(key)
            if prev:
                stable=("scheduled_start_at","player_ids","winner_id","precision")
                if any(prev[k]!=r[k] for k in stable):
                    del matches[key];blocked.add(key)
                    continue
                # Both source receipts were observed now; keep one.
            else:matches[key]=r
    return list(matches.values()),{"requested_sources":len(queries),
         "successful_sources":sum(h["status"]=="ok" for h in health),
         "failed_sources":sum(h["status"]!="ok" for h in health),
         "conflicting_match_ids":len(blocked),"feeds":health}

def partial_observed_workload(fixture,identity,completed,*,as_of):
    """Give confirmed 7/14-day completed-start counts only.

    First observed final time is NOT completion time. Without exact finish and
    actual duration, rest and court minutes stay unavailable.
    """
    if identity.get("status")!="source_verified":
        return {"status":"unavailable","reason":"SOURCE_IDENTITIES_UNVERIFIED"}
    if identity["provider"]!="espn":
        return {"status":"unavailable","reason":"HISTORY_PROVIDER_ID_MAPPING_UNAVAILABLE"}
    now=utc(as_of);start=utc(fixture["starts_at"])
    if now>=start:return {"status":"unavailable","reason":"FUTURE_MATCH_ALREADY_STARTED"}
    if not completed:return {"status":"unavailable","reason":"NO_VERIFIED_COMPLETED_MATCH_FEED"}
    sides={};invalid=0
    for side,pid in identity["source_athlete_ids"].items():
        relevant=[];seen=set()
        for record in completed:
            if record.get("tour")!=fixture["tour"] or pid not in record.get("player_ids",[]):
                continue
            try:
                started=utc(record["scheduled_start_at"])
                observed=utc(record["first_observed_final_at"])
                if not started<=observed<=now or started>=start:
                    invalid+=1;continue
                # Match receipts must be tied to the exact provider bytes.
                url=record["source_url"]
                digest=record["source_sha256"]
                if not isinstance(url,str) or not url.startswith(ESPN+"/"+fixture["tour"].lower()+"/scoreboard?dates="):
                    invalid+=1;continue
                if not isinstance(digest,str) or not re.fullmatch("[0-9a-f]{64}",digest):
                    invalid+=1;continue
                uid=record["match_id"]
                if uid in seen:invalid+=1;continue
                seen.add(uid)
                relevant.append(started)
            except (ValueError,KeyError,TypeError):
                invalid+=1
        if not relevant:
            sides[side]={"status":"no_matching_completed_records","completed_starts_7d":None,
                         "completed_starts_14d":None}
        else:
            sides[side]={"status":"partial_observed",
                         "completed_starts_7d":sum(timedelta(0)<=start-t<=timedelta(days=7) for t in relevant),
                         "completed_starts_14d":sum(timedelta(0)<=start-t<=timedelta(days=14) for t in relevant),
                         "last_documented_scheduled_start":max(relevant).isoformat(),
                         "court_minutes":None,"rest_hours":None}
    return {"status":"partial_observed_history","players":sides,
            "invalid_or_late_records":invalid,"observations_not_comprehensive":True,
            "actual_finishes_available":False,"win_probability_adjustment":None}
