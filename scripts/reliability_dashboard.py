"""Build a static read-only tennis reliability dashboard from verified local reports.

Missing data is unknown, not success or zero. No model scores are changed.
"""
import argparse
import html
import json
from pathlib import Path

def read(path):
    p=Path(path)
    if not p.is_file():return None
    try:return json.loads(p.read_text())
    except (ValueError,OSError):return None

def summarize(snapshot,quality,archive,recovery,settlement,scan_recovery,audit=None):
    models={}
    for m in (snapshot or {}).get("models",[]):
        if m.get("id") in ("champion","challenger","experimental"):
            models[m["id"]]=m.get("predictions")
    matches=(snapshot or {}).get("matches")
    if not isinstance(matches,list):matches=None
    triple=sum(all(x.get("results",{}).get(role,{}).get("status")=="ok" for role in ("champion","challenger","experimental")) for x in matches) if matches is not None else None
    source_health=None;verified=None;excluded=None
    if isinstance(settlement,dict) and "health" in settlement:
        health=settlement.get("health",[])
        source_health={"healthy":sum(h.get("status")=="ok" for h in health),"checked":len(health)}
        verified=len(settlement.get("settlements",[]))
        excluded=len(settlement.get("exclusions",{}))
    return {"generated_at":(snapshot or {}).get("generated_at"),
            "scan_status":(snapshot or {}).get("prediction_status","unknown"),
            "fixtures":len(matches) if matches is not None else None,
            "three_model_coverage":triple,
            "model_predictions":models,
            "scan_recovery":(scan_recovery or {}).get("status","not_recorded"),
            "archive_status":"verified" if archive and archive.get("remote_verified") else "not_verified",
            "archive_mirrors":(recovery or {}).get("verified"),
            "archive_recovery_status":(recovery or {}).get("status","not_checked"),
            "provider_health":source_health,
            "verified_settlements":verified,
            "excluded_settlements":excluded,
            "prospective_accuracy":(audit or {}).get("model_metrics_by_tour","not_established"),
            "verified_forecasts_graded":(audit or {}).get("two_source_verified"),
            "paired_three_model_metrics":(audit or {}).get("paired","not_established"),
            "champion_promoted":False}

def render(data):
    def field(v):
        if v is None:return "Not checked"
        if isinstance(v,(dict,list)):v=json.dumps(v,sort_keys=True)
        return html.escape(str(v),quote=True)
    labels=[("Scan status","scan_status"),("Fixtures","fixtures"),
            ("Three-model fixtures","three_model_coverage"),
            ("Predictions by model","model_predictions"),
            ("Scan recovery","scan_recovery"),
            ("Forecast archive","archive_status"),
            ("Verified archive branches","archive_mirrors"),
            ("Archive recovery","archive_recovery_status"),
            ("Result provider requests","provider_health"),
            ("Verified settlements this run","verified_settlements"),
            ("Quarantined settlements this run","excluded_settlements"),
            ("Prospective accuracy","prospective_accuracy"),
            ("Two-source graded fixtures","verified_forecasts_graded"),
            ("Paired three-model results","paired_three_model_metrics")]
    rows="\n".join("<tr><th>"+html.escape(label)+"</th><td>"+field(data.get(key))+"</td></tr>" for label,key in labels)
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Tennis Model Reliability</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font:16px system-ui;max-width:860px;margin:40px auto;padding:0 18px;color:#202b38;background:#fafbfc}
h1{font-size:1.8rem}table{border-collapse:collapse;width:100%;background:white}
th,td{border-bottom:1px solid #ddd;text-align:left;padding:12px;vertical-align:top;overflow-wrap:anywhere}
th{width:45%}p{line-height:1.5}.muted{color:#596579}</style>
<h1>Tennis model reliability</h1><p>Read-only diagnostics. Missing values mean not checked, not zero.
No prediction or Champion promotion is authorized by this page.</p>
<table>"""+rows+"""</table><p class="muted">These are current-run diagnostics, not a 7-day success rate.
Historical performance requires independently settled prospective fixtures.</p></html>"""

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--output",default="dist/reliability.html")
    cli.add_argument("--json-output",default="work/reliability-dashboard.json")
    args=cli.parse_args()
    result=summarize(read("work/snapshot.json"),read("work/scan-quality.json"),
        read("work/evidence-archive-report.json"),read("work/evidence-recovery-health.json"),
        read("work/settlement-observations.json"),read("work/recovery-report.json"),
        read("work/tennis-grading-audit.json"))
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(render(result),encoding="utf8")
    dest=Path(args.json_output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
if __name__=="__main__":main()
