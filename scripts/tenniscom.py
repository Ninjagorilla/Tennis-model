"""Read public, server-rendered schedule facts; never execute page scripts.

The provider's own win probabilities and all market fields are discarded.
"""
import concurrent.futures,hashlib,json,re,unicodedata,urllib.request
from datetime import datetime,timedelta,timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
BASE='https://www.tennis.com'
RULES='https://www.wtatennis.com/news/3043764/tennis-explained-learn-the-game'
CHALLENGER_RULES='https://www.atptour.com/-/media/files/rulebook/2026/2026-rulebook_27apr26.pdf'
CATEGORIES={('men','ATP'):('ATP','main'),('men','Challenger'):('ATP','challenger'),('women','WTA'):('WTA','main'),('women','WTA 125K'):('WTA','wta125')}
# Reviewed facts are scoped to an exact provider edition. Never infer a city,
# country, timezone or identity from a slug, initials, or fuzzy name similarity.
REVIEWED_EDITIONS={
    ('atp-challenger-fort-worth-usa','2026-10-18','2026-10-25'):{
        'name':'ATP Challenger Fort Worth, USA','surface':'hard','tourLevel':'Challenger',
        'location':'Fort Worth, United States','timezone':'America/Chicago',
        'source':'https://www.atptour.com/en/tournaments/fort-worth/3187/overview',
        'reviewed_at':'2026-10-20','timezone_basis':'Verified Fort Worth, Texas location',
    },
}
REVIEWED_PLAYER_NAMES={
    'jj-wolf':{'names':('Wolf, J.J.','J.J. Wolf','Wolf, J J','J J Wolf'),
               'country':'USA','canonical':'J J Wolf',
               'source':'https://www.atptour.com/en/players/enwiki/w09g/bio'},
}

def reviewed_metadata(raw):
    m=dict(raw); applied=[]
    review=REVIEWED_EDITIONS.get((m.get('slug'),m.get('startDate'),m.get('endDate')))
    if review:
        if (any(m.get(k)!=review[k] for k in ('name','surface','tourLevel'))
                or m.get('year')!=2026
                or [(c.get('gender'),c.get('category')) for c in m.get('competitions',[]) if c.get('type')=='singles']!=[('men','Challenger')]):
            raise ValueError('REVIEWED_EDITION_CONFLICT')
        for k in ('location','timezone'):
            if m.get(k) is None or m.get(k)=='':
                m[k]=review[k];applied.append(k)
            elif m[k]!=review[k]:raise ValueError('REVIEWED_EDITION_CONFLICT')
    location=m.get('location')
    if not isinstance(location,str) or len(location.split(','))<2 or not all(x.strip() for x in location.split(',')):
        raise ValueError('LOCATION_METADATA_MISSING')
    tz=m.get('timezone')
    if not isinstance(tz,str) or not tz:raise ValueError('TIMEZONE_METADATA_MISSING')
    try:ZoneInfo(tz)
    except (ZoneInfoNotFoundError,ValueError):raise ValueError('TIMEZONE_METADATA_INVALID')
    return m,({'fields':applied,'source':review['source'],'reviewed_at':review['reviewed_at'],
               'timezone_basis':review['timezone_basis']} if applied else None)

def unstarted_score(score):
    if score is None:return True
    if not isinstance(score,dict):return False
    if not score:return True
    # Exact current provider schema; booleans/floats/unknown fields fail closed.
    return (set(score)=={'currentSetNumber','homeSetsWon','awaySetsWon','sets','currentGame'}
            and score['currentSetNumber'] is None and score['currentGame'] is None
            and type(score['homeSetsWon']) is int and score['homeSetsWon']==0
            and type(score['awaySetsWon']) is int and score['awaySetsWon']==0
            and type(score['sets']) is list and not score['sets'])

def failure_code(exc):
    code=str(exc)
    return code if isinstance(exc,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{2,79}',code) else 'SOURCE_FETCH_OR_SCHEMA_FAILED'

def utc():return datetime.now(timezone.utc)
def stamp(s):
    d=datetime.fromisoformat(s.replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return d.astimezone(timezone.utc)
def key(s):return re.sub('[^a-z0-9]+',' ',''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c)).lower()).strip()
def walk(o):
    if isinstance(o,dict):
        yield o
        for v in o.values():yield from walk(v)
    elif isinstance(o,list):
        for v in o:yield from walk(v)
