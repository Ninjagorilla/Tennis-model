"""Opt-in, provenance-preserving 2026 historical updates for the V3 research model.

The bundled Sackmann archive is never overwritten. A validated 2026 CSV from
TennisMyLife may be imported as a separate source, with names mapped to known
IDs only when unique; October 8 official results without point counts are
tracked for Elo and last-N form but NEVER used to synthesize service points.
All of these sources remain research-only; their archival observation instants
cannot certify historical prospective forecasts.
"""
from __future__ import annotations
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
from .automatic import norm,is_complete_score,resolve_level,ROUND_ORDER,VERIFIED_NAME_ALIASES

SOURCE_NAMES={
    'atp_main':'2026.csv',
    'atp_challenger':'2026_challenger.csv',
    'atp_qualifying':'atp_quali/2026_atp_quali.csv',
    'wta_main':'2026_wta.csv',
}
BASE_URL='https://stats.tennismylife.org/data/'
UPDATE_START=date(2026,6,1)

def _index_names(names):
    d=defaultdict(set)
    for pid,aliases in names.items():
        for alias in aliases:d[norm(alias)].add(pid)
    return d

def _person_id(name,tour,source_id,aliases,exclusions):
    key=norm(name)
    key=VERIFIED_NAME_ALIASES.get((key,tour),key)
    candidates=aliases.get(key,set())
    if len(candidates)==1:return next(iter(candidates))
    if len(candidates)>1:
        exclusions['ambiguous_name_ids']+=1
        return None
    if source_id:
        return f'{tour}:TML:{str(source_id).strip()}'
    exclusions['unknown_player_identity']+=1
    return None

def _match_key(tour,winner,loser,tournament):
    return (tour,tuple(sorted((norm(winner),norm(loser)))),norm(tournament))

def _append_result_only(dat,path,cutoff,exclusions,keys,names_by_id,pairs):
    if not path.is_file():return 0
    aliases=_index_names(names_by_id);n=0
    for row in csv.DictReader(path.open(newline='',encoding='utf-8-sig')):
        if row['tour'].upper()!=dat['tour']:continue
        try:
            day=date.fromisoformat(row['date'])
            if not UPDATE_START<=day<=cutoff or not is_complete_score(row['score']):continue
            if not row['source_url'].startswith('https://'):raise ValueError('source url missing')
            surface=row['surface'].lower();assert surface in ('hard','clay','grass')
            key=_match_key(dat['tour'],row['winner_name'],row['loser_name'],row['tournament'])
            pair=(dat['tour'],tuple(sorted((norm(row['winner_name']),norm(row['loser_name'])))),day.isoformat())
            if key in keys or pair in pairs:
                exclusions['manual_result_already_present']+=1;continue
            w=_person_id(row['winner_name'],dat['tour'],None,aliases,exclusions)
            l=_person_id(row['loser_name'],dat['tour'],None,aliases,exclusions)
            if w is None or l is None or w==l:
                exclusions['manual_unknown_identity']+=1;continue
            uid='MANUAL-RESULT:'+hashlib.sha256(('|'.join(str(x) for x in key)+row['date']).encode()).hexdigest()[:18]
            dat['results'].append(dict(match_id=uid,date=day.isoformat(),observed_at=datetime.now(timezone.utc).isoformat(),
                tour=dat['tour'],surface=surface,level=row['level'],tournament_id='MANUAL:'+norm(row['tournament']),
                winner_id=w,loser_id=l,status='completed',temporal_precision='VERIFIED_MATCH_DAY_ARCHIVED_LATER',
                historical_source_url=row['source_url'],service_point_observations='NOT_AVAILABLE'))
            keys.add(key);pairs.add(pair);dat['names'].setdefault(w,[]);dat['names'].setdefault(l,[])
            dat['names'][w]=sorted(set(dat['names'][w]+[row['winner_name']]))
            dat['names'][l]=sorted(set(dat['names'][l]+[row['loser_name']]))
            n+=1
        except (KeyError,ValueError,AssertionError):
            exclusions['manual_bad_row']+=1
    return n

