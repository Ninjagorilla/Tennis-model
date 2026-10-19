"""Recover persisted pre-match evidence for outcome reconciliation.

Read primary evidence branch first, mirror second. Never use a cached current
forecast as proof of historical predictions. File SHA is checked against its path.
"""
import argparse
import base64
import hashlib
import json
import os
from datetime import datetime,timedelta,timezone
from pathlib import Path
from gh_evidence import GitHub,BRANCHES

def historical_records(client,now=None,days=4,max_files=260):
    now=now or datetime.now(timezone.utc)
    reasons={}
    for branch in BRANCHES:
        try:
            listing=client.api("GET","/git/trees/"+branch+"?recursive=1")
            if not listing or listing.get("truncated") or not isinstance(listing.get("tree"),list):
                raise RuntimeError("TREE_MISSING_OR_TRUNCATED")
            paths=[]
            for item in listing["tree"]:
                path=item.get("path","")
                if item.get("type")!="blob" or not path.startswith("evidence/forecasts/") or not path.endswith(".json"):
                    continue
                pieces=path.split("/")
                if len(pieces)!=7:continue
                try:date=datetime.strptime("/".join(pieces[2:5]),"%Y/%m/%d").replace(tzinfo=timezone.utc)
                except ValueError:continue
                if not now-timedelta(days=days+1)<=date<=now:continue
                paths.append(path)
            if not paths:raise RuntimeError("NO_RECENT_EVIDENCE_ON_BRANCH")
            if len(paths)>max_files:raise RuntimeError("EVIDENCE_FILE_CAP_EXCEEDED")
            forecasts={}
            for path in sorted(paths):
                data=client.api("GET","/contents/"+path+"?ref="+branch)
                if not data or data.get("encoding")!="base64":raise RuntimeError("EVIDENCE_FETCH_FAILED")
                raw=base64.b64decode(data["content"].replace("\n",""),validate=True)
                expected=path.rsplit("/",1)[-1].removesuffix(".json")
                if hashlib.sha256(raw).hexdigest()!=expected:raise RuntimeError("EVIDENCE_DIGEST_MISMATCH")
                doc=json.loads(raw)
                # GitHub's server-side commit time is the externally witnessed
                # archival receipt. A caller-supplied issued_at is not enough.
                from urllib.parse import quote
                commits=client.api("GET","/commits?path="+quote(path,safe="")+
                                   "&sha="+branch+"&per_page=1")
                if not isinstance(commits,list) or not commits:
                    raise RuntimeError("RECEIPT_COMMIT_NOT_VERIFIABLE")
                receipt=datetime.fromisoformat(commits[0]["commit"]["committer"]["date"].replace("Z","+00:00"))
                if receipt.tzinfo is None:
                    raise RuntimeError("RECEIPT_COMMIT_TIME_INVALID")
                if doc.get("schema_version")!=1 or not isinstance(doc.get("records"),list):
                    raise RuntimeError("EVIDENCE_SCHEMA_MISMATCH")
                for row in doc["records"]:
                    when=datetime.fromisoformat(row["issued_at"].replace("Z","+00:00"))
                    if when.tzinfo is None or not now-timedelta(days=days)<=when<=now:continue
                    start=datetime.fromisoformat(row["starts_at"].replace("Z","+00:00"))
                    if when>=start or receipt>=start:
                        # A late commit cannot be scored as a pre-match forecast.
                        continue
                    key=row["fixture_id"]
                    # Earliest archived pre-match forecast is the pre-registered one.
                    if key not in forecasts or when<datetime.fromisoformat(forecasts[key]["issued_at"].replace("Z","+00:00")):
                        forecasts[key]=row
            if not forecasts:raise RuntimeError("NO_ELIGIBLE_EVIDENCE_ON_BRANCH")
            return {"source":branch,"forecasts":list(forecasts.values()),"files_verified":len(paths)}
        except Exception as exc:
            reasons[branch]=type(exc).__name__
    raise RuntimeError("ALL_EVIDENCE_READ_PATHS_UNAVAILABLE:"+json.dumps(reasons))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="work/historical-forecasts.json")
    args=parser.parse_args()
    client=GitHub(os.environ["GITHUB_REPOSITORY"],os.environ["GH_TOKEN"])
    report=historical_records(client)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report["forecasts"],ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"source":report["source"],"records":len(report["forecasts"]),
                      "files_verified":report["files_verified"]}))
if __name__=="__main__":main()
