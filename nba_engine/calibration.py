"""Chronological probability calibration and prospective shadow comparisons."""
from math import log,exp

def _sigmoid(x):
    return 1/(1+exp(-max(-35,min(35,x))))

def fit_platt(training,steps=800,rate=.05):
    """Fit intercept and slope on prior labeled games only; no test reuse."""
    if len(training)<50:raise ValueError("Need at least 50 prior outcomes")
    a=0.;b=1.
    for _ in range(steps):
        ga=gb=0.
        for p,y in training:
            if not 0<p<1 or y not in (0,1):raise ValueError("Invalid training")
            x=log(p/(1-p));err=_sigmoid(a+b*x)-y
            ga+=err;gb+=err*x
        a-=rate*ga/len(training)
        b-=rate*gb/len(training)
    return (a,b)

def apply_platt(prob,parameters):
    if not 0<prob<1:raise ValueError("Invalid probability")
    a,b=parameters
    return _sigmoid(a+b*log(prob/(1-prob)))

def rolling_shadow(rows,min_train=100,calibration_window=50):
    """Each row: timestamp, raw_probability, home_won, optional market_probability.
    Fits only earlier results. Reports calibrated model and market benchmarks.
    """
    ordered=sorted(rows,key=lambda r:r["tipoff_utc"])
    if len(ordered)<=min_train or min_train<50 or calibration_window<50:
        raise ValueError("Insufficient chronological history")
    results=[]
    for i in range(min_train,len(ordered)):
        r=ordered[i]
        history=ordered[:i]
        if any(h["tipoff_utc"]>=r["tipoff_utc"] for h in history):
            raise ValueError("Same-time leakage")
        train=[(h["raw_probability"],int(h["home_won"])) for h in history[-calibration_window:]]
        params=fit_platt(train)
        p=apply_platt(r["raw_probability"],params)
        y=int(r["home_won"])
        results.append({"tipoff_utc":r["tipoff_utc"],"calibrated_probability":p,
                        "home_won":y,"brier":(p-y)**2,
                        "market_brier":(r["market_probability"]-y)**2 if r.get("market_probability") is not None else None})
    n=len(results)
    markets=[x["market_brier"] for x in results if x["market_brier"] is not None]
    return {"n":n,"model_brier":sum(x["brier"] for x in results)/n,
            "market_brier":sum(markets)/len(markets) if markets else None,
            "results":results,"status":"BACKTEST_NOT_PROSPECTIVE"}