def _tml_level(tour,kind,code,round_):
    """TML uses numerical tour categories; Sackmann numerical WTA codes mean ITF.

    The provenance and source tier MUST decide interpretation. Unknown codes do
    not inherit MAIN by default.
    """
    rnd=(round_ or '').strip().upper();code=str(code or '').strip().upper()
    if rnd in ('Q1','Q2','Q3','Q4'):return 'QUALIFYING',True
    if kind=='atp_qualifying':
        return ('QUALIFYING',True) if rnd in ('Q1','Q2','Q3','Q4') else (None,False)
    if kind=='atp_challenger':
        if code in ('C','CH','50','75','100','125','175','CHALLENGER'):
            return 'CHALLENGER',True
        return None,False
    if kind=='atp_main':
        if code in ('250','500','1000','A','M','G','F','O','D'):
            return ('DAVIS_CUP' if code=='D' else 'MAIN'),True
        return None,False
    if kind=='wta_main':
        if code in ('125','C','W','WTA125'):return 'WTA125',True
        if code in ('250','500','1000','2000','A','M','G','F','P','PM','I','O'):
            return 'MAIN',True
        return None,False
    return None,False

def _append_tml(dat,path,kind,cutoff,exclusions,keys,pairs,event_pairs):
    if not path.is_file():return 0,0
    names=dat['names'];aliases=_index_names(names);rows=0;points_added=0
    for row in csv.DictReader(path.open(newline='',encoding='utf-8-sig')):
        try:
            raw_date=(row.get('tourney_date') or '').strip()
            d=datetime.strptime(raw_date,'%Y%m%d').date()
            if not UPDATE_START<=d<=cutoff:continue
            # The published date may be the start of an entire tournament.
            # A late round could complete AFTER that start date. Refuse the
            # current 21-day uncertain window until independently dated.
            if d>cutoff-timedelta(days=21):
                exclusions['tml_unsettled_tournament_week_date_proxy']+=1;continue
            score=row.get('score') or ''
            if not is_complete_score(score):
                exclusions['tml_incomplete_score']+=1;continue
            surface=(row.get('surface') or '').lower()
            if surface not in ('hard','clay','grass'):
                exclusions['tml_missing_surface']+=1;continue
            level,include=_tml_level(dat['tour'],kind,row.get('tourney_level'),row.get('round'))
            if not include:
                exclusions['tml_itf_or_unsupported_level']+=1;continue
            winner_name=(row.get('winner_name') or '').strip();loser_name=(row.get('loser_name') or '').strip()
            if not winner_name or not loser_name:continue
            key=_match_key(dat['tour'],winner_name,loser_name,str(row.get('tourney_name') or ''))
            pair=(dat['tour'],tuple(sorted((norm(winner_name),norm(loser_name)))),d.isoformat())
            if key in keys or pair in pairs:
                exclusions['tml_duplicate']+=1;continue
            winner=_person_id(winner_name,dat['tour'],row.get('winner_id'),aliases,exclusions)
            loser=_person_id(loser_name,dat['tour'],row.get('loser_id'),aliases,exclusions)
            if not winner or not loser or winner==loser:
                exclusions['tml_identity_blocked']+=1;continue
            event_pair=(dat['tour'],str(row.get('tourney_id') or ''),frozenset((winner,loser)))
            if event_pair in event_pairs:
                exclusions['tml_duplicate_original_archive_event']+=1;continue
            # Preserve source names/IDs without assuming independent source's IDs are identical.
            names.setdefault(winner,[]);names.setdefault(loser,[])
            names[winner]=sorted(set(names[winner]+[winner_name]));names[loser]=sorted(set(names[loser]+[loser_name]))
            aliases[norm(winner_name)].add(winner);aliases[norm(loser_name)].add(loser)
            tid=str(row.get('tourney_id') or 'TML-UNKNOWN')
            uid='TML2026:'+hashlib.sha256(('|'.join(str(x) for x in key)+d.isoformat()+str(row.get('match_num'))).encode()).hexdigest()[:19]
            basic={'match_id':uid,'date':d.isoformat(),'observed_at':datetime.now(timezone.utc).isoformat(),
                'tour':dat['tour'],'surface':surface,'level':level,'tournament_id':'TML:'+tid,
                'temporal_precision':'TML_PUBLISHED_DATE_FIELD_NOT_INDEPENDENTLY_VERIFIED_MATCH_DAY'}
            won=[];valid=True
            for prefix in ('w','l'):
                try:
                    n=int(float(row[prefix+'_svpt']));a=int(float(row[prefix+'_1stWon']));b=int(float(row[prefix+'_2ndWon']))
                    if not 0<n and 0<=a+b<=n:valid=False;break
                    won.append((a+b,n))
                except (KeyError,TypeError,ValueError):valid=False;break
            if valid:
                dat['points'].append({**basic,'server_id':winner,'receiver_id':loser,'serve_points_won':str(won[0][0]),'serve_points_total':str(won[0][1])})
                dat['points'].append({**basic,'server_id':loser,'receiver_id':winner,'serve_points_won':str(won[1][0]),'serve_points_total':str(won[1][1])})
                points_added+=1
            else:
                exclusions['tml_result_only_missing_valid_service_points']+=1
            dat['results'].append({**basic,'winner_id':winner,'loser_id':loser,'status':'completed',
               'service_point_observations':'VERIFIED_IN_SOURCE' if valid else 'NOT_AVAILABLE'})
            keys.add(key);pairs.add(pair);event_pairs.add(event_pair);rows+=1
        except (TypeError,ValueError,KeyError,OverflowError):
            exclusions['tml_bad_row']+=1
    return rows,points_added

