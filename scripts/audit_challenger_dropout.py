"""Detect Challenger fixture dropout without fabricating a live forecast."""
import json,sys
from pathlib import Path

def audit(current,prior):
    def future_challenger(doc):
        from datetime import datetime,timezone
        cutoff=datetime.fromisoformat(current["generated_at"].replace("Z","+00:00"))
        return [m for m in doc.get("matches",[]) if m.get("regime","").startswith("challenger")
                and datetime.fromisoformat(m["starts_at"].replace("Z","+00:00"))>cutoff]
    previous=future_challenger(prior);now=future_challenger(current)
    if previous and not now:
        return {"status":"DEGRADED_CHALLENGER_COVERAGE","previous_future_challenger_matches":len(previous),
                "current_challenger_matches":0,"action":"WITHHOLD_ALL_TOUR_COMPLETENESS_CLAIM",
                "note":"Historical matches are not auto-published as fresh forecasts; restore current independently verified sources."}
    return {"status":"NO_TOTAL_CHALLENGER_DROPOUT_DETECTED",
            "previous_future_challenger_matches":len(previous),"current_challenger_matches":len(now)}
if __name__=="__main__":
    current=json.loads(Path(sys.argv[1]).read_text())
    old=json.loads(Path(sys.argv[2]).read_text())
    result=audit(current,old)
    print(json.dumps(result))
    if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(result,indent=2)+"\n")
