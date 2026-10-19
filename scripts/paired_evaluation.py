"""Paired, non-promoting Champion vs Challenger evaluation.

Do not compare unpaired tour samples: availability is itself a source of bias.
"""
import math
from collections import defaultdict

ROLES=("champion","challenger","experimental")
def paired(forecasts,outcomes):
    truth={o["fixture_id"]:o for o in outcomes}
    groups=defaultdict(list)
    for f in forecasts:
        o=truth.get(f["fixture_id"])
        if not o or o["winner"] not in ("a","b"):continue
        vals=[]
        for role in ROLES:
            v=f["results"].get(role,{})
            p=v.get("p_a")
            if v.get("status")!="ok" or type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1:break
            vals.append(p)
        else:
            groups[f["tour"]].append((vals, int(o["winner"]=="a")))
    report={}
    for tour, rows in sorted(groups.items()):
        scores={}
        for i,role in enumerate(ROLES):
            ps=[v[i] for v,y in rows]
            ys=[y for v,y in rows]
            scores[role]={"n":len(rows),
                "brier":round(sum((p-y)**2 for p,y in zip(ps,ys))/len(rows),8),
                "log_loss":round(-sum(y*math.log(max(p,1e-15))+(1-y)*math.log(max(1-p,1e-15)) for p,y in zip(ps,ys))/len(rows),8)}
        report[tour]={"paired_fixtures":len(rows),"models":scores}
    return {"status":"research_only","promotion_authorized":False,"paired_by_tour":report}
