"""Automatic, bounded scan retries with fail-closed recovery reporting.

Never alters model artifacts or promotes a cached result to a new live forecast.
"""
import json,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from verify_scan import verify

MAX_ATTEMPTS=2
def evaluate(snapshot, require_available=False):
    errors,details=verify(snapshot,require_available=require_available)
    for m in snapshot.get("models",[]):
        pf=m.get("preflight",{})
        if pf.get("passed")!=4 or pf.get("total")!=4:errors.append("MODEL_PREFLIGHT_FAILED")
    if snapshot.get("prediction_status")=="unavailable" and snapshot.get("matches"):
        errors.append("NO_VALID_MODEL_PREDICTIONS")
    if snapshot.get("prediction_status")=="unavailable":
        sources=snapshot.get("coverage",{}).get("sources",[])
        # No scheduled fixtures is acceptable only with at least one healthy feed.
        if not sources or not any(s.get("status")=="ok" for s in sources):
            errors.append("ALL_FIXTURE_SOURCES_UNAVAILABLE")
    try:
        generated=datetime.fromisoformat(snapshot["generated_at"].replace("Z","+00:00"))
        if generated.tzinfo is None or abs((datetime.now(timezone.utc)-generated).total_seconds())>1200:
            errors.append("INVALID_GENERATION_TIME")
    except (KeyError,ValueError,TypeError):errors.append("INVALID_GENERATION_TIME")
    return sorted(set(errors)),details

def retry(scan,backup,attempts=MAX_ATTEMPTS,pause=lambda _:None):
    """Pure coordinator: testable with injected scan and backup functions."""
    if attempts<1 or attempts>MAX_ATTEMPTS:raise ValueError("UNSAFE_RETRY_COUNT")
    history=[]
    for number in range(1,attempts+1):
        try:
            details=scan()
            history.append({"attempt":number,"outcome":"success","details":details})
            return True,{"status":"live","attempts":history,"backup":None}
        except Exception as exc:
            history.append({"attempt":number,"outcome":"failed","failure_code":
                str(exc)[:80] if str(exc).replace("_","").isalnum() else "SCAN_OR_QUALITY_GATE_FAILED"})
            if number<attempts:pause(number)
    try:selection=backup()
    except Exception:selection={"status":"unavailable","reason":"BACKUP_FETCH_FAILED"}
    # A cached backup is NEVER considered a successful current scan.
    return False,{"status":"degraded","attempts":history,"backup":selection}

def live_scan():
    p=subprocess.run([sys.executable,"scripts/scan.py"],capture_output=True,timeout=660)
    if p.returncode!=0:raise RuntimeError("SCAN_PROCESS_FAILED")
    path=Path("work/snapshot.json")
    if not path.is_file():raise RuntimeError("SNAPSHOT_MISSING")
    snapshot=json.loads(path.read_text(encoding="utf8"))
    errors,details=evaluate(snapshot,require_available=os.getenv("REQUIRE_LIVE_SCAN")=="1")
    if errors:raise RuntimeError("SCAN_QUALITY_FAILED")
    return details

def select_backup():
    p=subprocess.run(["node","scripts/backup_select.mjs"],capture_output=True,timeout=55)
    if p.returncode!=0:raise RuntimeError("BACKUP_SELECTION_FAILED")
    return json.loads(p.stdout.decode("utf8"))

def main():
    ok,report=retry(live_scan,select_backup,pause=lambda _:time.sleep(8))
    out=Path("work/recovery-report.json");out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"status":report["status"],"attempts":len(report["attempts"]),
                      "backup":report["backup"],"live_quality":report["attempts"][-1].get("details")},ensure_ascii=False))
    # On repeated failure, preserve the deployed site and trigger the alert job.
    return 0 if ok else 1
if __name__=="__main__":sys.exit(main())