class Page(HTMLParser):
    def __init__(self):super().__init__();self.scripts=[];self.links=[];self.script=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='script':self.script=[]
        if tag=='a' and 'href' in a:self.links.append(a['href'])
    def handle_data(self,data):
        if self.script is not None:self.script.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.script is not None:self.scripts.append(''.join(self.script));self.script=None
def documents(html):
    page=Page();page.feed(html);parts=[]
    for script in page.scripts:
        # Only decode a literal [1, string] payload. No eval, browser or JS runtime.
        m=re.fullmatch(r'\s*self\.__next_f\.push\((\[1,.*\])\)\s*;?\s*',script,re.S)
        if m:
            data=json.loads(m[1])
            if len(data)==2 and isinstance(data[1],str):parts.append(data[1])
    out=[]
    for line in ''.join(parts).splitlines():
        head,sep,value=line.partition(':')
        if sep and re.fullmatch('[0-9a-f]+',head):
            try:out.append(json.loads(value))
            except ValueError:pass
    if not out:raise ValueError('PROVIDER_SCHEMA_CHANGED')
    return out,page.links
def read(url):
    if not url.startswith(BASE+'/'):raise ValueError('UNAPPROVED_SOURCE')
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Courtside/1.0 personal tennis research'}),timeout=25) as response:
        if not response.url.startswith(BASE+'/'):raise ValueError('UNAPPROVED_REDIRECT')
        raw=response.read(5000000)
    if len(raw)>=5000000:raise ValueError('PAGE_TOO_LARGE')
    return raw.decode('utf8'),{'url':url,'status':'ok','fetched_at':utc().isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),'provider':'Tennis.com'}
def matches(doc):
    batches=[o['initialMatches'] for o in walk(doc) if isinstance(o.get('initialMatches'),list)]
    if not batches:raise ValueError('SCHEDULE_SCHEMA_CHANGED')
    return [r for batch in batches for r in batch if isinstance(r,dict)]
def metadata(doc,slug):
    candidates=[o for o in walk(doc) if o.get('slug')==slug and 'surface' in o and 'competitions' in o]
    if not candidates:raise ValueError('METADATA_MISSING')
    m=candidates[0]
    if any(any(x.get(k)!=m.get(k) for k in ('surface','startDate','endDate','location','timezone','tourLevel','competitions')) for x in candidates):raise ValueError('METADATA_CONFLICT')
    m,supplement=reviewed_metadata(m)
    surface={'hard':'Hard','hard_indoor':'Hard','clay':'Clay','clay_indoor':'Clay','grass':'Grass'}.get(str(m['surface']).lower());level=m.get('tourLevel','')
    if surface not in ('Hard','Clay','Grass'):raise ValueError('UNSUPPORTED_SURFACE')
    if not re.fullmatch(r'(ATP|WTA) (250|500|1000|Finals)|Challenger|WTA 125K?',level):raise ValueError('UNSUPPORTED_SCORING_FORMAT')
    start=datetime.fromisoformat(m['startDate']).date();end=datetime.fromisoformat(m['endDate']).date()
    if not 0<=(end-start).days<=21:raise ValueError('INVALID_TOURNAMENT_DATES')
    scopes={CATEGORIES[(c.get('gender'),c.get('category'))] for c in m['competitions'] if c.get('type')=='singles' and (c.get('gender'),c.get('category')) in CATEGORIES}
    if not scopes:raise ValueError('UNSUPPORTED_COMPETITION')
    return {'metadata_supplement':supplement,'slug':slug,'name':m['officialName'] or m['name'],'names':list({str(m[k]) for k in ('name','officialName') if m.get(k)}),'key':key(m['location'].split(',')[0]),'country':key(m['location'].rsplit(',',1)[-1]),'surface':surface,'court_enclosure':('Indoor' if str(m['surface']).lower().endswith('_indoor') else 'Outdoor'),'timezone':str(m['timezone']),'from':start.isoformat(),'through':end.isoformat(),'scopes':sorted(scopes),'source':BASE+'/tournaments/'+slug,'best_of':3,'deciding_tiebreak_target':7,'format_source':CHALLENGER_RULES if any(r=='challenger' for t,r in scopes) else RULES}
