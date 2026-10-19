"""Bounded repair and verification of content-addressed GitHub evidence mirrors.

No fabricated forecasts. Restored receipts retain original bytes but new GitHub
commit times; they do NOT become retroactive pre-match proof.
"""
import argparse
import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from gh_evidence import BRANCHES,GitHub

def read_receipt(client,branch,path,digest):
    try:
        data=client.api("GET","/contents/"+path+"?ref="+branch)
        if not data or data.get("encoding")!="base64":return None
        raw=base64.b64decode(data["content"].replace("\n",""),validate=True)
        if hashlib.sha256(raw).hexdigest()!=digest:return None
        return raw
    except Exception:
        return None

def repair(report,client,attempts=2,pause=lambda _:None):
    if attempts not in (1,2):raise ValueError("UNSAFE_ATTEMPTS")
    path=report["path"];digest=report["sha256"]
    if not path.startswith("evidence/") or not path.endswith("/"+digest+".json"):
        raise ValueError("UNSAFE_RECEIPT_PATH")
    if len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("INVALID_DIGEST")
    states={b:read_receipt(client,b,path,digest) for b in BRANCHES}
    present=[b for b in BRANCHES if states[b] is not None]
    if not present:
        return {"status":"critical","reason":"BOTH_MIRRORS_UNVERIFIABLE",
                "verified":0,"repaired":[],"alert":True}
    original=states[present[0]]
    if any(states[b] is not None and states[b]!=original for b in BRANCHES):
        return {"status":"critical","reason":"MIRROR_CONTENT_DISAGREEMENT",
                "verified":len(present),"repaired":[],"alert":True}
    repaired=[]
    for b in BRANCHES:
        if states[b] is not None:continue
        for n in range(attempts):
            try:
                client.save(b,path,original)
                if read_receipt(client,b,path,digest)!=original:
                    raise RuntimeError("RESTORE_READBACK_FAILED")
                repaired.append(b)
                break
            except Exception:
                if n+1<attempts:pause(n)
    final={b:read_receipt(client,b,path,digest) for b in BRANCHES}
    count=sum(v==original for v in final.values())
    return {"status":"healthy" if count==2 else "degraded",
            "verified":count,"repaired":repaired,"alert":count!=2,
            "note":"Repaired branch has a new receipt commit timestamp; never backdate grading."}

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("archive_report")
    cli.add_argument("--output",default="work/evidence-recovery-health.json")
    args=cli.parse_args()
    archive=json.loads(Path(args.archive_report).read_text())
    client=GitHub(os.environ["GITHUB_REPOSITORY"],os.environ["GH_TOKEN"])
    result=repair(archive,client,pause=lambda _:time.sleep(2))
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    return 1 if result["alert"] else 0
if __name__=="__main__":sys.exit(main())
