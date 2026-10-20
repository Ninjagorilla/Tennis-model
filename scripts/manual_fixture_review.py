"""Review manually discovered tennis fixtures before isolated inference."""
from datetime import datetime,timezone
from urllib.parse import urlparse
import re
from quality import normalize
HOSTS={"www.atptour.com","www.wtatennis.com","www.tennis.com","en.tennistemple.com","www.tennisexplorer.com"}
def timestamp(value):
 d=datetime.fromisoformat(value.replace("Z","+00:00"))
 if d.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
 return d.astimezone(timezone.utc)
def validate(row,now):
 now=timestamp(now)
 if row.get("tour") not in ("ATP","WTA"):raise ValueError("INVALID_TOUR")
 if row.get("regime") not in ("main","challenger","wta125","main_qualifying","challenger_qualifying","wta125_qualifying"):raise ValueError("INVALID_REGIME")
 if row.get("surface") not in ("Hard","Clay","Grass"):raise ValueError("UNKNOWN_SURFACE")
 if row.get("best_of")!=3 or row.get("deciding_tiebreak_target")!=7:raise ValueError("UNKNOWN_FORMAT")
 if timestamp(row["starts_at"])<=now:raise ValueError("MATCH_STARTED")
 if not row.get("tournament_key") or not row.get("source_match_id"):raise ValueError("UNKNOWN_FIXTURE")
 names=[normalize(row.get("name_a","")),normalize(row.get("name_b",""))]
 if len(set(names))!=2 or any(len(n)<3 for n in names):raise ValueError("AMBIGUOUS_PLAYERS")
 receipts=row.get("independent_receipts",[])
 if len(receipts)<2:raise ValueError("MISSING_SECOND_SOURCE")
 hosts=set()
 for item in receipts:
  u=urlparse(item.get("url",""))
  if u.scheme!="https" or u.hostname not in HOSTS:raise ValueError("UNAPPROVED_SOURCE")
  if not re.fullmatch("[0-9a-f]{64}",item.get("sha256","")):raise ValueError("SOURCE_HASH_MISSING")
  if timestamp(item["fetched_at"])>now:raise ValueError("FUTURE_RECEIPT")
  if item.get("fixture_and_surface_confirmed") is not True:raise ValueError("FACTS_UNVERIFIED")
  hosts.add(u.hostname)
 if len(hosts)<2:raise ValueError("NONINDEPENDENT_SOURCES")
 fields=("source_match_id","tour","regime","tournament_key","surface","name_a","name_b","starts_at","best_of","deciding_tiebreak_target")
 output={k:row[k] for k in fields}
 output.update(player_a=row["tour"]+":"+names[0],player_b=row["tour"]+":"+names[1])
 return output
