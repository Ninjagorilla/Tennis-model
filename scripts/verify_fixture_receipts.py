"""Re-fetch evidence receipts before any manual fixture is scored.

A reviewer-provided hash or confirmation flag alone is not evidence.
"""
import hashlib,re,urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse
from manual_fixture_review import timestamp,HOSTS
from quality import normalize
class Visible(HTMLParser):
 def __init__(self):super().__init__();self.words=[];self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ("script","style"):self.skip+=1
 def handle_endtag(self,tag):
  if tag in ("script","style"):self.skip=max(0,self.skip-1)
 def handle_data(self,data):
  if not self.skip:self.words.append(data)
def retrieve(url):
 req=urllib.request.Request(url,headers={"User-Agent":"Courtside-Independent-Fixture-Verification/1.0"})
 with urllib.request.urlopen(req,timeout=12) as response:
  dest=urlparse(response.geturl())
  if dest.scheme!="https" or dest.hostname!=urlparse(url).hostname:raise ValueError("UNEXPECTED_REDIRECT")
  data=response.read(1000001)
 if len(data)>1000000:raise ValueError("OVERSIZE_RECEIPT")
 return data
def verify_receipts(row,fetch=retrieve):
 for receipt in row["independent_receipts"]:
  url=receipt["url"];host=urlparse(url).hostname
  if host not in HOSTS:raise ValueError("UNAPPROVED_SOURCE")
  raw=fetch(url)
  if hashlib.sha256(raw).hexdigest()!=receipt["sha256"]:raise ValueError("SOURCE_CONTENT_CHANGED")
  page=Visible();page.feed(raw.decode("utf8"));body=normalize(" ".join(page.words))
  for field in ("name_a","name_b"):
   name=normalize(row[field])
   if not re.search(r"(?<![a-z0-9])"+re.escape(name)+r"(?![a-z0-9])",body):
    raise ValueError("PLAYER_ABSENT_FROM_SOURCE")
 return True
