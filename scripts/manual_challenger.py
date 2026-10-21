"""Human-entered Challenger fixture ledger. No automatic Challenger discovery.

An empty/missing ledger means no Challenger forecasts, never synthetic coverage.
Entries must be manually reviewed, source-linked, and time bounded.
"""
import json,re
from datetime import timedelta
from pathlib import Path
from collect import key,timestamp
PATH=Path("data/manual_challenger_fixtures.json")
REQUIRED=("source_match_id","source_event_id","tour","tournament","tournament_key","regime","surface","name_a","name_b","starts_at","round","event_source","surface_source","format_source","source_player_ids","reviewed_at","reviewer")
def load(now):
    if not PATH.is_file():return [],{"status":"missing_manual_ledger","accepted":0,"rejected":0}
    try:
        entries=json.loads(PATH.read_text(encoding="utf8"))
        if not isinstance(entries,list):raise ValueError("EXPECTED_LIST")
    except (OSError,ValueError):
        return [],{"status":"invalid_manual_ledger","accepted":0,"rejected":0}
    accepted=[];rejected=0;seen=set()
    for row in entries:
        try:
            if not isinstance(row,dict) or any(not row.get(k) for k in REQUIRED):raise ValueError()
            if row["tour"] not in ("ATP","WTA") or row["regime"] not in ("challenger","wta125"):raise ValueError()
            if (row["tour"],row["regime"]) not in (("ATP","challenger"),("WTA","wta125")):raise ValueError()
            if row["surface"] not in ("Hard","Clay","Grass"):raise ValueError()
            if not isinstance(row["source_player_ids"],list) or len(row["source_player_ids"])!=2 or len(set(map(str,row["source_player_ids"])))!=2:raise ValueError()
            if not all(isinstance(row[k],str) and 3<=len(row[k])<=160 for k in ("name_a","name_b","tournament")):raise ValueError()
            if key(row["name_a"])==key(row["name_b"]):raise ValueError()
            if not all(isinstance(row[k],str) and row[k].startswith("https://") for k in ("event_source","surface_source","format_source")):raise ValueError()
            if not re.fullmatch(r"[a-zA-Z0-9:_-]{3,120}",str(row["source_match_id"])):raise ValueError()
            start=timestamp(row["starts_at"]);review=timestamp(row["reviewed_at"])
            if not now<start<=now+timedelta(hours=24) or not now-timedelta(hours=12)<=review<=now:raise ValueError()
            identity=(row["tour"],row["source_match_id"])
            if identity in seen:raise ValueError()
            seen.add(identity)
            a,b=row["name_a"],row["name_b"]
            accepted.append({k:row[k] for k in ("source_match_id","source_event_id","tour","tournament","tournament_key","regime","surface","name_a","name_b","starts_at","round","event_source","surface_source","format_source","source_player_ids")}|{
                "player_a":row["tour"]+":"+key(a),"player_b":row["tour"]+":"+key(b),
                "court_enclosure":row.get("court_enclosure","Unknown"),
                "start_verified":True,"event_scope":"singles","source_state":"scheduled",
                "best_of":3,"deciding_tiebreak_target":7,"format_verified":True,
                "timing_kind":"HUMAN_REVIEWED_SOURCE_SCHEDULED",
                "source_provenance":"MANUAL_VERIFIED"})
        except (KeyError,ValueError,TypeError):rejected+=1
    return accepted,{"status":"manual_only","accepted":len(accepted),"rejected":rejected}
