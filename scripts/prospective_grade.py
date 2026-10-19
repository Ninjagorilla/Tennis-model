"""Read-only prospective tennis forecast grading. No Champion promotion.

Consumes immutable forecasts and independently reconciled results. Refuses to grade
forecasts recorded at/after scheduled start or results recorded before match completion.
"""
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROLES = ("champion", "challenger", "experimental")

def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_WITHOUT_TIMEZONE")
    return dt.astimezone(timezone.utc)

def evaluate(forecasts, outcomes):
    """Return graded metrics and exclusions; no missing predictions are imputed."""
    ledger = {}
    for item in forecasts:
        key = item["fixture_id"]
        if key in ledger:
            raise ValueError("DUPLICATE_FORECAST_ID")
        ledger[key] = item
    results = {}
    for item in outcomes:
        key = item["fixture_id"]
        if key in results:
            raise ValueError("DUPLICATE_OUTCOME_ID")
        results[key] = item
    samples = defaultdict(list)
    exclusions = defaultdict(int)
    for key, row in ledger.items():
        outcome = results.get(key)
        if not outcome:
            exclusions["OUTCOME_MISSING"] += 1
            continue
        try:
            issued = timestamp(row["issued_at"])
            start = timestamp(row["starts_at"])
            completed = timestamp(outcome["completed_at"])
            recorded = timestamp(outcome["recorded_at"])
            if issued >= start or completed < start or recorded < completed:
                exclusions["POINT_IN_TIME_VIOLATION"] += 1
                continue
            if row["tour"] != outcome["tour"]:
                exclusions["TOUR_MISMATCH"] += 1
                continue
            winner = outcome["winner"]
            if winner not in ("a", "b"):
                exclusions["NON_DECISIVE_RESULT"] += 1
                continue
            for role in ROLES:
                prediction = row.get("results", {}).get(role, {})
                if prediction.get("status") != "ok":
                    exclusions[role.upper() + "_UNAVAILABLE"] += 1
                    continue
                p = prediction.get("p_a")
                if type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1:
                    exclusions[role.upper() + "_INVALID_PROBABILITY"] += 1
                    continue
                y = 1 if winner == "a" else 0
                samples[(row["tour"], role)].append((p, y))
        except (KeyError, ValueError, TypeError):
            exclusions["INVALID_RECORD"] += 1
    by_tour = {}
    for (tour, role), values in sorted(samples.items()):
        brier = sum((p-y)**2 for p,y in values)/len(values)
        logloss = -sum(y*math.log(max(1e-15,min(1-1e-15,p))) + (1-y)*math.log(max(1e-15,min(1-1e-15,1-p))) for p,y in values)/len(values)
        by_tour.setdefault(tour, {})[role] = {
            "n": len(values), "brier": round(brier, 8),
            "log_loss": round(logloss, 8),
            "mean_prediction": round(sum(p for p,_ in values)/len(values), 8),
            "observed_rate_a": round(sum(y for _,y in values)/len(values), 8),
        }
    return {"status":"research_only","promotion_authorized":False,
            "metrics_by_tour":by_tour,"exclusions":dict(sorted(exclusions.items()))}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("forecasts")
    parser.add_argument("outcomes")
    parser.add_argument("--output",default="work/tennis-prospective-grades.json")
    args=parser.parse_args()
    report=evaluate(json.loads(Path(args.forecasts).read_text()),json.loads(Path(args.outcomes).read_text()))
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
if __name__=="__main__":
    main()