def full_name(p):
    if not isinstance(p,dict) or not re.fullmatch('[a-z0-9-]{3,100}',str(p.get('id',''))):raise ValueError('PLAYER_ID_MISSING')
    n=p.get('name','')
    if not isinstance(n,str):raise ValueError('FULL_PLAYER_NAME_REQUIRED')
    n=n.strip()
    alias=REVIEWED_PLAYER_NAMES.get(p['id'])
    if alias:
        if n not in alias['names'] or p.get('countryCode')!=alias['country']:
            raise ValueError('VERIFIED_PLAYER_ALIAS_CONFLICT')
        return alias['canonical']
    if ',' in n:
        family,given=n.split(',',1);n=given.strip()+' '+family.strip()
    if len(n)>100 or len(key(n).split())<2 or key(n) in ('tbd','qualifier','unknown') or '.' in n:raise ValueError('FULL_PLAYER_NAME_REQUIRED')
    return n
def parse_match(r,m,now,source):
    if r.get('status')!='scheduled' or r.get('startTimeConfirmed') is not True or r.get('winnerId') or not unstarted_score(r.get('score')) or r.get('homeTeam') or r.get('awayTeam'):return None
    cat=(r.get('competitionGender'),r.get('competitionCategory'))
    if cat not in CATEGORIES or r.get('eventCategory')!=('Men\'s Singles' if cat[0]=='men' else 'Women\'s Singles'):return None
    tour,regime=CATEGORIES[cat]
    if (tour,regime) not in [tuple(s) for s in m['scopes']]:return None
    start=stamp(r['startTime'])
    if not now<start<=now+timedelta(hours=24) or not m['from']<=start.astimezone(ZoneInfo(m['timezone'])).date().isoformat()<=m['through']:return None
    ps=sorted([(full_name(r[s]),r[s]['id']) for s in ('homeCompetitor','awayCompetitor')],key=lambda p:key(p[0]))
    if key(ps[0][0])==key(ps[1][0]):return None
    mid=r.get('matchScoreKey')
    if not re.fullmatch(r'sr:sport_event:\d+',str(mid)):return None
    rnd=str(r.get('round',''))
    if 'qualif' in rnd.lower():regime+='_qualifying'
    return {'source_match_id':'tc:'+mid,'source_event_id':m['slug'],'tour':tour,'tournament':m['name'],'tournament_key':m['key'],'regime':regime,'surface':m['surface'],'court_enclosure':m.get('court_enclosure','Unknown'),'name_a':ps[0][0],'name_b':ps[1][0],'player_a':tour+':'+key(ps[0][0]),'player_b':tour+':'+key(ps[1][0]),'source_player_ids':[p[1] for p in ps],'starts_at':start.isoformat(),'start_verified':True,'event_source':source,'surface_source':m['source'],'format_source':m['format_source'],'event_scope':'singles','source_state':'scheduled','round':rnd[:80],'best_of':3,'deciding_tiebreak_target':7,'format_verified':True,'timing_kind':'SOURCE_SCHEDULED_ESTIMATE'}
