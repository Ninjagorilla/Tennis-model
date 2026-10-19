"""Publish only verified, fresh tennis snapshots; preserve last good on failure."""
import base64
import json
import os
import pathlib
import subprocess
from datetime import datetime, timezone
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from verify_scan import verify

def main():
    snapshot = pathlib.Path("work/snapshot.json")
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    errors, details = verify(data, require_available=True)
    if errors:
        raise SystemExit("Refusing invalid publication: " + ",".join(errors))
    now = datetime.now(timezone.utc)
    expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    if expires <= now:
        raise SystemExit("Refusing expired snapshot")
    if not any(all(m["results"][role]["status"] == "ok" for role in ("champion","challenger","experimental")) for m in data["matches"]):
        print("Warning: no fixture has full three-model coverage", file=sys.stderr)
    repo = os.environ["GH_REPO"]
    target = f"repos/{repo}/contents/public-results/latest.json"
    previous = subprocess.run(["gh","api",target+"?ref=scan-results","--jq",".sha"],capture_output=True,text=True)
    payload = {"message":"Publish independently verified tennis scan "+os.environ.get("GITHUB_RUN_ID","manual"),"branch":"scan-results","content":base64.b64encode(snapshot.read_bytes()).decode("ascii")}
    if previous.returncode == 0 and previous.stdout.strip():
        payload["sha"] = previous.stdout.strip()
    request = pathlib.Path("work/independent-publication.json")
    request.write_text(json.dumps(payload),encoding="utf-8")
    subprocess.run(["gh","api","-X","PUT",target,"--input",str(request)],check=True)
    print("Published verified tennis snapshot:",details["fixture_count"],"fixtures")
if __name__ == "__main__":
    main()
