"""Validated opt-in fixture fallback. Never supplies model probabilities."""
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from quality import identity

def load(path,now):
    doc=json.loads(Path(path).read_text())
    if doc.get("schema_version")!=1:raise ValueError("INVALID_SCHEMA")
    out=[]
    for x in doc.get("fixtures",[]):
        required=("name_a","name_b","source_match_id","source_event_id","tournament","tournament_key","starts_at","surface","source_url","source_checked_at","source_player_ids")
        if any(not x.get(k) for k in required):raise ValueError("INCOMPLETE_FIXTURE")
        t=datetime.fromisoformat(x["starts_at"].replace("Z","+00:00"))
        checked=datetime.fromisoformat(x["source_checked_at"].replace("Z","+00:00"))
        if t.tzinfo is None or checked.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
        if not now<t<=now+timedelta(hours=24) or abs((now-checked).total_seconds())>3600:raise ValueError("STALE_FIXTURE")
        if x["surface"] not in ("Hard","Clay","Grass"):raise ValueError("INVALID_SURFACE")
        if not str(x["source_url"]).startswith("https://"):raise ValueError("SOURCE_REQUIRED")
        if len(x["source_player_ids"])!=2:raise ValueError("PLAYER_IDS_REQUIRED")
        if any(len(x[k].split())<2 for k in ("name_a","name_b")):raise ValueError("FULL_NAMES_REQUIRED")
        if identity("ATP",x["name_a"])==identity("ATP",x["name_b"]):raise ValueError("DUPLICATE_PLAYER")
        out.append(dict(x,tour="ATP",regime="challenger",player_a=identity("ATP",x["name_a"]),player_b=identity("ATP",x["name_b"]),source_match_id="manual:"+str(x["source_match_id"]),event_source=x["source_url"],surface_source=x["source_url"],format_source="https://www.atptour.com/en/corporate/rulebook",best_of=3,deciding_tiebreak_target=7,court_enclosure=x.get("court_enclosure","Unknown"),round=x.get("round",""),start_verified=True,format_verified=True,event_scope="singles",source_state="scheduled",timing_kind="MANUAL_VERIFIED_ESTIMATE"))
    return out
