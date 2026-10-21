"""Check Challenger fixture presence without treating a green job as full coverage."""
import json,sys
from pathlib import Path

def assess(snapshot):
    matches=snapshot.get("matches") or []
    challenger=[m for m in matches if str(m.get("regime","")).startswith("challenger")]
    unavailable=snapshot.get("coverage",{}).get("unavailable_scopes",[])
    missing=not challenger or "ATP Challenger" in unavailable
    return {"challenger_missing":missing,"challenger_count":len(challenger),"status":"degraded" if missing else "present_not_exhaustive"}

if __name__=="__main__":
    data=json.loads(Path(sys.argv[1] if len(sys.argv)>1 else "work/snapshot.json").read_text())
    report=assess(data)
    Path("work/challenger-coverage.json").write_text(json.dumps(report))
    print(json.dumps(report))
    if report["challenger_missing"]:sys.exit(2)
