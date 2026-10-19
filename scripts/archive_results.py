"""Archive verified result observations on both evidence branches without overwrites."""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime,timezone
from pathlib import Path
from gh_evidence import GitHub,BRANCHES,canonical

def archive_results(data,client,run_id,now=None):
    if not isinstance(data,dict) or not isinstance(data.get("settlements"),list):
        raise ValueError("INVALID_SETTLEMENT_REPORT")
    now=now or datetime.now(timezone.utc)
    payload={"schema_version":1,"run_id":str(run_id),
             "retrieval_health":data.get("health",[]),
             "settlements":data["settlements"],
             "exclusions":data.get("exclusions",{}),
             "exclusion_details":data.get("exclusion_details",{})}
    raw=canonical(payload)
    digest=hashlib.sha256(raw).hexdigest()
    path=f'evidence/results/{now:%Y/%m/%d}/{run_id}/{digest}.json'
    receipts={}
    for branch in BRANCHES:
        try:receipts[branch]={"status":client.save(branch,path,raw),"digest":digest}
        except Exception as exc:receipts[branch]={"status":"failed","error":type(exc).__name__}
    return {"path":path,"sha256":digest,"destinations":receipts,
            "remote_verified":any(x["status"] in ("verified","existing") for x in receipts.values())}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--output",default="work/result-archive-report.json")
    args=parser.parse_args()
    report=json.loads(Path(args.report).read_text())
    result=archive_results(report,GitHub(os.environ["GITHUB_REPOSITORY"],os.environ["GH_TOKEN"]),os.environ["GITHUB_RUN_ID"])
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    return 0 if result["remote_verified"] else 1
if __name__=="__main__":sys.exit(main())