def append_updates(dat,cache,cutoff=None):
    cutoff=cutoff or date.today();cache=Path(cache);where=cache/'updates'
    if not where.is_dir():return dat
    x=defaultdict(int)
    keys=set();pairs=set();event_pairs=set()
    # The raw archive has tournament START dates and names; this is a best-effort
    # duplicate key, not a claim that distinct provider IDs match.
    for r in dat['results']:
        event_pairs.add((r['tour'],str(r.get('tournament_id') or ''),frozenset((r['winner_id'],r['loser_id']))))
        w=dat['names'].get(r['winner_id'],[]);l=dat['names'].get(r['loser_id'],[])
        if w and l:
            # Unknown legacy tournament's human-readable name: same-player same-day
            # matches may still require manual reconciliation.
            keys.add((r['tour'],tuple(sorted((norm(w[0]),norm(l[0])))),str(r.get('tournament_id',''))))
    count_tml=0;count_point=0
    for name in (['atp_main','atp_challenger','atp_qualifying'] if dat['tour']=='ATP' else ['wta_main']):
        file=where/(name+'.csv')
        if not file.is_file():continue
        meta=file.with_suffix('.source.json')
        if not meta.is_file():raise ValueError('MISSING_TML_SOURCE_MANIFEST:'+str(file))
        obj=json.loads(meta.read_text(encoding='utf-8'))
        actual=hashlib.sha256(file.read_bytes()).hexdigest()
        if obj.get('sha256')!=actual or obj.get('origin')!=BASE_URL+SOURCE_NAMES[name]:
            raise ValueError('TML_SOURCE_INTEGRITY_FAILURE:'+str(file))
        added,with_points=_append_tml(dat,file,name,cutoff,x,keys,pairs,event_pairs)
        count_tml+=added;count_point+=with_points
        dat['sources'].append({'kind':'tml_verified_recent','file':name,'year':2026,'url':obj['origin'],
               'sha256':actual,'local_file':str(file),'rows_imported':added,
               'point_stats_imported':with_points,'temporal_limit':'NO_ORIGINAL_REALTIME_OBSERVATION_SNAPSHOT'})
    manual=where/'manual_verified_results_2026_10.csv'
    manual_added=_append_result_only(dat,manual,cutoff,x,keys,dat['names'],pairs)
    if manual.is_file():
        dat['sources'].append({'kind':'manually_verified_results_only','year':2026,'url':'per_row_source_url',
                'sha256':hashlib.sha256(manual.read_bytes()).hexdigest(),'local_file':str(manual),
                'rows_imported':manual_added,'point_stats_imported':0})
    if not (count_tml or manual_added):return dat
    dat['excluded'].update({f'update_{k}':v for k,v in x.items()})
    dat['update_summary']={'tml_completed_matches':count_tml,'tml_matches_with_service_points':count_point,
           'manual_results_only':manual_added,'manual_or_feed_unknown_identity':x['manual_unknown_identity']}
    dat['matches']=len(dat['results'])
    dat['date_min']=min(r['date'] for r in dat['results']);dat['date_max']=max(r['date'] for r in dat['results'])
    dat['date_max_points']=max(r['date'] for r in dat['points'])
    return dat
