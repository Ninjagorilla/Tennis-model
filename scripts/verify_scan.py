"""Fail-closed quality gates for staged scans; does not modify predictions."""
import argparse,json,sys,math
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from quality import fixture_key,challenge
from fixture_ledger import publisher, window, TOURS

ROLES=("champion","challenger","experimental")
def verify(snapshot,require_available=False):
    errors=[]
    if snapshot.get("schema_version")!=2:errors.append("SCHEMA_VERSION")
    models={m.get("id"):m for m in snapshot.get("models",[])}
    if set(models)!=set(ROLES):errors.append("MODEL_REGISTRY")
    matches=snapshot.get("matches",[])
    if not isinstance(matches,list):return ["MATCHES_NOT_LIST"],{}
    ids=set()
    for e in matches:
        try:
            key=fixture_key(e)
            if key in ids:errors.append("DUPLICATE_FIXTURE")
            ids.add(key)
            datetime.fromisoformat(e["starts_at"].replace("Z","+00:00"))
            for role in ROLES:
                r=e["results"][role]
                if r["status"]=="ok":
                    p=r["p_a"];q=r["p_b"]
                    if not(type(p) in (int,float) and math.isfinite(p) and 0<=p<=1 and
                           type(q) in (int,float) and math.isfinite(q) and 0<=q<=1 and abs(p+q-1)<1e-9):
                        errors.append("INVALID_PROBABILITY")
                elif r["status"]!="unavailable":errors.append("INVALID_MODEL_STATUS")
            actual=e.get("devils_advocate")
            if actual is not None and actual!=challenge(e):errors.append("CHALLENGER_MISMATCH")
        except (KeyError,ValueError,TypeError):errors.append("MALFORMED_FIXTURE")
    count={role:sum(e.get("results",{}).get(role,{}).get("status")=="ok" for e in matches) for role in ROLES}
    for role in ROLES:
        if role in models and count[role]!=models[role].get("predictions"):errors.append("MODEL_COUNT_MISMATCH")
    status=snapshot.get("prediction_status")
    any_ok=any(count.values())
    if status not in ("available","unavailable","blocked"):errors.append("INVALID_SCAN_STATUS")
    if (status=="available")!=any_ok:errors.append("STATUS_MISMATCH")
    if require_available and status!="available":errors.append("NO_AVAILABLE_SCAN")
    if status=="blocked":errors.append("BLOCKED_SCAN")
    coverage=snapshot.get("coverage",{})
    if not isinstance(coverage,dict):
        errors.append("MALFORMED_COVERAGE")
        coverage={}
    manual=coverage.get("manual_challenger",{})
    if isinstance(manual,dict) and manual.get("rejected",0):
        errors.append("REJECTED_MANUAL_CHALLENGER_FIXTURES")
    if snapshot.get("prediction_status")=="available" and not matches:
        errors.append("AVAILABLE_WITHOUT_FIXTURES")
    if coverage.get('status') not in ('COMPLETE','PARTIAL'):
        errors.append('FAILED_OR_MISSING_LEDGER_GATE')
    if status=='available':
        try:
            if coverage['status'] not in ('COMPLETE','PARTIAL') or snapshot.get('scan_status')!=coverage['status']:
                raise ValueError('INVALID_COVERAGE_STATUS')
            expected=window(coverage['window']['start_date'],coverage['window']['days'])
            if coverage['window']!=expected or coverage['count_tolerance']!=0:
                raise ValueError('INVALID_COVERAGE_WINDOW')
            required={(tour,day) for day in expected['utc_dates'] for tour in TOURS}
            counts=coverage['counts']
            if len(counts)!=len(required) or {(r['tour'],r['utc_date']) for r in counts}!=required:
                raise ValueError('MISSING_TOUR_DATE_COUNTS')
            for row in counts:
                values=list(row['source_counts'].values())
                if any(n is not None and (type(n) is not int or n<0) for n in values):
                    raise ValueError('INVALID_SOURCE_COUNTS')
                if coverage['status']=='COMPLETE' and (row['status']!='COMPLETE' or len([n for n in values if n is not None])<2 or len(set(n for n in values if n is not None))!=1 or row['verified_count']!=max(n for n in values if n is not None)):
                    raise ValueError('FALSE_COMPLETE_COVERAGE')
            if coverage['status']=='PARTIAL' and not coverage['reasons']:
                raise ValueError('PARTIAL_REASON_REQUIRED')
            for match in matches:
                evidence=match['verification']
                providers={publisher(url) for url in evidence['source_urls']}
                if len(providers)<2 or providers!=set(evidence['providers']):
                    raise ValueError('TWO_INDEPENDENT_SOURCES_REQUIRED')
        except (KeyError,ValueError,TypeError,AttributeError) as exc:
            errors.append('UNVERIFIED_LEDGER_COVERAGE:'+str(exc))
    details={
        "status":status,"fixture_count":len(matches),"model_predictions":count,
        "scan_status":coverage.get('status','FAILED'),"coverage_reasons":coverage.get('reasons',[]),
        "counts":coverage.get('counts',[]),
        "three_model_coverage":sum(all(e.get("results",{}).get(r,{}).get("status")=="ok" for r in ROLES) for e in matches),
        "devils_advocate_reviews":sum(e.get("devils_advocate",{}).get("recommendation")=="review" for e in matches),
        "identity_diagnostics":coverage.get("identity_diagnostics",{}),
        "missing_model_reasons":coverage.get("model_missing_reasons",{}),
        "generated_at":snapshot.get("generated_at"),
        "run_id":snapshot.get("build",{}).get("run_id")
    }
    return sorted(set(errors)),details
def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("snapshot",nargs="?",default="work/snapshot.json")
    cli.add_argument("--require-available",action="store_true")
    cli.add_argument("--output",default="work/scan-quality.json")
    args=cli.parse_args()
    d=json.loads(Path(args.snapshot).read_text(encoding="utf8"))
    errors,details=verify(d,args.require_available)
    details["errors"]=errors
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(details,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps(details,ensure_ascii=False))
    if errors:sys.exit(1)
if __name__=="__main__":main()
