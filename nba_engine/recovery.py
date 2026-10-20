"""Atomic verified snapshot publication and conservative stale-data rejection."""
import json, os, tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

def publish(snapshot, path, max_age_minutes=60):
    if not snapshot or not isinstance(snapshot,list): raise ValueError("Empty scan")
    now=datetime.now(timezone.utc)
    seen=set()
    for row in snapshot:
        if row.get("status")!="UNCALIBRATED_RESEARCH": raise ValueError("Unknown model state")
        if row.get("game_id") in seen or not row.get("game_id"): raise ValueError("Duplicate/missing game")
        seen.add(row["game_id"])
        stamp=datetime.fromisoformat(row["asof_utc"].replace("Z","+00:00"))
        if stamp.tzinfo is None or stamp>now or now-stamp>timedelta(minutes=max_age_minutes):
            raise ValueError("Stale or future snapshot")
    dest=Path(path)
    dest.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".nba-",dir=str(dest.parent))
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(snapshot,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,dest)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return str(dest)
