"""Point-in-time walk-forward evaluation. No in-sample score claims."""
from math import log

def grade(predictions, outcomes):
    truth={x["game_id"]:x for x in outcomes}
    joined=[]
    for p in predictions:
        o=truth.get(p["game_id"])
        if o is None: continue
        if p["asof_utc"]>p["tipoff_utc"]: raise ValueError("Lookahead detected")
        prob=p["home_win_probability"]
        if not 0<prob<1: raise ValueError("Bad probability")
        y=int(o["home_won"])
        joined.append((prob,y))
    if not joined: raise ValueError("No matched outcomes")
    n=len(joined)
    return {"n":n,"brier":sum((p-y)**2 for p,y in joined)/n,
        "log_loss":-sum(y*log(p)+(1-y)*log(1-p) for p,y in joined)/n,
        "accuracy":sum((p>=0.5)==bool(y) for p,y in joined)/n}

def walk_forward(rows, minimum_train=100):
    """Rows sorted by tipoff, each with game_id, tipoff_utc, asof_utc, probability, home_won.
    Evaluates only later games; caller must fit model using preceding training rows.
    """
    rows=sorted(rows,key=lambda x:x["tipoff_utc"])
    if len(rows)<=minimum_train: raise ValueError("Insufficient future holdout")
    test=rows[minimum_train:]
    return grade([{"game_id":r["game_id"],"tipoff_utc":r["tipoff_utc"],
       "asof_utc":r["asof_utc"],"home_win_probability":r["probability"]} for r in test],test)
