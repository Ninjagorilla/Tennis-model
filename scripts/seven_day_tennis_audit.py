"""Seven-day *prospective*, deduplicated tennis research audit.

Read-only: immutable forecast receipts and independent result receipts.
No imputed outcomes, no market-upset claims without pre-match market odds,
no Champion promotion. Both GitHub branches are the same hosting failure domain.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path
from gh_evidence import GitHub,BRANCHES
from retrieve_evidence import historical_records
from result_reconciliation import grade
from paired_evaluation import paired,ROLES
from settlement_health import has_two_valid_sources

def when(value):
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError("NAIVE_TIME")
    return d.astimezone(timezone.utc)

def verified_results(client,now=None,days=7,max_files=100):
    now=now or datetime.now(timezone.utc)
    all_paths=set(); listings={}; failures={}
    for branch in BRANCHES:
        try:
            tree=client.api("GET","/git/trees/"+branch+"?recursive=1")
            if not tree or tree.get("truncated") or not isinstance(tree.get("tree"),list):
                raise RuntimeError("INVALID_EVIDENCE_TREE")
            paths=set()
            for item in tree["tree"]:
                path=item.get("path","")
                if item.get("type")!="blob" or not path.startswith("evidence/results/") or not path.endswith(".json"):
                    continue
                parts=path.split("/")
                if len(parts)!=7:continue
                try:day=datetime.strptime("/".join(parts[2:5]),"%Y/%m/%d").replace(tzinfo=timezone.utc)
                except ValueError:continue
                if now-timedelta(days=days+1)<=day<=now:paths.add(path)
            listings[branch]=paths
            all_paths.update(paths)
        except Exception as exc:failures[branch]=type(exc).__name__
    if not listings:raise RuntimeError("ALL_RESULT_TREES_FAILED:"+json.dumps(failures))
    if len(all_paths)>max_files:raise RuntimeError("RESULT_FILE_CAP")
    receipts=[];sources=Counter()
    for path in sorted(all_paths):
        found=False
        for branch in BRANCHES:
            if path not in listings.get(branch,set()):continue
            try:
                obj=client.api("GET","/contents/"+path+"?ref="+branch)
                if not obj or obj.get("encoding")!="base64":raise RuntimeError("RESULT_READ_FAILED")
                raw=base64.b64decode(obj["content"].replace("\n",""),validate=True)
                if hashlib.sha256(raw).hexdigest()!=path.rsplit("/",1)[-1][:-5]:
                    raise RuntimeError("RESULT_DIGEST_MISMATCH")
                doc=json.loads(raw)
                if doc.get("schema_version")!=1 or not isinstance(doc.get("settlements"),list):
                    raise RuntimeError("RESULT_SCHEMA_INVALID")
                receipts.append(doc);sources[branch]+=1;found=True;break
            except Exception:continue
        if not found:raise RuntimeError("UNVERIFIABLE_RESULT_RECEIPT:"+path)
    return {"source":"sha_verified_union","receipts":receipts,
            "files_verified":len(receipts),"branch_reads":dict(sources)}

def build(forecasts,receipts,now=None,days=7):
    now=now or datetime.now(timezone.utc)
    cutoff=now-timedelta(days=days)
    selected={}
    for f in forecasts:
        try:
            start=when(f["starts_at"])
            if not cutoff<=start<=now:continue
            key=f["fixture_id"]
            if key not in selected or when(f["issued_at"])<when(selected[key]["issued_at"]):
                selected[key]=f
        except (KeyError,ValueError,TypeError):continue
    settled={};conflicts=set();excluded={};source_diagnostics={}
    for receipt in receipts:
        for fixture,details in receipt.get("exclusion_details",{}).items():
            if fixture not in source_diagnostics:source_diagnostics[fixture]=details
        for fixture,reason in receipt.get("exclusions",{}).items():
            if fixture not in excluded:excluded[fixture]=reason
        for o in receipt["settlements"]:
            key=o.get("fixture_id")
            if key not in selected:continue
            if not has_two_valid_sources(o):
                conflicts.add(key);continue
            old=settled.get(key)
            if old is not None and (old.get("winner")!=o.get("winner") or old.get("tour")!=o.get("tour")):
                conflicts.add(key)
            elif old is None:settled[key]=o
    for key in conflicts:settled.pop(key,None)
    research=grade(list(selected.values()),list(settled.values()))
    # Reconciliation may reject an apparently two-source outcome on time/identity.
    verified_ids={f["fixture_id"] for f in selected.values()}-set(research["reconciliation"]["rejected"])
    accepted=[settled[k] for k in verified_ids if k in settled]
    counts=Counter()
    diagnostics={}
    for key,f in selected.items():
        if key in verified_ids:continue
        reason=("CONFLICTING_ARCHIVED_RESULTS" if key in conflicts else
                research["reconciliation"]["rejected"].get(key) or
                excluded.get(key) or "AWAITING_INDEPENDENT_RESULT")
        counts[reason]+=1
        diagnostics[key]={"tour":f["tour"],"name_a":f["name_a"],"name_b":f["name_b"],
                          "starts_at":f["starts_at"],"reason":reason,
                          "source_exclusion":excluded.get(key),
                          "source_diagnostics":source_diagnostics.get(key)}
    daily={}
    for f in selected.values():
        day=when(f["starts_at"]).date().isoformat()
        row=daily.setdefault(day,{"forecast_fixtures":0,"verified_settlements":0,"unresolved":0})
        row["forecast_fixtures"]+=1
        if f["fixture_id"] in verified_ids:row["verified_settlements"]+=1
        else:row["unresolved"]+=1
    # Paired model comparison on exactly the same verified fixtures.
    paired_scores=paired(list(selected.values()),accepted)
    per_role={}
    truth={o["fixture_id"]:o for o in accepted}
    for role in ROLES:
        valid=correct=0
        for key,o in truth.items():
            p=selected[key].get("results",{}).get(role,{})
            prob=p.get("p_a")
            if p.get("status")!="ok" or type(prob) not in (int,float) or not math.isfinite(prob) or not 0<=prob<=1 or prob==0.5:continue
            valid+=1
            correct+=int(("a" if prob>0.5 else "b")==o["winner"])
        per_role[role]={"graded_decisions":valid,"correct":correct,
                        "accuracy":round(correct/valid,6) if valid else None,
                        "market_upsets_correct":None,
                        "market_upsets_reason":"NO_ARCHIVED_POINT_IN_TIME_MARKET_ODDS"}
    return {"schema_version":1,"window_days":days,"window_start":cutoff.isoformat(),
            "window_end":now.isoformat(),"forecast_fixtures":len(selected),
            "verified_settlements":len(accepted),"unresolved":len(selected)-len(accepted),
            "result_conflicts_quarantined":len(conflicts),
            "daily":dict(sorted(daily.items())),"exclusion_reasons":dict(sorted(counts.items())),
            "exclusion_details":diagnostics,"metrics_by_tour":research["metrics_by_tour"],
            "paired":paired_scores,"model_decisions":per_role,
            "status":"verified_results" if accepted else "awaiting_verified_results",
            "promotion_authorized":False,"champion_frozen":True,
            "research_only":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",default="work/seven-day-tennis-audit.json")
    args=p.parse_args()
    client=GitHub(os.environ["GITHUB_REPOSITORY"],os.environ["GH_TOKEN"])
    now=datetime.now(timezone.utc)
    f=historical_records(client,now=now,days=7)
    r=verified_results(client,now=now,days=7)
    result=build(f["forecasts"],r["receipts"],now=now)
    result["forecast_archive_branch"]=f["source"]
    result["result_archive_branch"]=r["source"]
    result["result_receipts_verified"]=r["files_verified"]
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("exclusion_details","paired","metrics_by_tour","daily","model_decisions")}))
if __name__=="__main__":main()
