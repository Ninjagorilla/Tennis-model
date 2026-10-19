"""Generate isolated V2 readiness and shadow diagnostics from real published scans.

No unsupported traits, weather or injuries are invented from fixtures.
An optional verified evidence bundle may be supplied by a future trusted adapter.
"""
import argparse,json
from pathlib import Path
from matchup_intelligence_v2 import shadow

def report(snapshot,features=None):
    features=features or {}
    result=[]
    for match in snapshot.get("matches",[]):
        experimental=match.get("results",{}).get("experimental",{})
        if experimental.get("status")!="ok":continue
        identity=match.get("source_match_id")
        if not identity or not match.get("starts_at"):continue
        data=features.get(identity,{})
        r=shadow(experimental["p_a"],match["starts_at"],identity,data)
        r.update({"match_id":identity,"tour":match["tour"],"regime":match["regime"],
                  "name_a":match["name_a"],"name_b":match["name_b"],
                  "surface":match["surface"],"starts_at":match["starts_at"],
                  "baseline_experimental_model":experimental["model_id"],
                  "baseline_artifact_sha256":experimental["artifact_sha256"]})
        result.append(r)
    return {"schema_version":1,"experimental_registered_unchanged":True,
            "readiness_only":True,"generated_from":snapshot.get("generated_at"),
            "scanned":len(result),"matches":result}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("snapshot")
    p.add_argument("--evidence",help="Optional separately verified point-in-time feature bundle")
    p.add_argument("--output",default="work/matchup-v2-shadow.json")
    args=p.parse_args()
    snapshot=json.loads(Path(args.snapshot).read_text())
    features=json.loads(Path(args.evidence).read_text()) if args.evidence else {}
    doc=report(snapshot,features)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(doc,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"scanned":doc["scanned"],"mode":"SHADOW_READINESS_ONLY",
                      "verified_feature_count":sum(len(r["verified_features"]) for r in doc["matches"])}))
if __name__=="__main__":main()
