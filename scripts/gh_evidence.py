"""Durable GitHub evidence receipts with failover, no overwrites or false freshness.

Primary: tennis-evidence branch; backup A: scan-results branch; backup B:
GitHub Actions artifact (uploaded by the trusted workflow, time-limited).
All three remain within GitHub's failure domain.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API="https://api.github.com"
BRANCHES=("tennis-evidence","scan-results")

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def payload(records,run_id):
    if not isinstance(records,list) or not records:
        raise ValueError("NO_FORECAST_RECORDS")
    if not re.fullmatch(r"[0-9]{1,20}",str(run_id)):
        raise ValueError("INVALID_RUN_ID")
    unique=set()
    for r in records:
        if not isinstance(r,dict) or not all(k in r for k in ("fixture_id","issued_at","starts_at","commit","results")):
            raise ValueError("INVALID_FORECAST_RECORD")
        k=(r["fixture_id"],r["issued_at"],r["commit"])
        if k in unique:raise ValueError("DUPLICATE_FORECAST_RECORD")
        unique.add(k)
    obj={"schema_version":1,"run_id":str(run_id),"records":records}
    raw=canonical(obj)
    date=datetime.fromisoformat(records[0]["issued_at"].replace("Z","+00:00"))
    if date.tzinfo is None:raise ValueError("NAIVE_RECORD_DATE")
    digest=hashlib.sha256(raw).hexdigest()
    path=f'evidence/forecasts/{date:%Y/%m/%d}/{run_id}/{digest}.json'
    return path,raw,digest

class GitHub:
    def __init__(self,repo,token,opener=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",repo):
            raise ValueError("INVALID_REPOSITORY")
        if not token:raise ValueError("GITHUB_TOKEN_MISSING")
        self.repo=repo
        self.token=token
        self.open=opener or urllib.request.urlopen

    def api(self,method,route,obj=None):
        url=API+"/repos/"+self.repo+route
        data=canonical(obj) if obj is not None else None
        request=urllib.request.Request(url,data=data,method=method,headers={
            "Authorization":"Bearer "+self.token,"Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28","User-Agent":"Courtside-Evidence/1.0",
            "Content-Type":"application/json"})
        try:
            with self.open(request,timeout=25) as response:
                raw=response.read(5_000_000)
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code==404:return None
            raise

    def ensure_branch(self,branch):
        ref=self.api("GET","/git/ref/heads/"+branch)
        if ref is not None:return
        # CI runs on trusted main only. A first branch starts from main and retains
        # immutable per-run paths; branch names are allowlisted, never user input.
        base=self.api("GET","/git/ref/heads/main")
        if not base:raise RuntimeError("MAIN_REF_UNAVAILABLE")
        self.api("POST","/git/refs",{"ref":"refs/heads/"+branch,"sha":base["object"]["sha"]})
        if not self.api("GET","/git/ref/heads/"+branch):
            raise RuntimeError("BRANCH_BOOTSTRAP_UNVERIFIED")

    def save(self,branch,path,raw):
        if branch not in BRANCHES:raise ValueError("UNAPPROVED_BRANCH")
        self.ensure_branch(branch)
        route="/contents/"+"/".join(urllib.parse.quote(x,safe="") for x in path.split("/"))
        route+="?ref="+branch
        before=self.api("GET",route)
        if before:
            original=base64.b64decode(before.get("content","").replace("\n",""))
            if original!=raw:raise RuntimeError("IMMUTABLE_RECEIPT_COLLISION")
            return "existing"
        doc={"message":"Archive immutable tennis evidence","branch":branch,
             "content":base64.b64encode(raw).decode()}
        try:self.api("PUT",route.split("?")[0],doc)
        except urllib.error.HTTPError:
            # Ambiguous response: only accept an exact byte-for-byte existing receipt.
            existing=self.api("GET",route)
            if not existing or base64.b64decode(existing.get("content","").replace("\n",""))!=raw:
                raise
        after=self.api("GET",route)
        if not after or base64.b64decode(after.get("content","").replace("\n",""))!=raw:
            raise RuntimeError("PERSISTENCE_READBACK_FAILED")
        return "verified"

def archive(records,run_id,client):
    path,raw,digest=payload(records,run_id)
    receipts={}
    for branch in BRANCHES:
        try:
            result=client.save(branch,path,raw)
            receipts[branch]={"status":result,"sha256":digest,"path":path}
        except Exception as exc:
            receipts[branch]={"status":"failed","reason":type(exc).__name__}
    return {"schema_version":1,"sha256":digest,"path":path,
            "remote_verified":any(r["status"] in ("verified","existing") for r in receipts.values()),
            "destinations":receipts,
            "artifact_backup":"workflow_upload_required"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("ledger")
    parser.add_argument("--run-id",help="original GitHub Actions run ID for verified manual artifact restoration")
    parser.add_argument("--report",default="work/evidence-archive-report.json")
    args=parser.parse_args()
    records=[json.loads(line) for line in Path(args.ledger).read_text().splitlines() if line.strip()]
    run=args.run_id or os.environ.get("GITHUB_RUN_ID")
    report=archive(records,run,GitHub(os.environ.get("GITHUB_REPOSITORY",""),os.environ.get("GH_TOKEN","")))
    out=Path(args.report);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
    return 0 if report["remote_verified"] else 1

if __name__=="__main__":sys.exit(main())
