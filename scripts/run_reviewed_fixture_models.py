"""Isolated scoring of reviewed matches using registered three-model workers."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from manual_fixture_review import validate
from inference import execute,preflight,ROLES
from runtime import stage
from scan import project
from quality import challenge

def run(manifest,root=Path("work/runtime"),directory=Path("work/manual-scan"),now=None):
 now=now or datetime.now(timezone.utc).isoformat()
 rows=manifest.get("matches",[])
 if not rows:raise ValueError("NO_REVIEWED_FIXTURES")
 events=[validate(row,now) for row in rows]
 ids=[(e["tour"],e["tournament_key"],tuple(sorted((e["player_a"],e["player_b"])))) for e in events]
 if len(ids)!=len(set(ids)):raise ValueError("DUPLICATE_FIXTURES")
 root=root.resolve()
 directory.mkdir(parents=True,exist_ok=True)
 stage(root)
 checks=preflight(root,directory/"preflight")
 if any(checks[k]["passed"]!=checks[k]["total"] for k in ROLES):raise ValueError("MODEL_PREFLIGHT_FAILED")
 outputs=execute(root,events,now[:10],directory/"workers")
 results=[]
 for i,event in enumerate(events):
  scores={role:project(outputs.get(role,{}).get(i)) for role in ROLES}
  results.append({**event,"results":scores,"devils_advocate":challenge({**event,"results":scores}),"research_only":True})
 return {"schema_version":1,"status":"MANUAL_RESEARCH_ONLY","generated_at":now,"matches":results,
         "models_unchanged":True,"production_publish":False}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("reviewed_manifest")
 p.add_argument("--output",default="work/manual-scored.json")
 a=p.parse_args()
 output=run(json.loads(Path(a.reviewed_manifest).read_text()))
 path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
 print(json.dumps({"status":output["status"],"count":len(output["matches"]),
 "three_model_coverage":sum(all(m["results"][k]["status"]=="ok" for k in ROLES) for m in output["matches"])}))
if __name__=="__main__":main()
