"""Conservative, auditable historical evidence for Experimental V2.

Uses the ALREADY PINNED (and SHA-checked) Sackmann match archive loaded by
experimental v3.4-A. Tournament dates are WEEK START proxies, not match dates:
we exclude 21 whole days after each event start. This makes short-term fatigue,
precise rest intervals and pre-match historical backtests impossible. No market.
"""
from datetime import datetime,date,timedelta,timezone
import hashlib,json,math
from pathlib import Path

ALLOWED_ARCHIVES=(
    "https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/",
    "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/",
    "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/",
)
def provenance(history,start):
    """Only accept cached files that agree with their recorded SHA256."""
    sources=[]
    for s in history.get("sources",[]):
        if s.get("unavailable"):continue
        url=s.get("url","")
        path=s.get("local_file")
        sha=s.get("sha256")
        at=s.get("retrieved_at")
        if not url.startswith(ALLOWED_ARCHIVES) or not path or not sha or not at:
            return None
        try:
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:
                return None
            observed=datetime.fromisoformat(at.replace("Z","+00:00"))
            if observed.tzinfo is None or observed.astimezone(timezone.utc)>=start:
                return None
        except (ValueError,OSError,TypeError):
            return None
        sources.append((url,sha,observed))
    if not sources:return None
    # Evidence manifest digest commits to every archive involved, not one file.
    manifest=hashlib.sha256(json.dumps(sorted((u,h) for u,h,_ in sources),sort_keys=True).encode()).hexdigest()
    return {"url":sources[0][0],"sha":manifest,"observed_at":max(x[2] for x in sources).isoformat(),
            "source_count":len(sources),"source_urls":[s[0] for s in sources]}

def history_features(history,a,b,match,*,verify_provenance=True):
    """Derive measured serve, style and H2H evidence, NEVER probability updates.

    H2H requires 3 completed, distinct source matches; sparse H2H remains missing.
    Surface and style require at least 40 underlying service points per player,
    with full historical sources. Data are tournament-start proxies.
    """
    start=datetime.fromisoformat(match["starts_at"].replace("Z","+00:00"))
    if start.tzinfo is None:raise ValueError("MATCH_START_TZ_MISSING")
    if a==b:raise ValueError("DUPLICATE_PLAYER_ID")
    surface=match["surface"].lower()
    if surface not in ("hard","clay","grass"):raise ValueError("SURFACE_UNKNOWN")
    prov=provenance(history,start) if verify_provenance else None
    # Do not pretend synthetic or missing-provenance archives are verified.
    if prov is None:return {},{"status":"ARCHIVE_PROVENANCE_UNAVAILABLE"}
    # Safely exclude an event that may still have been played for weeks
    # following the tournament-start proxy. Date-only replay is NOT certified.
    before=(start.date()-timedelta(days=21))
    relevant={}
    for r in history.get("results",[]):
        try:
            dt=date.fromisoformat(r["date"][:10])
            if dt>before or r.get("temporal_precision")!="TOURNAMENT_START_ONLY":continue
            if a not in (r["winner_id"],r["loser_id"]) and b not in (r["winner_id"],r["loser_id"]):continue
            mid=r["match_id"]
            if mid in relevant:raise ValueError("DUPLICATE_ARCHIVE_MATCH")
            relevant[mid]=r
        except (KeyError,ValueError,TypeError):continue
    stats={a:{"sw":0,"sn":0,"rw":0,"rn":0,"ssw":0,"ssn":0,"srw":0,"srn":0},
           b:{"sw":0,"sn":0,"rw":0,"rn":0,"ssw":0,"ssn":0,"srw":0,"srn":0}}
    # Distinct match identities, with one record per server/receiver for each.
    seen=set()
    for row in history.get("points",[]):
        mid=row.get("match_id")
        if mid not in relevant:continue
        try:
            pid=row["server_id"];recv=row["receiver_id"]
            n=int(row["serve_points_total"]);won=int(row["serve_points_won"])
            if (mid,pid,recv) in seen or not 0<n<=2000 or not 0<=won<=n:
                continue
            seen.add((mid,pid,recv))
            for target in (a,b):
                s=stats[target]
                if pid==target:
                    s["sn"]+=n;s["sw"]+=won
                    if relevant[mid]["surface"]==surface:s["ssn"]+=n;s["ssw"]+=won
                elif recv==target:
                    s["rn"]+=n;s["rw"]+=n-won
                    if relevant[mid]["surface"]==surface:s["srn"]+=n;s["srw"]+=n-won
        except (KeyError,ValueError,TypeError):continue
    output={};summary={"status":"HISTORICAL_DATE_PROXY_21D_EMBARGO","archive_sources":prov["source_count"],
                       "player_a_archive_matches":sum(a in (r["winner_id"],r["loser_id"]) for r in relevant.values()),
                       "player_b_archive_matches":sum(b in (r["winner_id"],r["loser_id"]) for r in relevant.values())}
    def emit(kind,x,y,n):
        output[kind]={"status":"verified","match_id":match["source_match_id"],
            "source_url":prov["url"],"source_sha256":prov["sha"],
            "observed_at":prov["observed_at"],"evidence_type":"ARCHIVE_TOURNAMENT_DATE_PROXY",
            "raw":{"a":round(x,8),"b":round(y,8),"effective_n":n}}
    sa,sb=stats[a],stats[b]
    if sa["ssn"]>=40 and sb["ssn"]>=40 and sa["srn"]>=40 and sb["srn"]>=40:
        # Net point competence, including both serve and return on surface.
        x=(sa["ssw"]/sa["ssn"]+sa["srw"]/sa["srn"])/2
        y=(sb["ssw"]/sb["ssn"]+sb["srw"]/sb["srn"])/2
        emit("surface",x,y,min(sa["ssn"],sb["ssn"],sa["srn"],sb["srn"]))
        summary["surface_point_strength"]={"a":round(x,4),"b":round(y,4)}
    if min(sa["sn"],sb["sn"],sa["rn"],sb["rn"])>=40:
        # Serve reliance vs return efficiency: a descriptive style *proxy*;
        # no inference of labels such as aggressive baseliner or volleyer.
        x=sa["sw"]/sa["sn"]-sa["rw"]/sa["rn"]
        y=sb["sw"]/sb["sn"]-sb["rw"]/sb["rn"]
        emit("style",x,y,min(sa["sn"],sb["sn"],sa["rn"],sb["rn"]))
        summary["serve_reliance_style_proxy"]={"a":round(x,4),"b":round(y,4)}
    direct=[r for r in relevant.values() if {r["winner_id"],r["loser_id"]}=={a,b}]
    summary["h2h_completed_archive_matches"]=len(direct)
    if len(direct)>=3:
        wa=sum(r["winner_id"]==a for r in direct)
        emit("h2h",wa/len(direct),1-wa/len(direct),len(direct))
        summary["h2h_archive_wins"]={"a":wa,"b":len(direct)-wa}
    return output,summary
