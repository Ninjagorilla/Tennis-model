"""Fail-closed daily settlement acceptance report, without invented hit rates.

Health != model accuracy. A match pending a verified result is not a loss.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

def assess(forecasts, report, archive):
    if not isinstance(forecasts,list) or not forecasts:
        return {"status":"blocked","alert":True,"reason":"NO_VERIFIED_HISTORICAL_FORECASTS",
                "forecast_count":0,"settled_count":None}
    if not isinstance(report,dict) or not isinstance(report.get("settlements"),list) or not isinstance(report.get("health"),list):
        return {"status":"blocked","alert":True,"reason":"SETTLEMENT_REPORT_MISSING_OR_INVALID",
                "forecast_count":len(forecasts),"settled_count":None}
    by_provider=Counter(h.get("provider") for h in report["health"] if h.get("status")=="ok")
    verified=report["settlements"]
    def has_two_valid_sources(item):
        if not isinstance(item,dict):return False
        observations=item.get("observations")
        if not isinstance(observations,list) or len(observations)<2:return False
        sources=set()
        for obs in observations:
            if not isinstance(obs,dict):return False
            provider=obs.get("provider")
            if provider not in ("espn","tenniscom"):return False
            if not isinstance(obs.get("event_id"),str) or not obs["event_id"]:return False
            if not isinstance(obs.get("source_sha256"),str) or not re.fullmatch("[0-9a-f]{64}",obs["source_sha256"]):return False
            url=obs.get("url","")
            if not isinstance(url,str) or not url.startswith("https://"+("site.api.espn.com/" if provider=="espn" else "www.tennis.com/")):return False
            if obs.get("winner")!=item.get("winner"):return False
            sources.add(provider)
        return sources=={"espn","tenniscom"}
    if any(not has_two_valid_sources(x) for x in verified):
        return {"status":"blocked","alert":True,"reason":"SETTLEMENT_LACKS_TWO_PROVIDER_EVIDENCE",
                "forecast_count":len(forecasts),"settled_count":len(verified)}
    grade=report.get("graded_research",{})
    reconciliation=grade.get("reconciliation",{}) if isinstance(grade,dict) else {}
    if reconciliation.get("verified_fixtures")!=len(verified):
        return {"status":"blocked","alert":True,"reason":"GRADE_COUNT_DISAGREEMENT",
                "forecast_count":len(forecasts),"settled_count":len(verified)}
    archived=bool(isinstance(archive,dict) and archive.get("remote_verified"))
    healthy=by_provider["espn"]>0 and by_provider["tenniscom"]>0
    status=("degraded" if not healthy or not archived else
            "verified_results" if verified else "awaiting_verified_results")
    return {"status":status,"alert":not healthy or not archived,
            "forecast_count":len(forecasts),"settled_count":len(verified),
            "excluded_count":len(report.get("exclusions",{})),
            "source_requests_ok":{"espn":by_provider["espn"],"tenniscom":by_provider["tenniscom"]},
            "settlement_archive_verified":archived,
            "metrics_by_tour":grade.get("metrics_by_tour",{}),
            "promotion_authorized":False}

def load(path):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--forecasts",default="work/historical-forecasts.json")
    p.add_argument("--settlements",default="work/settlement-observations.json")
    p.add_argument("--archive",default="work/result-archive-report.json")
    p.add_argument("--output",default="work/settlement-health.json")
    args=p.parse_args()
    result=assess(load(args.forecasts),load(args.settlements),load(args.archive))
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="metrics_by_tour"}))
    # Workflow records alert state and opens an actionable issue; don't suppress it.
    return 1 if result["alert"] else 0
if __name__=="__main__":
    raise SystemExit(main())
