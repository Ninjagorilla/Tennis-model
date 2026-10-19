"""Genuine independent ESPN + Tennis.com tennis result observation collector.

Both providers are fetched afresh. Unknown formats, IDs, withdrawals, ambiguous
opponents and conflicting winners remain ungraded. No market probabilities used.
"""
import argparse
import hashlib
import json
import re
import urllib.request
from datetime import timedelta,timezone,datetime
from pathlib import Path
from tenniscom import documents,matches,full_name,BASE
from result_reconciliation import grade

ESPN="https://site.api.espn.com/apis/site/v2/sports/tennis"
HOSTS=("https://site.api.espn.com/","https://www.tennis.com/")
MAX_BYTES=4_000_000

def normalize(value):
    import unicodedata
    value=unicodedata.normalize("NFKD",str(value))
    return re.sub(r"[^a-z0-9]+"," ", "".join(c for c in value if not unicodedata.combining(c)).casefold()).strip()

def download(url):
    if not any(url.startswith(host) for host in HOSTS):
        raise ValueError("UNAPPROVED_RESULT_HOST")
    request=urllib.request.Request(url,headers={"User-Agent":"Courtside/1.0 personal research"})
    with urllib.request.urlopen(request,timeout=25) as response:
        if not any(response.url.startswith(host) for host in HOSTS):
            raise ValueError("UNAPPROVED_RESULT_REDIRECT")
        body=response.read(MAX_BYTES+1)
    if len(body)>MAX_BYTES:raise ValueError("RESULT_RESPONSE_TOO_LARGE")
    return body

def espn_observations(doc,tour,observed_at,url,digest):
    out=[]
    for event in doc.get("events",[]):
        for grouping in event.get("groupings",[]):
            slug=grouping.get("grouping",{}).get("slug")
            if slug!=("mens-singles" if tour=="ATP" else "womens-singles"):continue
            for c in grouping.get("competitions",[]):
                try:
                    state=c["status"]["type"]
                    if state.get("state")!="post" or state.get("completed") is not True:
                        continue
                    if state.get("name") not in ("STATUS_FINAL","STATUS_FULL_TIME"):
                        continue
                    if any(x in str(c).lower() for x in ("walkover","retired","retirement","defaulted","abandoned")):
                        continue
                    ps=c["competitors"]
                    if len(ps)!=2 or sum(p.get("winner") is True for p in ps)!=1:
                        continue
                    winner=next(p for p in ps if p.get("winner") is True)
                    a,b=ps
                    if not all(str(p.get("id","")).isdigit() for p in ps):continue
                    out.append({"provider":"espn","tour":tour,"event_id":str(c["id"]),
                        "event_name":event.get("name",""),"name_a":a["athlete"]["displayName"],
                        "name_b":b["athlete"]["displayName"],
                        "winner_name":winner["athlete"]["displayName"],"result_type":"completed",
                        "scheduled_at":c.get("startDate") or c.get("date"),"observed_at":observed_at,
                        "url":url,"source_sha256":digest})
                except (KeyError,ValueError,TypeError):continue
    return out

def tenniscom_observations(doc,tour,observed_at,url,digest):
    out=[]
    for r in matches(doc):
        try:
            cat=r.get("competitionGender")
            if cat!=("men" if tour=="ATP" else "women"):continue
            if r.get("eventCategory")!=("Men's Singles" if tour=="ATP" else "Women's Singles"):
                continue
            if r.get("status")!="completed":continue
            if any(term in str(r.get(field,"")).lower() for term in ("retir","walkover","default","abandon") for field in ("score","status","matchStatus")):
                continue
            players=[r["homeCompetitor"],r["awayCompetitor"]]
            names=[full_name(p) for p in players]
            winner=str(r.get("winnerId",""))
            if not winner:continue
            winner_index=None
            for index,p in enumerate(players):
                if winner in [str(p.get("id","")),str(p.get("competitorId","")),str(p.get("srId","")),str(p.get("sportradarId",""))]:
                    winner_index=index
            if winner_index is None:continue
            mid=str(r["matchScoreKey"])
            if not re.fullmatch(r"sr:sport_event:[0-9]+",mid):continue
            out.append({"provider":"tenniscom","tour":tour,"event_id":mid,
                "event_name":r.get("tournamentSlug",""),"name_a":names[0],
                "name_b":names[1],"winner_name":names[winner_index],
                "result_type":"completed","scheduled_at":r.get("startTime"),
                "observed_at":observed_at,"url":url,"source_sha256":digest})
        except (KeyError,ValueError,TypeError):continue
    return out

