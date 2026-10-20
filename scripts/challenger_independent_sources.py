"""Independent Challenger discovery probe; never silently creates model fixtures.

Official ATP schedule + TennisTemple + Tennis Explorer. HTTP failure and
markup/schema changes are explicit. Third-party pages are discovery signals,
NOT sufficient to authorize a predicted matchup or a claimed live schedule.
"""
import hashlib,json,re,urllib.request
from datetime import datetime,timezone,timedelta
from html.parser import HTMLParser

def sources_for(day):
 return {"official_atp":"https://www.atptour.com/en/scores/current-challenger/",
 "tennistemple":f"https://en.tennistemple.com/matches/{day:%Y-%m-%d}",
 "tennisexplorer":f"https://www.tennisexplorer.com/matches/?day={day.day}&month={day.month}&type=all&year={day.year}"}
SOURCES=sources_for(datetime.now(timezone.utc).date())
TOURNAMENTS={
 "florence":("Florence","Firenze"),
 "fort_worth":("Fort Worth",),
 "guangzhou":("Guangzhou",),
 "lisbon":("Lisbon","Lisboa"),
 "cali":("Cali",)
}
class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ("style","script"):self.skip+=1
 def handle_endtag(self,tag):
  if tag in ("style","script"):self.skip=max(0,self.skip-1)
 def handle_data(self,data):
  if not self.skip:self.parts.append(data)

def probe(reader=None,*,observed_at=None,day=None):
 at=observed_at or datetime.now(timezone.utc).isoformat()
 requested=day or datetime.fromisoformat(at.replace('Z','+00:00')).date()
 urls=sources_for(requested)
 out={}
 for source,url in urls.items():
  try:
   if reader:
    raw=reader(url)
   else:
    req=urllib.request.Request(url,headers={"User-Agent":"Courtside-Research-Discovery/0.1"})
    with urllib.request.urlopen(req,timeout=12) as response:
     if response.url.split("?")[0]!=url.split("?")[0]:raise ValueError("REDIRECTED_SOURCE")
     raw=response.read(1500001)
   if not isinstance(raw,bytes) or len(raw)>1500000:raise ValueError("INVALID_SOURCE_BODY")
   doc=Text();doc.feed(raw.decode("utf-8"))
   page=" ".join(doc.parts)
   # Keyword detection is for independent tournament PRESENCE only.
   # It does not prove the date, specific opponent or future status.
   appearances={key:any(re.search(r"(?<![a-z])"+re.escape(term)+r"(?![a-z])",page,re.I) for term in names)
                for key,names in TOURNAMENTS.items()}
   out[source]={"status":"fetched_unverified_markup","url":url,"observed_at":at,
                "sha256":hashlib.sha256(raw).hexdigest(),"mentions":appearances,
                "match_predictions_eligible":False}
  except (ValueError,TypeError,OSError,UnicodeError,TimeoutError) as exc:
   out[source]={"status":"unavailable","url":url,"reason":type(exc).__name__,
                "match_predictions_eligible":False}
 return {"schema":"challenger-independent-source-probe-0.1",
         "data_kind":"DISCOVERY_SIGNAL_ONLY","sources":out,
         "confirmed_live_fixtures":[],"probabilities_modified":False,
         "limitations":["Keyword matches do not establish actual court dates or opponent identities",
                        "Do not promote third-party discovery into forecasts without exact match verification",
                        "Official ATP pages may render schedule data client-side"]}

if __name__=="__main__":
 import argparse
 from pathlib import Path
 p=argparse.ArgumentParser();p.add_argument("--output",default="work/challenger-source-probe.json");p.add_argument("--date",default=None)
 a=p.parse_args();result=probe(day=datetime.fromisoformat(a.date).date() if a.date else None);path=Path(a.output);path.parent.mkdir(exist_ok=True,parents=True)
 path.write_text(json.dumps(result,indent=2)+"\n")
 print(json.dumps({"status":"DISCOVERY_ONLY",
  "available_sources":sum(s["status"]=="fetched_unverified_markup" for s in result["sources"].values()),
  "sources_checked":3,"probabilities_modified":False}))
