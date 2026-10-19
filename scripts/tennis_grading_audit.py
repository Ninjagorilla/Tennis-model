"""Read-only prospective audit from archived forecasts and two-source settlements.

Never equate a forecast with a settled match, count missing results as losses,
or authorize Champion promotion. Metrics only use reconciled independent results.
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from result_reconciliation import reconcile,grade
from paired_evaluation import paired

ROLES=("champion","challenger","experimental")

def audit(forecasts,report):
    if not isinstance(forecasts,list) or not isinstance(report,dict):
        raise ValueError("INVALID_AUDIT_INPUT")
    outcomes=report.get("settlements")
    if not isinstance(outcomes,list):raise ValueError("MISSING_SETTLEMENTS")
    matched,settled,errors=reconcile(forecasts,outcomes)
    evaluated=grade(forecasts,outcomes)
    paired_report=paired(matched,settled)
    actual={o["fixture_id"]:o["winner"] for o in settled}
    per=defaultdict(lambda:{"n":0,"correct":0,"brier_total":0.0,"log_total":0.0})
    for f in matched:
        for role in ROLES:
            pred=f.get("results",{}).get(role,{})
            p=pred.get("p_a")
            if pred.get("status")!="ok" or type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1:
                continue
            y=int(actual[f["fixture_id"]]=="a")
            key=(f["tour"],role)
            d=per[key]
            d["n"]+=1
            # A 50/50 prediction is a tie, not a correct winner pick.
            d["correct"]+=int((p>0.5 and y==1) or (p<0.5 and y==0))
            d["brier_total"]+=(p-y)**2
            d["log_total"]+=-(y*math.log(max(p,1e-15))+(1-y)*math.log(max(1-p,1e-15)))
    metrics={}
    for (tour,role),d in sorted(per.items()):
        metrics.setdefault(tour,{})[role]={
            "n":d["n"],"correct":d["correct"],
            "winner_accuracy":round(d["correct"]/d["n"],6),
            "brier":round(d["brier_total"]/d["n"],8),
            "log_loss":round(d["log_total"]/d["n"],8)}
    health=report.get("health",[])
    health=health if isinstance(health,list) else []
    return {"schema_version":1,"status":"research_only",
        "forecast_fixtures":len({f["fixture_id"] for f in forecasts}),
        "two_source_verified":len(matched),
        "unverified_or_missing":len(forecasts)-len(matched),
        "source_checks":{"healthy":sum(h.get("status")=="ok" for h in health),"total":len(health)},
        "exclusions":{"collector":report.get("exclusions",{}),"reconciliation":errors},
        "model_metrics_by_tour":metrics,
        "paired":paired_report["paired_by_tour"],
        "market_upset_performance":"unavailable_without_point_in_time_market_odds",
        "promotion_authorized":False,
        "seven_day_reliability":"not_established_from_one_run"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("forecasts")
    parser.add_argument("settlements")
    parser.add_argument("--output",default="work/tennis-grading-audit.json")
    args=parser.parse_args()
    forecasts=json.loads(Path(args.forecasts).read_text())
    settlements=json.loads(Path(args.settlements).read_text())
    result=audit(forecasts,settlements)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"forecasts":result["forecast_fixtures"],
                      "verified":result["two_source_verified"],
                      "paired_tours":list(result["paired"])}))
if __name__=="__main__":main()
