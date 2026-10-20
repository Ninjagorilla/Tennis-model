"""Reconcile discovered tournament presence against verified model fixtures."""
from collections import defaultdict
from manual_fixture_review import validate

def reconcile(snapshot,discovery,reviewed=None,now=None):
 counts=defaultdict(int)
 for m in snapshot.get("matches",[]):
  counts[(m.get("tour"),m.get("regime"),m.get("tournament_key"))]+=1
 signals=discovery.get("sources",{})
 coverage={}
 for tournament in ("florence","fort_worth","guangzhou","lisbon","cali"):
  named=[key for key,source in signals.items() if source.get("status")=="fetched_unverified_markup" and source.get("mentions",{}).get(tournament)]
  equivalent={"florence":"florence","fort_worth":"fort worth","guangzhou":"guangzhou","lisbon":"lisboa","cali":"cali"}[tournament]
  predicted=sum(n for (tour,regime,key),n in counts.items() if regime.startswith("challenger") and (equivalent in str(key) or tournament.replace("_"," ") in str(key)))
  coverage[tournament]={"independent_presence_sources":len(named),"sources":named,
    "scored_fixtures":predicted,"status":"GAP_REQUIRES_REVIEW" if named and predicted==0 else "PARTIAL_OR_UNKNOWN"}
 accepted=[];errors=[]
 for i,row in enumerate((reviewed or {}).get("matches",[])):
  try:accepted.append(validate(row,now))
  except (ValueError,KeyError,TypeError) as exc:errors.append({"index":i,"error":str(exc)})
 return {"schema":"tennis-fixture-coverage-v1","tournaments":coverage,
         "reviewed_valid":len(accepted),"reviewed_rejected":errors,
         "complete_all_tours":False,"reason":"Source presence is not exhaustive draw coverage"}