def discover(now):
    days=sorted({now.date(),(now+timedelta(hours=24)).date()});sources=[];raw=[];slugs=set();unknown=[]
    for day in days:
        url=BASE+'/?date='+day.isoformat()
        try:
            html,evidence=read(url);doc,_=documents(html);rows=matches(doc);sources.append(evidence)
            for row in rows:
                if (row.get('competitionGender'),row.get('competitionCategory')) not in CATEGORIES:continue
                slug=row.get('tournamentSlug','')
                if re.fullmatch('[a-z0-9-]{2,120}',slug):slugs.add(slug);raw.append((row,slug,url))
        except Exception:sources.append({'url':url,'provider':'Tennis.com','status':'unavailable','fetched_at':utc().isoformat()})
    # Calendar links include upcoming main-tour qualifying events before score cards appear.
    try:
        html,evidence=read(BASE+'/tournaments');_,links=documents(html);sources.append(evidence)
        slugs.update(m[1] for link in links if (m:=re.fullmatch(r'/tournaments/([a-z0-9-]{2,120})',link)))
    except Exception:sources.append({'url':BASE+'/tournaments','provider':'Tennis.com','status':'unavailable','fetched_at':utc().isoformat()})
    capped=len(slugs)>60
    def fetch(slug):
        url=BASE+'/tournaments/'+slug
        try:
            html,evidence=read(url);doc,_=documents(html);return slug,metadata(doc,slug),evidence
        except Exception as exc:return slug,None,{'url':url,'provider':'Tennis.com metadata','status':'unavailable','failure_code':failure_code(exc),'fetched_at':utc().isoformat()}
    catalog={};metadata_failures={};rejected=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for slug,m,evidence in pool.map(fetch,sorted(slugs)[:60]):
            sources.append(evidence)
            if m:catalog[slug]=m
            else:
                unknown.append(slug);metadata_failures[slug]=evidence['failure_code']
    events=[]
    for r,slug,url in raw:
        # Diagnose only prospective singles, not historical rows or doubles.
        if r.get('status')!='scheduled' or r.get('eventCategory') not in ("Men's Singles","Women's Singles"):continue
        try:
            if not now<stamp(r['startTime'])<=now+timedelta(hours=24):continue
        except (KeyError,ValueError,TypeError):
            rejected.append({'tournament':slug,'match_id':str(r.get('matchScoreKey','')),'scope':str(r.get('competitionCategory','')),'reason':'INVALID_START_TIME'});continue
        def reject(reason):
            rejected.append({'tournament':slug,'match_id':str(r.get('matchScoreKey','')),'scope':str(r.get('competitionCategory','')),'reason':reason})
        if slug not in catalog:
            reject(metadata_failures.get(slug,'METADATA_DISCOVERY_CAPPED'));continue
        try:
            e=parse_match(r,catalog[slug],now,url)
            if e:events.append(e)
            else:reject('FIXTURE_NOT_VERIFIED')
        except (KeyError,TypeError,ValueError) as exc:reject(failure_code(exc))
    rejected=list({(r['tournament'],r['match_id'],r['reason']):r for r in rejected}.values())
    return events,list(catalog.values()),{'metadata_failures':metadata_failures,'rejected_scheduled_matches':rejected,'incomplete_scopes':sorted({r['scope'] for r in rejected}),'metadata_supplements':{slug:m['metadata_supplement'] for slug,m in catalog.items() if m['metadata_supplement']},'sources':sources,'unknown_tournaments':unknown,'discovery_capped':capped,'metadata_mode':'automatic','metadata_tournaments':len(catalog),'challenger_source_ok':all(s['status']=='ok' for s in sources[:len(days)])}
def match_espn_metadata(event,tour,catalog):
    name=key(event.get('name',''));candidates=[m for m in catalog if name in {key(n) for n in m['names']} and any(s[0]==tour for s in m['scopes'])]
    if not candidates:
        # Sponsor names differ. Require exact city/country, tour and matching edition
        # dates; ambiguous simultaneous events in one city remain unjoined.
        location=event.get('venue',{}).get('displayName','').split(',')
        countries={'china pr':'china','great britain':'united kingdom'}
        if len(location)!=2:return None
        city=key(location[0]);country=countries.get(key(location[1]),key(location[1]))
        try:
            begin=stamp(event['date']).date();end=stamp(event['endDate']).date()
            candidates=[m for m in catalog if m['key']==city and countries.get(m['country'],m['country'])==country and any(s[0]==tour for s in m['scopes']) and abs((datetime.fromisoformat(m['from']).date()-begin).days)<=3 and abs((datetime.fromisoformat(m['through']).date()-end).days)<=3]
        except (KeyError,ValueError,TypeError):return None
    if len(candidates)!=1:return None
    m=candidates[0];scopes=[s for s in m['scopes'] if s[0]==tour]
    if len(scopes)!=1:return None
    return {**m,'tour':tour,'regime':scopes[0][1]}
