"""Export a verified offline tennis evidence backup. No GitHub writes.

Run locally and store the resulting ZIP outside GitHub. It includes all immutable
forecast/result receipts visible in the selected branch and a SHA-256 manifest.
"""
import argparse
import base64
import hashlib
import json
import os
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime,timezone
from pathlib import Path

REPO="Ninjagorilla/Tennis-model"
BASE="https://api.github.com/repos/"+REPO
BRANCHES=("tennis-evidence","scan-results")

def fetch(route,token=None):
    headers={"Accept":"application/vnd.github+json","User-Agent":"Tennis-Offline-Backup/1.0"}
    if token:headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+route,headers=headers)
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)

def export(reader,output,max_files=3000):
    failures={}
    for branch in BRANCHES:
        try:
            tree=reader("/git/trees/"+branch+"?recursive=1")
            if tree.get("truncated") or not isinstance(tree.get("tree"),list):
                raise RuntimeError("INCOMPLETE_TREE")
            paths=sorted(x["path"] for x in tree["tree"] if x.get("type")=="blob"
                and x.get("path","").startswith("evidence/")
                and x.get("path","").endswith(".json"))
            if not paths or len(paths)>max_files:raise RuntimeError("NO_EVIDENCE_OR_LIMIT_EXCEEDED")
            contents={}
            for path in paths:
                doc=reader("/contents/"+urllib.parse.quote(path,safe="/")+"?ref="+branch)
                if doc.get("encoding")!="base64":raise RuntimeError("BAD_ENCODING")
                raw=base64.b64decode(doc["content"].replace("\n",""),validate=True)
                sha=path.rsplit("/",1)[-1].removesuffix(".json")
                if len(sha)!=64 or hashlib.sha256(raw).hexdigest()!=sha:
                    raise RuntimeError("DIGEST_MISMATCH")
                contents[path]=raw
            manifest={"schema_version":1,"source_branch":branch,"repository":REPO,
                "exported_at":datetime.now(timezone.utc).isoformat(),
                "files":{path:hashlib.sha256(raw).hexdigest() for path,raw in contents.items()}}
            target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
                for path,raw in contents.items():z.writestr(path,raw)
                z.writestr("manifest.json",json.dumps(manifest,sort_keys=True,indent=2)+"\n")
            return {"status":"verified","branch":branch,"files":len(contents),"zip":str(target)}
        except Exception as exc:
            failures[branch]=type(exc).__name__
    raise RuntimeError("OFFLINE_BACKUP_UNAVAILABLE:"+json.dumps(failures))

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--output",default="tennis-evidence-offline.zip")
    args=cli.parse_args()
    token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    print(json.dumps(export(lambda route:fetch(route,token),args.output)))
if __name__=="__main__":main()
