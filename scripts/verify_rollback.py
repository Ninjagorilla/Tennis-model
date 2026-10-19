"""Verify that a proposed rollback commit retains registered sports model artifacts.

Read-only: this tool never rewrites branches, resets history, or promotes models.
"""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
IMMUTABLE=("engine/manifest.json","engine/native/registration.json","nfl/manifest.json")
def git_read(commit,path,runner=subprocess.run):
    p=runner(["git","show",commit+":"+path],capture_output=True,timeout=15)
    if p.returncode:raise ValueError("ROLLBACK_FILE_NOT_AVAILABLE")
    return p.stdout
def check_rollback(target,current="HEAD",reader=git_read):
    if not re.fullmatch(r"[0-9a-fA-F]{40}",target):return {"approved":False,"reason":"EXPLICIT_FULL_COMMIT_SHA_REQUIRED"}
    diff=[]
    try:
        for path in IMMUTABLE:
            a=reader(target,path);b=reader(current,path)
            if hashlib.sha256(a).digest()!=hashlib.sha256(b).digest():diff.append(path)
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return {"approved":False,"reason":"ROLLBACK_COMMIT_UNVERIFIED"}
    return {"approved":not diff,"reason":"IMMUTABLE_MODEL_FILES_MATCH" if not diff else "MODEL_ARTIFACT_CHANGE_DETECTED",
            "target":target,"checked_files":list(IMMUTABLE),"mismatches":diff}
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--target",required=True)
    args=parser.parse_args()
    report=check_rollback(args.target)
    print(json.dumps(report))
    return 0 if report["approved"] else 1
if __name__=="__main__":sys.exit(main())
