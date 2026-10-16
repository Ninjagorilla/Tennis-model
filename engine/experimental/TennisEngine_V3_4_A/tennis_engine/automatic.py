"""Research-only automatic player-name matchup adapter for public historical CSVs.

WARNING: Jeff Sackmann match CSVs expose tournament start dates, not actual
match timestamps. This data CANNOT certify contemporaneous Elo, prospective
forecasts, or historical out-of-sample results. Users see explicit warnings.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from .models import (train_glm, train_elo, score_match, save_artifact, load_artifact,
                     sha256_data)
from .scoring import simulate

SOURCE_TEMPLATE=(
    'https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/{tour}/{tour}_matches_{year}.csv',
    'https://raw.githubusercontent.com/JeffSackmann/tennis_{tour}/master/{tour}_matches_{year}.csv',
)
# AUDIT NOTE 2026-10-08: the JeffSackmann/tennis_atp (and tennis_wta) upstream
# repositories return HTTP 404 for the whole repo as of 2026-10-08 (verified via
# the GitHub API: "Not Found"). The Aneeshers mirror is therefore the effective
# primary source and is tried FIRST. The old upstream URL is kept last in case
# the repository is restored; a fast 404 there falls through to the next template.
DISCLAIMER=(
    'RESEARCH_ONLY. No original SR-Elo Champion artifacts or original current-state feature. '
    'Historical CSV has tournament START dates, not verified match dates, so Elo chronology '
    'and time-decay are approximate. No calibrated accuracy is claimed. '
    'No verified upcoming fixture or latest medical status is supplied.'
)
QUAL_SOURCE_TEMPLATE={
    'ATP':('https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/atp/atp_matches_qual_chall_{year}.csv',),
    'WTA':('https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/wta/wta_matches_qual_itf_{year}.csv',),
}
# AUDIT NOTE 2026-10-08: the Sackmann "qual/challenger" files carry ATP Challenger
# events (level 'C'), tour-level qualifying (rounds Q1-Q4), WTA125 events (women's
# level 'C' or 'W', e.g. "Canberra 125"), and ITF prize-money levels. ITF is OUT OF SCOPE
# for this engine and is excluded at parse time; everything else is ingested with
# a tour-aware level label so the GLM level feature can separate the tiers.
LEVELS={'A':'MAIN','G':'MAIN','M':'MAIN','F':'MAIN','D':'DAVIS_CUP','Q':'QUALIFYING',
        'P':'MAIN','PM':'MAIN','I':'MAIN','O':'MAIN'}  # O = Olympic singles
# NOTE: raw level 'C' is tour-aware (ATP -> CHALLENGER, WTA -> WTA125) and 'W' is WTA125;
# in resolve_level, not via LEVELS. 'S' (men's satellites) and all-digit codes
# (women's ITF prize money, e.g. '15','35') are ITF -> excluded, never forecasted.


def resolve_level(tour, raw_level, round_):
    """Map a Sackmann (tourney_level, round) to (engine level, include_row).

    ITF rows return (None, False) and are excluded from training entirely.
    """
    code=(raw_level or '').strip()
    rnd=(round_ or '').upper()
    if rnd in ('Q1','Q2','Q3','Q4'):
        return 'QUALIFYING',True
    if tour=='ATP' and code=='C':
        return 'CHALLENGER',True
    # WTA's original archive also codes a handful of 125 events as 'W'.
    if tour=='WTA' and code in ('C','W'):
        return 'WTA125',True
    if code=='S' or code.isdigit():
        return None,False  # ITF / satellites: out of scope, excluded
    # Unknown codes are NEVER interpreted as main-tour matches. A new source
    # vocabulary should trigger a deliberate review, not contaminate the fit.
    if code not in LEVELS:
        return None,False
    return LEVELS[code],True
ROUND_ORDER={'Q1':0,'Q2':1,'Q3':2,'RR':3,'R256':4,'R128':5,'R64':6,'R32':7,'R16':8,
             'QF':9,'SF':10,'F':11,'BR':12}
FRESH_AFTER_DAYS=21

# The source archive has two IDs for the *same* Czech Jakub Mensik, adjacent in
# 2023 with matching ages (17.3--17.6), nationality and exact name. The 210150
# record continues through 2026; 210084 only covers eleven matches Jan--May 2023.
# This is a narrowly verified selector, not fuzzy-merging people or match data.
# The earlier rows remain attributed to their source ID in the model.
VERIFIED_NAME_ID_SELECTOR={('jakub mensik','ATP'):'ATP:210150'}
# Individually corroborated spelling/spacing variants from the prior fixed
# August-September backtest. Only apply if the target maps to ONE existing ID.
VERIFIED_NAME_ALIASES={('abdullah shelbayh','ATP'):'abedallah shelbayh',
                       ('xinyu wang','WTA'):'xin yu wang'}


def norm(name):
    value=unicodedata.normalize('NFKD',name).casefold()
    value=''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9 ]',' ',value).split())


def is_complete_score(score):
    score=(score or '').upper().strip()
    return bool(score) and bool(re.search(r'\d\s*[-:]\s*\d',score)) and not any(
        token in score for token in ('RET','W/O','WO','DEF','ABD','ABN','CANCEL','UNFIN','SUSP'))


def _inspect_csv_kind(raw:bytes,kind:str):
    """Reject main-tour CSVs mislabeled as qualifying/Challenger caches."""
    try:
        sample=raw.decode('utf-8-sig')
        rd=csv.DictReader(io.StringIO(sample))
        required={'winner_id','loser_id','w_svpt','l_svpt','tourney_date','surface','score','tourney_level','round'}
        if not required.issubset(rd.fieldnames or []):
            raise ValueError('BAD_CSV_HEADER')
        qual_codes=0
        inspected=0
        for record in rd:
            inspected+=1
            code=(record.get('tourney_level') or '').strip()
            rnd=(record.get('round') or '').strip().upper()
            if code=='C' or rnd in ('Q1','Q2','Q3','Q4') or code=='S' or code.isdigit():
                qual_codes+=1
            if inspected>=1500:break
        if inspected==0:raise ValueError('EMPTY_ARCHIVE')
        # In the bundled source archives, all supplementary records have these
        # codes, while none of the main-tour files do. A conservative 25% guard
        # catches a mislabeled main/qual download without relying on filenames.
        if kind=='qual' and qual_codes<inspected*.25:
            raise ValueError('WRONG_ARCHIVE_KIND: qualifying file contains mainly main-draw rows')
        if kind=='main' and qual_codes>inspected*.75:
            raise ValueError('WRONG_ARCHIVE_KIND: main file contains mainly qualifying rows')
    except UnicodeError as exc:
        raise ValueError('NON_UTF8_ARCHIVE') from exc


def _cached_file_is_valid(path:Path,meta:Path,kind:str,stem:str)->bool:
    if not path.exists():return False
    try:
        raw=path.read_bytes()
        _inspect_csv_kind(raw,kind)
        if not meta.exists():
            # Synthetic/local developer fixtures can have no provenance. Never
            # silently accept that state for the supplementary qualifying tier.
            return kind=='main'
        source=json.loads(meta.read_text(encoding='utf-8'))
        sha=source.get('sha256')
        if sha and hashlib.sha256(raw).hexdigest()!=sha:return False
        if source.get('kind') and source['kind']!=kind:return False
        url=source.get('url','')
        if url.startswith(('http://','https://')) and f'/{stem}.csv' not in url:
            return False
        return True
    except (OSError,ValueError,TypeError,KeyError):
        return False


def _get_file(tour,year,cache,refresh_hours=24,kind='main'):
    # tour: lowercase 'atp' | 'wta'. kind='main' -> tour main-draw archive;
    # kind='qual' -> challenger/qualifying archive (best-effort supplementary).
    tour_u=tour.upper()
    if kind=='main':
        stem=f'{tour}_matches_{year}'
        templates=SOURCE_TEMPLATE
    elif kind=='qual':
        stem=(f'{tour}_matches_qual_chall_{year}' if tour_u=='ATP'
              else f'{tour}_matches_qual_itf_{year}')
        templates=QUAL_SOURCE_TEMPLATE[tour_u]
    else:
        raise ValueError("kind must be 'main' or 'qual'")
    cache=Path(cache);path=cache / 'raw' / f'{stem}.csv'
    meta=path.with_suffix('.source.json');path.parent.mkdir(parents=True,exist_ok=True)
    cache_valid=_cached_file_is_valid(path,meta,kind,stem)
    if cache_valid and (datetime.now(timezone.utc)-datetime.fromtimestamp(path.stat().st_mtime,timezone.utc)).total_seconds()<refresh_hours*3600:
        return path,json.loads(meta.read_text()) if meta.exists() else {'url':'previously cached'}
    errors=[]
    # Previously a hard-coded SOURCE_TEMPLATE caused a *main-tour* download to
    # overwrite a correctly named Challenger/WTA125 file on refresh.
    for template in templates:
        url=template.format(tour=tour,year=year)
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'TennisModelResearch/1.1 (noncommercial attribution Jeff Sackmann)'})
            with urllib.request.urlopen(request,timeout=24) as r:
                raw=r.read(12_000_001)
            if len(raw)>12_000_000:raise ValueError('CSV larger than configured download cap')
            _inspect_csv_kind(raw,kind)
            temp=path.with_suffix('.tmp');temp.write_bytes(raw);temp.replace(path)
            source={'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),
                    'kind':kind,'stem':stem,
                    'note':'match dates are tournament-start proxies, not actual dates'}
            meta.write_text(json.dumps(source,indent=2));return path,source
        except Exception as exc:
            errors.append(f'{url}: {type(exc).__name__}: {exc}')
    if cache_valid:
        old=json.loads(meta.read_text()) if meta.exists() else {'url':'offline cached'}
        old['refresh_errors']=errors
        return path,old
    raise RuntimeError(('DATA_SOURCE_UNAVAILABLE_OR_CORRUPT_CACHE: ' if path.exists() else 'DATA_SOURCE_UNAVAILABLE: ') + ' / '.join(errors))


def load_archive(tour,years,cache,refresh_hours=24,allow_partial=False,include_qual=True):
    """Auto-download and parse public noncommercial historical tennis data.

    Ingests both the main-draw archive and the challenger/qualifying archive.
    ITF rows are excluded (out of scope). The qual archive is best-effort: if it
    is unreachable, main-tour ingestion still succeeds and the gap is recorded.
    """
    if tour not in ('ATP','WTA'):raise ValueError('tour must be ATP or WTA')
    sources=[];points=[];results=[];names=defaultdict(set);dated=[];excluded=defaultdict(int)
    seen_ids=set()
    for year in years:
        for kind in (('main','qual') if include_qual else ('main',)):
            try:path,source=_get_file(tour.lower(),year,cache,refresh_hours,kind=kind)
            except RuntimeError:
                if kind=='qual':
                    # Supplementary tier: degrade gracefully, keep main-tour data.
                    sources.append({'kind':kind,'year':year,'unavailable':True,
                                    'local_file':None})
                    excluded['supplementary_qual_archive_unavailable']+=1
                    continue
                if allow_partial:continue
                raise
            sources.append({**source,'kind':kind,'year':year,'local_file':str(path)})
            if source.get('unavailable'):continue
            with path.open(encoding='utf-8-sig',newline='') as f:
                for n,r in enumerate(csv.DictReader(f),start=1):
                    try:
                        surface=(r.get('surface') or '').lower()
                        if surface not in ('hard','clay','grass'):
                            excluded['unknown_surface']+=1;continue
                        if not is_complete_score(r.get('score')):
                            excluded['incomplete_retirement_or_walkover']+=1;continue
                        tournament_start=datetime.strptime(r['tourney_date'],'%Y%m%d').date()
                        if tournament_start>date.today():
                            excluded['future_tournament']+=1;continue
                        # Ignore any tournament started fewer than 21 days ago because its
                        # match dates are unknown and could include uncompleted draws.
                        if tournament_start>date.today()-timedelta(days=FRESH_AFTER_DAYS):
                            excluded['unsettled_recent_tournament']+=1;continue
                        winner=f'{tour}:{r["winner_id"]}';loser=f'{tour}:{r["loser_id"]}'
                        if not (r.get('winner_name') and r.get('loser_name') and winner!=loser):
                            excluded['identity_missing']+=1;continue
                        level,include=resolve_level(tour,r.get('tourney_level',''),r.get('round',''))
                        if not include:
                            excluded['itf_or_unrecognized_level_excluded']+=1;continue
                        names[winner].add(r['winner_name'].strip());names[loser].add(r['loser_name'].strip())
                        ww=int(float(r['w_1stWon']))+int(float(r['w_2ndWon']))
                        lw=int(float(r['l_1stWon']))+int(float(r['l_2ndWon']))
                        wn=int(float(r['w_svpt']));ln=int(float(r['l_svpt']))
                        if not (0<wn and 0<ln and 0<=ww<=wn and 0<=lw<=ln):
                            excluded['invalid_service_statistics']+=1;continue
                        tid=str(r.get('tourney_id') or 'EVENT-UNKNOWN')
                        roundval=ROUND_ORDER.get(r.get('round','').upper(),13)
                        match_id=f'{tournament_start:%Y-%m-%d}|{roundval:02d}|{tid}|{str(r.get("match_num",n)).zfill(5)}|{winner}|{loser}'
                        if match_id in seen_ids:
                            excluded['duplicate_match_across_files']+=1;continue
                        seen_ids.add(match_id)
                        # Proxied tournament start dates for model research only.
                        d=tournament_start.isoformat()
                        common={'match_id':match_id,'date':d,'observed_at':datetime.now(timezone.utc).isoformat(),
                                'tour':tour,'surface':surface,'level':level,'tournament_id':tid,
                                'temporal_precision':'TOURNAMENT_START_ONLY'}
                        results.append({**common,'winner_id':winner,'loser_id':loser,'status':'completed'})
                        points.append({**common,'server_id':winner,'receiver_id':loser,
                                       'serve_points_won':str(ww),'serve_points_total':str(wn)})
                        points.append({**common,'server_id':loser,'receiver_id':winner,
                                       'serve_points_won':str(lw),'serve_points_total':str(ln)})
                        dated.append(d)
                    except (TypeError,ValueError,KeyError,OverflowError):
                        excluded['bad_row_or_missing_point_stats']+=1
    if not points:raise RuntimeError('NO_USABLE_SERVICE_POINT_HISTORY')
    dat={'tour':tour,'points':points,'results':results,'names':{k:sorted(v) for k,v in names.items()},
            'sources':sources,'date_min':min(dated),'date_max':max(dated),
            'date_max_points':max(dated),'excluded':dict(excluded),'matches':len(results)}
    from .history_updates import append_updates
    return append_updates(dat,cache,cutoff=date.today())


def fit_cached(tour,years,cache,refresh_hours=24,allow_partial=False,include_qual=True):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    dat=load_archive(tour,years,cache,refresh_hours,allow_partial=allow_partial,include_qual=include_qual)
    legacy_fingerprint=hashlib.sha256(json.dumps([(x.get('sha256'),x.get('year')) for x in dat['sources']],sort_keys=True).encode()).hexdigest()
    fingerprints=[]
    for src in dat['sources']:
        loc=src.get('local_file')
        digest=hashlib.sha256(Path(loc).read_bytes()).hexdigest() if loc else 'UNAVAILABLE'
        fingerprints.append((src.get('kind'),src.get('year'),digest))
    fingerprint=hashlib.sha256(json.dumps({'schema':'V3_4_SOURCE_BYTES_INCLUDE_UPDATES',
                                'inputs':fingerprints},sort_keys=True).encode()).hexdigest()
    model_file=cache/'models'/f'{tour.lower()}_research_{years[0]}_{years[-1]}.json'
    pkg=None
    if model_file.exists():
        try:
            old=load_artifact(model_file)
            if old.get('raw_data_fingerprint')==fingerprint:pkg=old
            elif (old.get('raw_data_fingerprint')==legacy_fingerprint and
                  all(src.get('sha256')==sha for src,(_,_,sha) in zip(dat['sources'],fingerprints))):
                # V3.2 changed competition-level parsing and must always
                # refit to avoid reusing features trained with old labels.
                pkg=None
        except (OSError,ValueError,KeyError):pass
    if pkg is None:
        cutoff=date.today()+timedelta(days=1)
        pkg={'id':'RECONSTRUCTED_RESEARCH_TOURNAMENT_DATE_PROXY',
             'trained_through':cutoff.isoformat(),
             'raw_data_fingerprint':fingerprint,
             'source_fingerprint_schema':'V3_4_SOURCE_BYTES_INCLUDE_UPDATES',
             'sr_champion':{tour:train_glm(dat['points'],cutoff,365)},
             'sr_challenger':{tour:train_glm(dat['points'],cutoff,180)},
             'elo':train_elo(dat['results'],cutoff),
             'temporal_warning':'Elo is approximate: tournament-start date proxies and round-order tie breaking',
             'original_artifacts_present':False}
        save_artifact(model_file,pkg)
    return pkg,dat,model_file


def resolve_name(name,names):
    if not name.strip():raise ValueError('EMPTY_PLAYER_NAME')
    value=norm(name)
    tours={pid.split(':',1)[0] for pid in names}
    if len(tours)==1:
        value=VERIFIED_NAME_ALIASES.get((value,next(iter(tours))),value)
    exact=[(pid,vals) for pid,vals in names.items() if any(norm(v)==value for v in vals) or pid.casefold()==name.casefold()]
    if len(exact)==1:return exact[0][0],exact[0][1][0]
    if len(exact)>1:
        tour=exact[0][0].split(':',1)[0]
        if all(pid.startswith(tour+':') for pid,_ in exact):
            canonical=VERIFIED_NAME_ID_SELECTOR.get((value,tour))
            if canonical and canonical in {pid for pid,_ in exact}:
                return canonical,names[canonical][0]
    if len(exact)>1:raise ValueError('AMBIGUOUS_PLAYER_NAME: '+repr([(x[0],x[1][0]) for x in exact][:10]))
    fuzzy=[(pid,vals[0]) for pid,vals in names.items() if any(value in norm(v) for v in vals)]
    if len(fuzzy)==1:return fuzzy[0]
    if fuzzy:raise ValueError('PLAYER_NAME_NOT_EXACT. Try one of '+ repr(fuzzy[:12]))
    raise ValueError('PLAYER_NOT_FOUND_IN_DATASET: '+name)



def player_diagnostics(pid,source, surface):
    """Observed descriptive rates, NOT opponent-adjusted fitted effects."""
    served=[r for r in source['points'] if r['server_id']==pid]
    returned=[r for r in source['points'] if r['receiver_id']==pid]
    if not served or not returned:raise ValueError(f'INSUFFICIENT_PLAYER_HISTORY:{pid}')
    def aggregate(rows):
        tot=sum(int(r['serve_points_total']) for r in rows)
        won=sum(int(r['serve_points_won']) for r in rows)
        return (won,tot)
    sw,st=aggregate(served);opp_w,opp_t=aggregate(returned)
    ss,ssn=aggregate([r for r in served if r['surface']==surface])
    os,osn=aggregate([r for r in returned if r['surface']==surface])
    recent=sorted([r for r in source['results'] if pid in (r['winner_id'],r['loser_id'])],
                  key=lambda r:(r['date'],r['match_id']),reverse=True)
    return {'observed_matches':len(recent), 'historical_service_points':st,
            'observed_service_point_win_rate':sw/st,
            'historical_return_points':opp_t,
            'observed_return_point_win_rate':(opp_t-opp_w)/opp_t,
            'surface_service_point_win_rate':ss/ssn if ssn else None,
            'surface_return_point_win_rate':(osn-os)/osn if osn else None,
            'surface_service_points':ssn,'surface_return_points':osn,
            'last_5_match_wins':sum(r['winner_id']==pid for r in recent[:5]),
            'last_10_match_wins':sum(r['winner_id']==pid for r in recent[:10]),
            'last_observed_tournament_start':recent[0]['date'] if recent else None,
            'round_order_is_estimated':True,'not_current_injury_or_fitness_data':True}

def infer_level(player_a,player_b,results):
    """Majority level across both players' 10 most recent observed results.

    Used when research_matchup is called with level='AUTO'. Tie -> 'MAIN'.
    """
    from collections import Counter
    votes=Counter()
    for pid in (player_a,player_b):
        recent=sorted((r for r in results if pid in (r['winner_id'],r['loser_id'])),
                      key=lambda r:(r['date'],r['match_id']),reverse=True)[:10]
        votes.update(r['level'] for r in recent)
    if not votes:return 'MAIN'
    top=votes.most_common()
    winners=[lv for lv,c in top if c==top[0][1]]
    return winners[0] if len(winners)==1 else 'MAIN'


def research_matchup(a,b,tour,surface,best_of=3,n=100000,cache='data_cache',start_year=2023,
                     refresh_hours=24,allow_partial=False,allow_stale=True,seed=None,
                     level='AUTO',include_qual=True,prepared_context=None):
    tour=tour.upper();surface=surface.lower()
    if tour not in ('ATP','WTA') or surface not in ('hard','clay','grass'):raise ValueError('INVALID_TOUR_OR_SURFACE')
    if best_of not in (3,5):raise ValueError('best_of must be 3 or 5')
    if n<100000:raise ValueError('MATCHUP_SCAN_REQUIRES_AT_LEAST_100000_TRIALS')
    level=str(level).upper()
    if level not in ('AUTO','MAIN','CHALLENGER','WTA125','QUALIFYING','DAVIS_CUP'):
        raise ValueError('level must be AUTO, MAIN, CHALLENGER, WTA125, QUALIFYING or DAVIS_CUP')
    if (tour=='ATP' and level=='WTA125') or (tour=='WTA' and level=='CHALLENGER'):
        raise ValueError('TOUR_COMPETITION_LEVEL_MISMATCH')
    if prepared_context is None:
        pkg,dat,model_path=fit_cached(tour,list(range(start_year,date.today().year+1)),cache,
                                       refresh_hours,allow_partial,include_qual=include_qual)
    else:
        pkg,dat,model_path=prepared_context
        if dat['tour']!=tour:raise ValueError('CROSS_TOUR_PREPARED_MODEL_FORBIDDEN')
    player_a,name_a=resolve_name(a,dat['names']);player_b,name_b=resolve_name(b,dat['names'])
    if player_a==player_b:raise ValueError('PLAYERS_MUST_DIFFER')
    if level=='AUTO':
        level=infer_level(player_a,player_b,dat['results'])
        level_source='INFERRED_FROM_RECENT_HISTORY'
    else:
        level_source='USER_SUPPLIED'
    age=(date.today()-date.fromisoformat(dat['date_max'])).days
    service_point_age=(date.today()-date.fromisoformat(dat.get('date_max_points',dat['date_max']))).days
    if not allow_stale and (age>90 or service_point_age>90):raise ValueError(f'HISTORICAL_DATA_STALE:RESULTS_{age}_DAYS;SERVICE_POINTS_{service_point_age}_DAYS')
    missing_qual=[s['year'] for s in dat['sources'] if s.get('kind')=='qual' and s.get('unavailable')]
    if missing_qual and level in ('CHALLENGER','WTA125','QUALIFYING'):
        raise ValueError(f'REQUIRED_QUALIFYING_CHALLENGER_SOURCE_MISSING_FOR_YEARS:{missing_qual}')
    fixture={'match_id':'RESEARCH-ONLY-'+hashlib.sha256(f'{player_a}|{player_b}|{surface}|{best_of}|{level}|{date.today()}'.encode()).hexdigest()[:14],
             'tour':tour,'level':level,'tournament_id':'UNKNOWN_UPCOMING_CONTEXT',
             'player_a_id':player_a,'player_b_id':player_b,'surface':surface,'format':f'bo{best_of}',
             'start_at':datetime.now(timezone.utc).isoformat(),'status':'UNVERIFIED_RESEARCH_MATCHUP'}
    pred=score_match(fixture,pkg)
    if seed is None:
        seed=int(hashlib.sha256(f'{fixture["match_id"]}|{sha256_data(pkg)}|{n}'.encode()).hexdigest()[:8],16)
    mc=simulate(pred['sr_service_a'],pred['sr_service_b'],pred['elo_bridge_service_a'],
                pred['elo_bridge_service_b'],pred['elo_weight'],best_of,n,seed)
    delta=abs(pred['p_a']-mc['p_a'])
    max_error=6*max(mc['mc_se'],1/(2*n)**.5)+.002
    if delta>max_error:raise ArithmeticError(f'DP_MONTE_CARLO_DISAGREEMENT:{delta:.5f}')
    if service_point_age>45:pred['fragility_flags'].append('SERVICE_POINT_STATISTICS_OLDER_THAN_45_DAYS')
    if dat.get('update_summary'):pred['fragility_flags'].append('RECENT_RESULTS_MAY_HAVE_NO_SERVICE_POINT_DATA')
    if missing_qual:pred['fragility_flags'].append('PARTIAL_CHALLENGER_OR_QUALIFYING_ARCHIVE_COVERAGE')
    pred['fragility_flags'].extend(['TOURNAMENT_DATE_PROXY_NOT_EXACT_MATCH_DATE',
                                    'HYPOTHETICAL_MATCHUP_NO_START_STATUS_VERIFIED'])
    return {'mode':'AUTOMATIC_NAME_MATCHUP_RESEARCH_ONLY','model_status':'RECONSTRUCTED_UNVALIDATED',
            'disclaimer':DISCLAIMER,'player_a':name_a,'player_b':name_b,'player_a_id':player_a,
            'player_b_id':player_b,'tour':tour,'surface':surface,'format':f'bo{best_of}',
            'level':level,'level_source':level_source,
            'pick':name_a if pred['p_a']>=.5 else name_b,'probability_a':pred['p_a'],
            'probability_b':pred['p_b'],'sr_probability_a':pred['sr_p_a'],
            'elo_probability_a':pred['elo_p_a'],'challenger_probability_a':pred['challenger_p_a'],
            'elo_weight':pred['elo_weight'],'exact_scorelines':pred['exact']['scorelines'],
            'expected_games':pred['exact']['expected_games'],'median_games':pred['exact']['median_games'],
            'tiebreak_probability':pred['exact']['p_tiebreak'],
            'deciding_set_probability':pred['exact']['p_deciding_set'],
            'fragility_flags':pred['fragility_flags'],'data_quality':pred['data_quality'],
            'player_diagnostics':{'a':player_diagnostics(player_a,dat,surface),
                                  'b':player_diagnostics(player_b,dat,surface)},
            'simulation':mc,'dp_vs_mc_difference':delta,
            'serve_probabilities':{'sr_a':pred['sr_service_a'],'sr_b':pred['sr_service_b'],
                                   'elo_bridge_a':pred['elo_bridge_service_a'],
                                   'elo_bridge_b':pred['elo_bridge_service_b'],
                                   'elo_weight':pred['elo_weight']},
            'dataset':{'oldest_tournament_start':dat['date_min'],'newest_tournament_start':dat['date_max'],
                       'newest_source_age_days':age,'latest_service_point_date':dat.get('date_max_points'),
                       'service_point_age_days':service_point_age,'update_summary':dat.get('update_summary',{}),
                       'records_used':dat['matches'],
                       'excluded_records':dat['excluded'],'sources':dat['sources']},
            'model_path':str(model_path),'model_sha256':sha256_data(pkg),
            'created_at':datetime.now(timezone.utc).isoformat(),
            'no_fixture_verification_or_betting_market_inputs':True,
            'forecast_type':'hypothetical_research_not_eligible_for_prospective_ledger'}
