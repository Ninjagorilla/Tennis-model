"""Auditable blend-fit and forward evaluation on precomputed WALK-FORWARD predictions.

The input must be produced independently from frozen source model vintages.
This script does not generate or authenticate historical predictions itself.
Usage:
 python scripts/reproducible_blend.py oof.csv receipt.json
Columns: fixture_id,tour,played_at,observed_at,y,p_elo,p_sr,vintage_sha256
Periods: 2023-2024 fit, 2025 validate temperature, 2026 forward test.
The 2026 results are never consulted during fitting or calibration.
"""
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def clip(p):
    return min(1-1e-8,max(1e-8,float(p)))


def loss(rows, predictor):
    if not rows:
        raise ValueError("EMPTY_EVALUATION_WINDOW")
    brier = logloss = 0.
    for row in rows:
        p = clip(predictor(row))
        y = row["y"]
        brier += (p-y)**2
        logloss -= y*math.log(p)+(1-y)*math.log1p(-p)
    return {"n": len(rows), "brier": brier/len(rows),
            "log_loss":logloss/len(rows)}


def temperature(p,t):
    p=clip(p)
    return 1/(1+math.exp(-math.log(p/(1-p))/t))


def evaluate(source_path):
    raw=Path(source_path).read_bytes()
    records=list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    if not records: raise ValueError("NO_ROWS")
    required={"fixture_id","tour","played_at","observed_at","y","p_elo","p_sr","vintage_sha256"}
    if not required <= set(records[0]):
        raise ValueError("REQUIRED_COLUMNS_MISSING")
    seen=set()
    tours=defaultdict(lambda:defaultdict(list))
    for r in records:
        key=(r["tour"],r["fixture_id"])
        if key in seen:raise ValueError("DUPLICATE_FIXTURE")
        seen.add(key)
        if r["tour"] not in ("ATP","WTA"):raise ValueError("INVALID_TOUR")
        if not r["vintage_sha256"] or len(r["vintage_sha256"])!=64 or any(c not in "0123456789abcdef" for c in r["vintage_sha256"]):
            raise ValueError("UNVERIFIED_VINTAGE_REFERENCE")
        if r["played_at"][:10] <= r["observed_at"][:10]:
            raise ValueError("PREDICTION_NOT_PRIOR_DAY")
        year=int(r["played_at"][:4])
        period="fit" if year in (2023,2024) else "calibrate" if year==2025 else "test" if year==2026 else None
        if period is None:raise ValueError("OUTSIDE_PREREGISTERED_PERIOD")
        if r["y"] not in ("0","1"):raise ValueError("INVALID_LABEL")
        r["y"]=int(r["y"])
        for col in ("p_elo","p_sr"):
            val=float(r[col])
            if not math.isfinite(val) or not 0<val<1:raise ValueError("INVALID_PROBABILITY")
            r[col]=val
        tours[r["tour"]][period].append(r)
    report={"schema":"independent-blend-evaluation-v1","input_sha256":digest(raw),
            "periods":{"fit":"2023-2024","calibrate":"2025","test":"2026"},
            "leakage_status":"WINDOW_DISJOINT_ONLY; SOURCE VINTAGES REQUIRE INDEPENDENT AUDIT",
            "tours":{}}
    for tour,groups in tours.items():
        for period in ("fit","calibrate","test"):
            if not groups[period]:raise ValueError("MISSING_WINDOW:"+tour+":"+period)
        fit,cal,test=(groups[k] for k in ("fit","calibrate","test"))
        # Constrained convex blend, selected exclusively on 2023-24 OOF rows.
        blend=lambda r,w: w*r["p_elo"]+(1-w)*r["p_sr"]
        weights=[i/100 for i in range(101)]
        w=min(weights,key=lambda value:loss(fit,lambda r:blend(r,value))["log_loss"])
        # Validation-only temperature: never calibrated on 2026 forward labels.
        temps=[.50+i*.05 for i in range(61)]
        t=min(temps,key=lambda temp:loss(cal,lambda r:temperature(blend(r,w),temp))["log_loss"])
        report["tours"][tour]={"blend_elo_weight":w,"temperature":t,
            "vintages":sorted(set(r["vintage_sha256"] for r in fit+cal+test)),
            "fit":loss(fit,lambda r:blend(r,w)),
            "calibration":loss(cal,lambda r:temperature(blend(r,w),t)),
            "test":{
                "blend":loss(test,lambda r:temperature(blend(r,w),t)),
                "elo":loss(test,lambda r:r["p_elo"]),
                "serve_return":loss(test,lambda r:r["p_sr"])},
            "promotion_authorized":False}
    return report


if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("usage: reproducible_blend.py predictions.csv receipt.json")
    report=evaluate(sys.argv[1])
    output=Path(sys.argv[2])
    if output.exists():raise ValueError("DO_NOT_OVERWRITE_EXISTING_RECEIPT")
    output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"receipt":str(output),"input_sha256":report["input_sha256"],
                      "promotion_authorized":False}))