def retrieve(forecasts,reader=download,now=None):
    now=now or datetime.now(timezone.utc)
    scheduled_dates=set()
    for f in forecasts:
        try:
            start=datetime.fromisoformat(f["starts_at"].replace("Z","+00:00"))
            if start.tzinfo is None:continue
            if start > now or (now-start)>timedelta(days=7):continue
            scheduled_dates.add(start.astimezone(timezone.utc).date())
        except (KeyError,ValueError,TypeError):continue
    observations=[];health=[]
    # Query both adjacent dates to survive UTC/local-day boundaries.
    requested=sorted({day+timedelta(days=delta) for day in scheduled_dates for delta in (-1,0,1,2)})
    for day in requested:
        for tour in ("ATP","WTA"):
            for provider,url in (("espn",f"{ESPN}/{tour.lower()}/scoreboard?dates={day:%Y%m%d}"),
                                 ("tenniscom",f"{BASE}/?date={day.isoformat()}")):
                try:
                    body=reader(url)
                    digest=hashlib.sha256(body).hexdigest()
                    observed=now.isoformat()
                    doc=json.loads(body) if provider=="espn" else documents(body.decode("utf8"))[0]
                    obs=(espn_observations(doc,tour,observed,url,digest) if provider=="espn"
                         else tenniscom_observations(doc,tour,observed,url,digest))
                    observations.extend(obs)
                    health.append({"provider":provider,"date":day.isoformat(),"status":"ok",
                                   "matches":len(obs),"sha256":digest,"url":url})
                except Exception as exc:
                    health.append({"provider":provider,"date":day.isoformat(),
                                   "status":"unavailable","reason":type(exc).__name__,"url":url})
    return observations,health

def resolve(forecasts,observations,now=None):
    now=now or datetime.now(timezone.utc)
    settlements=[];exclusions={}
    for f in forecasts:
        try:
            start=datetime.fromisoformat(f["starts_at"].replace("Z","+00:00"))
            if start.tzinfo is None or start>now:continue
            names={normalize(f["name_a"]),normalize(f["name_b"])}
            if len(names)!=2:continue
            matches_by_provider={}
            for o in observations:
                if o["tour"]!=f["tour"]:continue
                raw_id=str(f.get("source_match_id") or "")
                if raw_id.startswith("tc:") and o["provider"]=="tenniscom" and o["event_id"]!=raw_id[3:]:continue
                if raw_id.isdigit() and o["provider"]=="espn" and o["event_id"]!=raw_id:continue
                if {normalize(o["name_a"]),normalize(o["name_b"])}!=names:continue
                date=o.get("scheduled_at")
                if date:
                    try:
                        event_time=datetime.fromisoformat(date.replace("Z","+00:00"))
                        if event_time.tzinfo is None or abs((event_time-start).total_seconds())>48*3600:continue
                    except (ValueError,TypeError):continue
                matches_by_provider.setdefault(o["provider"],[]).append(o)
            if any(len({o["event_id"] for o in a})!=1 for a in matches_by_provider.values()) or len(matches_by_provider)<2:
                exclusions[f["fixture_id"]]="SOURCE_MISSING_OR_AMBIGUOUS";continue
            selected=[matches_by_provider[p][0] for p in ("espn","tenniscom")]
            winner_names={normalize(x["winner_name"]) for x in selected}
            if len(winner_names)!=1 or not winner_names.issubset(names):
                exclusions[f["fixture_id"]]="SOURCE_WINNER_DISAGREEMENT";continue
            winner="a" if normalize(f["name_a"]) in winner_names else "b"
            observations_for_grade=[]
            for item in selected:
                observations_for_grade.append({"provider":item["provider"],"event_id":item["event_id"],
                    "name_a":f["name_a"],"name_b":f["name_b"],"winner":winner,
                    "result_type":"completed","observed_at":item["observed_at"],
                    "source_sha256":item["source_sha256"],"url":item["url"]})
            settled_at=max(datetime.fromisoformat(x["observed_at"].replace("Z","+00:00")) for x in selected)
            # Neither provider guarantees precise match completion time. The earliest
            # verified observation is a conservative upper bound, not invented final time.
            completed_at=min(datetime.fromisoformat(x["observed_at"].replace("Z","+00:00")) for x in selected)
            settlements.append({"fixture_id":f["fixture_id"],"tour":f["tour"],
                "name_a":f["name_a"],"name_b":f["name_b"],"winner":winner,
                "result_type":"completed","completed_at":completed_at.isoformat(),
                "recorded_at":settled_at.isoformat(),"observations":observations_for_grade})
        except (KeyError,ValueError,TypeError):
            exclusions[f.get("fixture_id","unknown")]="INVALID_FORECAST_OR_RESULT"
    return settlements,exclusions

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("forecasts")
    parser.add_argument("--output",default="work/settlement-observations.json")
    args=parser.parse_args()
    raw=json.loads(Path(args.forecasts).read_text())
    forecasts=raw.get("records") if isinstance(raw,dict) else raw
    obs,health=retrieve(forecasts)
    settled,excluded=resolve(forecasts,obs)
    report={"settlements":settled,"health":health,"exclusions":excluded,
            "graded_research":grade(forecasts,settled)}
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"settled":len(settled),"excluded":len(excluded),
                      "feeds_ok":sum(x["status"]=="ok" for x in health)}))
if __name__=="__main__":main()
