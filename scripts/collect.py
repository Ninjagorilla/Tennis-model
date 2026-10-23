"""Public scheduled singles only; unknown surfaces/formats fail closed."""
import concurrent.futures,hashlib,json,re,unicodedata,urllib.request
from datetime import datetime,timedelta,timezone
from tenniscom import discover,match_espn_metadata
from quality import deduplicate,identity
from zoneinfo import ZoneInfo
RULES='https://www.wtatennis.com/news/3043764/tennis-explained-learn-the-game'
def utc():return datetime.now(timezone.utc)
def timestamp(s):
    d=datetime.fromisoformat(s.replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return d.astimezone(timezone.utc)
def key(s):
    s=unicodedata.normalize('NFKD',s)
    return re.sub('[^a-z0-9]+',' ',''.join(c for c in s if not unicodedata.combining(c)).lower()).strip()
def parse(doc,tour,now,config):
    rows=[];unknown=set()
    for event in doc.get('events',[]):
        spec=config.get(str(event.get('id')))
        for group in event.get('groupings',[]):
            if group.get('grouping',{}).get('slug')!=('mens-singles' if tour=='ATP' else 'womens-singles'):continue
            for c in group.get('competitions',[]):
                try:
                    t=c['status']['type'];start=timestamp(c.get('startDate') or c['date'])
                    if t.get('state')!='pre' or t.get('name')!='STATUS_SCHEDULED' or t.get('completed') or c.get('timeValid') is not True or not now<start<=now+timedelta(hours=24):continue
                    players=c['competitors']
                    if len(players)!=2 or any(not str(p['id']).isdigit() or int(p['id'])<=0 for p in players):continue
                    players=sorted(players,key=lambda p:str(p['id']))
                    names=[p['athlete']['displayName'].strip() for p in players]
                    if any(len(n)<4 or len(n)>100 or key(n) in ('tbd','qualifier','unknown') for n in names) or key(names[0])==key(names[1]):continue
                    if not spec or spec['tour']!=tour or not spec['from']<=start.astimezone(ZoneInfo(spec.get('timezone','UTC'))).date().isoformat()<=spec['through']:
                        unknown.add(str(event.get('name','Unknown'))[:150]);continue
                    rows.append({'source_match_id':str(c['id']),'source_event_id':str(event['id']),'tour':tour,'tournament':str(event['name'])[:150],'tournament_key':spec['key'],'regime':spec['regime']+('_qualifying' if 'qualif' in str(c.get('round',{}).get('displayName','')).lower() else ''),'surface':spec['surface'],'court_enclosure':spec.get('court_enclosure','Unknown'),'name_a':names[0],'name_b':names[1],'player_a':tour+':'+key(names[0]),'player_b':tour+':'+key(names[1]),'source_player_ids':[str(p['id']) for p in players],'starts_at':start.isoformat(),'start_verified':True,'event_source':'https://site.api.espn.com/apis/site/v2/sports/tennis/'+tour.lower()+'/scoreboard','format_source':RULES,'surface_source':spec['source'],'event_scope':'singles','source_state':'scheduled','round':str(c.get('round',{}).get('displayName',''))[:80],'best_of':3,'deciding_tiebreak_target':7,'format_verified':True,'timing_kind':'SOURCE_SCHEDULED_ESTIMATE'})
                except (KeyError,ValueError,TypeError):continue
    return rows,unknown
def collect(now=None, scan_window=None):
    """Only independently verified ledger fixtures enter production inference."""
    import os
    from fixture_ledger import load, window
    now = now or utc()
    scan_window = scan_window or window(
        os.getenv('TENNIS_SCAN_DATE', now.astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()),
        int(os.getenv('TENNIS_SCAN_DAYS', '1')))
    return load(now, scan_window)


def merge(rows):
    # Match across providers by exact normalized players and local tournament context.
    # Prefer ESPN when both agree, preserving the existing match IDs.
    out={};blocked=set()
    for row in rows:
        identity=(row['tour'],tuple(sorted((row['player_a'],row['player_b']))),row['tournament_key'],row['regime'])
        if identity in out:
            old=out[identity]
            if any(old[k]!=row[k] for k in ('starts_at','surface','best_of','deciding_tiebreak_target')):blocked.add(identity)
        else:out[identity]=row
    return [e for k,e in out.items() if k not in blocked],len(blocked)

def fingerprint(e):return tuple(str(e[k]) for k in ('tour','source_match_id','source_event_id','regime','player_a','player_b','source_player_ids','starts_at','surface','best_of','deciding_tiebreak_target'))

