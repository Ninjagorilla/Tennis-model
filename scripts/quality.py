"""Read-only fixture identity, coverage diagnostics and Devil's Advocate analysis.

Never fills unavailable probabilities or modifies any model output.
"""
import re,unicodedata
from collections import defaultdict

ALIASES={
 ("WTA","shi han"):"han shi",
 ("WTA","sorana cirstea"):"sorana cirstea",
 ("WTA","catherine mcnally"):"caty mcnally",
}
def normalize(name):
    s=unicodedata.normalize("NFKD",name)
    return re.sub(r"[^a-z0-9]+"," ","".join(c for c in s if not unicodedata.combining(c)).casefold()).strip()
def identity(tour,name):
    k=normalize(name)
    return tour+":"+ALIASES.get((tour,k),k)
def fixture_key(row):
    return (row["tour"],tuple(sorted((identity(row["tour"],row["name_a"]),identity(row["tour"],row["name_b"])))),row["tournament_key"],row["regime"])
def deduplicate(rows):
    """Keep one source row only if key and scheduling facts are unambiguous."""
    groups=defaultdict(list)
    for row in rows:groups[fixture_key(row)].append(row)
    out=[];conflicts=0;duplicates=0
    for group in groups.values():
        if len(group)>1:duplicates+=len(group)-1
        first=group[0]
        if any(any(x[k]!=first[k] for k in ("surface","best_of","deciding_tiebreak_target")) for x in group[1:]):
            conflicts+=1;continue
        # Providers may disagree on estimated start times; never silently pick a
        # fixture if scheduled times differ by more than 90 minutes.
        from datetime import datetime
        dates=[datetime.fromisoformat(x["starts_at"].replace("Z","+00:00")) for x in group]
        if (max(dates)-min(dates)).total_seconds()>5400:
            conflicts+=1;continue
        # Prefer ESPN source when present; keep orientation and IDs intact.
        selected=sorted(group,key=lambda x:(str(x["source_match_id"]).startswith("tc:"),x["source_match_id"]))[0]
        out.append(selected)
    return out,{"duplicates_collapsed":duplicates,"identity_conflicts":conflicts}


def cross_source_opponent_conflicts(rows):
    """Withhold a match if independent providers name different opponents.

    Compare same tour, edition, player, and start within 3 hours.
    Never infer the replacement matchup from one provider.
    """
    from datetime import datetime
    blocked=set()
    for i,a in enumerate(rows):
        for j,b in enumerate(rows[i+1:],i+1):
            pa=str(a.get("source_match_id","")).startswith("tc:")
            pb=str(b.get("source_match_id","")).startswith("tc:")
            if pa==pb or a["tour"]!=b["tour"] or a["tournament_key"]!=b["tournament_key"]:
                continue
            if a["regime"]!=b["regime"]:continue
            ta=datetime.fromisoformat(a["starts_at"].replace("Z","+00:00"))
            tb=datetime.fromisoformat(b["starts_at"].replace("Z","+00:00"))
            if abs((ta-tb).total_seconds())>10800:continue
            aa={identity(a["tour"],a["name_a"]),identity(a["tour"],a["name_b"])}
            bb={identity(b["tour"],b["name_a"]),identity(b["tour"],b["name_b"])}
            if len(aa&bb)==1:
                blocked.update((i,j))
    return [r for k,r in enumerate(rows) if k not in blocked],len(blocked)

def challenge(row):
    """Only interprets three observed model probabilities, never invents one."""
    probs={}
    for role in ("champion","challenger","experimental"):
        r=row["results"][role]
        if r["status"]=="ok":probs[role]=r["p_a"]
    missing=[r for r in ("champion","challenger","experimental") if r not in probs]
    if not probs:return {"status":"unavailable","missing_models":missing,"flags":["NO_MODEL_PROBABILITIES"],"recommendation":"withhold"}
    mean=sum(probs.values())/len(probs)
    side="a" if mean>=.5 else "b"
    pick=row["name_"+side]
    picked=[v if side=="a" else 1-v for v in probs.values()]
    spread=max(picked)-min(picked)
    flags=[]
    if missing:flags.append("INCOMPLETE_MODEL_COVERAGE")
    if any(x<.5 for x in picked):flags.append("MODEL_DISAGREEMENT")
    if spread>=.10:flags.append("HIGH_PROBABILITY_SPREAD")
    if max(mean,1-mean)<.60:flags.append("FRAGILE_FAVORITE")
    if row.get("regime","").endswith("qualifying"):flags.append("QUALIFYING_UNCERTAINTY")
    reasons=[]
    if "MODEL_DISAGREEMENT" in flags:reasons.append("At least one model favors the opponent.")
    if "HIGH_PROBABILITY_SPREAD" in flags:reasons.append("Model probabilities differ by at least 10 percentage points.")
    if "FRAGILE_FAVORITE" in flags:reasons.append("The mean probability is below 60%, so the opponent has substantial modeled upset probability.")
    if missing:reasons.append("One or more models did not return a valid prediction.")
    return {"status":"complete" if not missing else "partial","pick":pick,"side":side,
            "mean_available_probability":round(max(mean,1-mean),6),
            "opponent_probability":round(min(mean,1-mean),6),
            "model_spread_pp":round(100*spread,3),"missing_models":missing,
            "flags":flags,"reasons":reasons,
            "recommendation":"review" if flags else "no_automatic_promotion"}
