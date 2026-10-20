"""Authenticated NBA Stat API adapter with bounded retries and explicit fail-closed behavior."""
import json, os, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone

class ProviderError(RuntimeError): pass

class NBAStatProvider:
    def __init__(self, token=None, opener=None, retries=2, base_url="https://nbastat.io/api/v1"):
        self.token=token or os.environ.get("NBASTAT_API_TOKEN")
        if not self.token: raise ProviderError("NBASTAT_API_TOKEN required; no fallback to fabricated data")
        self.opener=opener or urlopen
        self.retries=min(max(0,retries),3)
        self.base_url=base_url.rstrip("/")
    def get(self,path):
        if not path.startswith("/") or "://" in path or ".." in path:
            raise ValueError("Unsafe API path")
        req=Request(self.base_url+path,headers={"Authorization":"Bearer "+self.token,"Accept":"application/json"})
        for attempt in range(self.retries+1):
            try:
                with self.opener(req,timeout=12) as r:
                    data=json.load(r)
                return {"provider":"nbastat.io","retrieved_at_utc":datetime.now(timezone.utc).isoformat(),"data":data}
            except HTTPError as e:
                if e.code not in (429,500,502,503,504) or attempt==self.retries:
                    raise ProviderError("Provider HTTP failure: "+str(e.code)) from e
            except (URLError,TimeoutError,ValueError) as e:
                if attempt==self.retries: raise ProviderError("Provider unavailable or invalid JSON") from e
            time.sleep(min(2**attempt,4))
        raise ProviderError("Retries exhausted")
    def games(self,start,end):
        from datetime import date
        if date.fromisoformat(end)<date.fromisoformat(start): raise ValueError("Invalid dates")
        return self.get("/games?date_from="+start+"&date_to="+end+"&per_page=100")
    def boxscore(self,game_id):
        if not str(game_id).isdigit(): raise ValueError("Invalid game ID")
        return self.get("/games/"+str(game_id)+"/boxscore")
    def injuries(self,game_id):
        if not str(game_id).isdigit(): raise ValueError("Invalid game ID")
        return self.get("/games/"+str(game_id)+"/injuries")
