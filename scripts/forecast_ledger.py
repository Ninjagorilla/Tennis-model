"""Fail-closed immutable forecast capture with canonical player orientation.

This creates a local append-only JSONL ledger. A durable remote destination must be
configured separately; do not claim local files alone survive ephemeral CI runners.
"""
import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

ROLES=("champion","challenger","experimental")

def utc(value):
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None: raise ValueError("NAIVE_TIMESTAMP")
    return dt.astimezone(timezone.utc)

def canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)

def stable_id(match):
    players=(match["name_a"],match["name_b"])
    if not all(isinstance(x,str) and x.strip() for x in players) or players[0]==players[1]:
        raise ValueError("INVALID_PLAYER_IDENTITY")
    basis=[match["tour"],match["tournament_key"],match["regime"],match.get("round",""),*sorted(players)]
    return hashlib.sha256(canonical(basis).encode()).hexdigest()

def extract(snapshot, recorded_at, commit):
    now=utc(recorded_at)
    generated=utc(snapshot["generated_at"])
    if generated>now:raise ValueError("FUTURE_GENERATION")
    if snapshot["prediction_status"]!="available":raise ValueError("SCAN_NOT_AVAILABLE")
    if not commit or len(commit)!=40 or any(c not in "0123456789abcdef" for c in commit.lower()):
        raise ValueError("INVALID_COMMIT")
    out=[]
    for match in snapshot["matches"]:
        start=utc(match["starts_at"])
        if now>=start:continue
        probabilities={}
        for role in ROLES:
            p=match["results"][role]
            if p["status"]!="ok":
                probabilities[role]={"status":"unavailable","reason":p.get("reason","UNKNOWN")}
                continue
            a,b=p["p_a"],p["p_b"]
            if type(a) not in (float,int) or type(b) not in (float,int) or not all(math.isfinite(x) for x in (a,b)) or not (0<=a<=1 and 0<=b<=1 and abs(a+b-1)<1e-9):
                raise ValueError("INVALID_PROBABILITY")
            probabilities[role]={k:p[k] for k in ("status","p_a","p_b","model_id","state_date","artifact_sha256")}
        out.append({"fixture_id":stable_id(match),"tour":match["tour"],"tournament_key":match["tournament_key"],
                    "regime":match["regime"],"name_a":match["name_a"],"name_b":match["name_b"],
                    "starts_at":start.isoformat(),"source_match_id":match.get("source_match_id"),
                    "event_source":match.get("event_source"),"round":match.get("round"),
                    "issued_at":now.isoformat(),"source_generated_at":generated.isoformat(),
                    "commit":commit,"results":probabilities})
    return out

def append(path,records):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    existing=set()
    if path.exists():
        for line in path.read_text().splitlines():
            obj=json.loads(line);existing.add((obj["fixture_id"],obj["commit"],obj["issued_at"]))
    with path.open("a",encoding="utf8") as stream:
        for row in records:
            key=(row["fixture_id"],row["commit"],row["issued_at"])
            if key in existing:continue
            stream.write(canonical(row)+"\n");existing.add(key)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("snapshot")
    parser.add_argument("--output",default="work/tennis-forecast-ledger.jsonl")
    parser.add_argument("--commit",default=os.environ.get("GITHUB_SHA",""))
    args=parser.parse_args()
    data=json.loads(Path(args.snapshot).read_text())
    records=extract(data,datetime.now(timezone.utc).isoformat(),args.commit)
    append(args.output,records)
    print(json.dumps({"recorded":len(records),"ledger":str(args.output),"remote_persistence":"NOT_CONFIGURED"}))
if __name__=="__main__":main()
