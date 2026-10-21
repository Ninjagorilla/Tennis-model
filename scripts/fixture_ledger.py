"""Reviewed source observations, Pacific windows and independent coverage gates.

Parsing is not verification: only agreement between different publishers admits
a fixture. Completeness additionally requires explicit whole-tour/date receipts.
"""
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

PATH = Path('data/tennis_fixture_ledger.json')
TOURS = ('ATP', 'WTA', 'ATP_CHALLENGER', 'WTA125')
SCOPES = {('ATP', 'main'): 'ATP', ('WTA', 'main'): 'WTA',
          ('ATP', 'challenger'): 'ATP_CHALLENGER', ('WTA', 'wta125'): 'WTA125'}
PUBLISHERS = {'atptour.com': 'ATP', 'wtatennis.com': 'WTA', 'tennis.com': 'TENNIS_COM'}

def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return result.astimezone(timezone.utc)

def key(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c))
    return re.sub('[^a-z0-9]+', ' ', value.lower()).strip()

def publisher(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('INVALID_SOURCE_URL')
    host = (parts.hostname or '').lower()
    for domain, name in PUBLISHERS.items():
        if host == domain or host.endswith('.' + domain):
            return name
    raise ValueError('UNAPPROVED_SOURCE_PUBLISHER')

def window(start_date, days=1):
    if type(days) is not int or not 1 <= days <= 7:
        raise ValueError('INVALID_WINDOW_DAYS')
    start = date.fromisoformat(start_date)
    zone = ZoneInfo('America/Los_Angeles')
    lo = datetime.combine(start, time.min, zone).astimezone(timezone.utc)
    hi = datetime.combine(start + timedelta(days=days), time.min, zone).astimezone(timezone.utc)
    dates = []
    day = lo.date()
    while day <= (hi - timedelta(microseconds=1)).date():
        dates.append(day.isoformat())
        day += timedelta(days=1)
    return {'timezone': 'America/Los_Angeles', 'start_date': start_date, 'days': days,
            'start_utc': lo.isoformat(), 'end_utc': hi.isoformat(), 'utc_dates': dates}

def local_start(day, clock, zone_name):
    """Reject DST gaps and folds rather than guessing a UTC offset."""
    naive = datetime.fromisoformat(day + 'T' + clock)
    if naive.tzinfo is not None:
        raise ValueError('LOCAL_TIME_MUST_NOT_HAVE_OFFSET')
    zone = ZoneInfo(zone_name)
    candidates = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(utc)
    if len(candidates) != 1:
        raise ValueError('AMBIGUOUS_OR_NONEXISTENT_LOCAL_TIME')
    return candidates.pop().isoformat()

def category(row):
    return SCOPES[(row['tour'], row['regime'].removesuffix('_qualifying'))]

def identity(row):
    return (category(row), row['tournament_key'], tuple(sorted((key(row['name_a']), key(row['name_b'])))))

def signature(row):
    return identity(row) + (stamp(row['starts_at']).isoformat(), row['regime'], row['surface'],
                            row['best_of'], row['deciding_tiebreak_target'], row['round'])

def validate_row(row):
    category(row)
    for field in ('name_a', 'name_b', 'tournament', 'tournament_key', 'round', 'source_match_id', 'source_event_id'):
        if not isinstance(row[field], str) or not row[field].strip() or len(row[field]) > 160:
            raise ValueError('INVALID_' + field.upper())
    for name in (row['name_a'], row['name_b']):
        if not key(name) or key(name) in ('tbd', 'qualifier', 'unknown', 'bye', 'winner', 'loser') or '/' in name:
            raise ValueError('UNRESOLVED_PLAYER')
    ids = row['source_player_ids']
    if not isinstance(ids, list) or len(ids) != 2 or any(not isinstance(i, str) or not i.strip() for i in ids) or ids[0] == ids[1]:
        raise ValueError('INVALID_PLAYER_IDENTITIES')
    if key(row['name_a']) == key(row['name_b']):
        raise ValueError('DUPLICATE_PLAYERS')
    if row['surface'] not in ('Hard', 'Clay', 'Grass') or type(row['best_of']) is not int or row['best_of'] != 3:
        raise ValueError('INVALID_SURFACE_OR_FORMAT')
    if type(row['deciding_tiebreak_target']) is not int or row['deciding_tiebreak_target'] != 7:
        raise ValueError('INVALID_TIEBREAK_FORMAT')
    for field in ('event_source', 'surface_source', 'format_source'):
        publisher(row[field])
    if stamp(row['starts_at']).isoformat() != local_start(row['local_date'], row['local_time'], row['venue_timezone']):
        raise ValueError('UTC_CONVERSION_MISMATCH')
    return row

def validate_source(source, now):
    provider = publisher(source['url'])
    if not isinstance(source['reviewer'], str) or not source['reviewer'].strip():
        raise ValueError('REVIEWER_REQUIRED')
    observed, reviewed = stamp(source['observed_at']), stamp(source['reviewed_at'])
    if not now - timedelta(hours=12) <= observed <= reviewed <= now:
        raise ValueError('STALE_OR_FUTURE_SOURCE')
    if not re.fullmatch('[a-f0-9]{64}', source['paste_sha256']):
        raise ValueError('PASTE_RECEIPT_REQUIRED')
    if not isinstance(source['fixtures'], list) or not isinstance(source['complete_buckets'], list):
        raise ValueError('INVALID_SOURCE_SCHEMA')
    buckets = set()
    for bucket in source['complete_buckets']:
        if bucket['tour'] not in TOURS or bucket.get('whole_tour_date_reviewed') is not True:
            raise ValueError('WHOLE_TOUR_DATE_REVIEW_REQUIRED')
        buckets.add((bucket['tour'], date.fromisoformat(bucket['utc_date']).isoformat()))
    seen = set()
    for row in source['fixtures']:
        validate_row(row)
        if row['event_source'] != source['url'] or identity(row) in seen:
            raise ValueError('SOURCE_MISMATCH_OR_DUPLICATE_FIXTURE')
        seen.add(identity(row))
    return provider, buckets

def evaluate(document, scan_window, now):
    """Return verified upcoming rows and an auditable count matrix, fail closed."""
    lo, hi = stamp(scan_window['start_utc']), stamp(scan_window['end_utc'])
    expected = [(tour, day) for day in scan_window['utc_dates'] for tour in TOURS]
    groups, scopes, receipts = {}, defaultdict(set), []
    errors = []
    if not isinstance(document, dict) or document.get('schema_version') != 1 or not isinstance(document.get('sources'), list):
        document = {'sources': []}
        errors.append('INVALID_LEDGER_SCHEMA')
    for index, source in enumerate(document['sources']):
        try:
            provider, buckets = validate_source(source, now)
            provider_rows = groups.setdefault(provider, {})
            for row in source['fixtures']:
                ident = identity(row)
                if ident in provider_rows and signature(provider_rows[ident]) != signature(row):
                    raise ValueError('CONFLICTING_SOURCE_OBSERVATIONS')
                provider_rows[ident] = row
            scopes[provider].update(buckets)
            receipts.append({'provider': provider, 'url': source['url'], 'status': 'ok',
                             'observed_at': source['observed_at'], 'reviewed_at': source['reviewed_at'],
                             'paste_sha256': source['paste_sha256']})
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            errors.append('INVALID_SOURCE_' + str(index) + ':' + str(exc))
    # Malformed or stale evidence invalidates the ledger, never silently disappears.
    rows_by_signature = defaultdict(dict)
    counts = {p: defaultdict(int) for p in groups}
    for provider, rows in groups.items():
        for row in rows.values():
            start = stamp(row['starts_at'])
            if lo <= start < hi:
                bucket = (category(row), start.date().isoformat())
                counts[provider][bucket] += 1
                rows_by_signature[signature(row)][provider] = row
    verified, verified_counts = [], defaultdict(int)
    unverified_counts = defaultdict(int)
    for observations in rows_by_signature.values():
        row = next(iter(observations.values()))
        start = stamp(row['starts_at'])
        bucket = (category(row), start.date().isoformat())
        if len(observations) < 2:
            unverified_counts[bucket] += 1
            continue
        verified_counts[bucket] += 1
        if start <= now:
            continue
        a, b = row['name_a'], row['name_b']
        ident = hashlib.sha256(json.dumps(signature(row)).encode()).hexdigest()[:24]
        verified.append(dict(row, source_match_id='verified:' + ident,
            player_a=row['tour'] + ':' + key(a), player_b=row['tour'] + ':' + key(b),
            start_verified=True, format_verified=True, event_scope='singles', source_state='scheduled',
            timing_kind='TWO_SOURCE_REVIEWED_SCHEDULE', source_provenance='TWO_SOURCE_VERIFIED',
            verification={'providers': sorted(observations), 'source_urls': [r['event_source'] for r in observations.values()],
                          'source_player_ids': {p: r['source_player_ids'] for p, r in observations.items()}}))
    matrix, reasons = [], []
    for tour, day in expected:
        bucket = (tour, day)
        observed = {p: counts[p][bucket] if bucket in scopes[p] else None for p in groups}
        known = [n for n in observed.values() if n is not None]
        why = []
        if len(known) < 2:
            why.append('MISSING_INDEPENDENT_TOUR_DATE_SOURCE')
        if len(set(known)) > 1:
            why.append('SOURCE_COUNT_MISMATCH')
        if known and (verified_counts[bucket] != max(known) or unverified_counts[bucket]):
            why.append('UNVERIFIED_OR_CONFLICTING_FIXTURES')
        matrix.append({'tour': tour, 'utc_date': day, 'source_counts': observed,
                       'verified_count': verified_counts[bucket], 'unverified_count': unverified_counts[bucket],
                       'status': 'PARTIAL' if why else 'COMPLETE', 'reasons': why})
        reasons.extend(tour + '/' + day + ':' + reason for reason in why)
    if errors or not verified:
        status = 'FAILED'
        reasons = errors + (['EMPTY_OR_UNVERIFIED_LEDGER'] if not verified else []) + reasons
        verified = []
    else:
        status = 'PARTIAL' if reasons else 'COMPLETE'
    summary = '; '.join(f"{r['tour']} {r['utc_date']}: " + ', '.join(f'{p}={n if n is not None else "missing"}' for p, n in r['source_counts'].items()) + f", verified={r['verified_count']}" for r in matrix)
    report = {'status': status, 'coverage': status.lower(), 'reasons': reasons, 'window': scan_window,
              'count_tolerance': 0, 'counts': matrix, 'sources': receipts, 'verified_upcoming_count': len(verified),
              'note': status + (': ' + '; '.join(reasons) if reasons else '') + '. ' + summary}
    return verified, report

def load(now, scan_window, path=PATH):
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        doc = None
    return evaluate(doc, scan_window, now)
