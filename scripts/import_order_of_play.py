"""Parse reviewed pasted schedules; assemble source receipts without inventing data."""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from fixture_ledger import local_start, validate_source, evaluate, window, key

# Deliberately small grammar. Unknown text is an error, never silently skipped.
LINE = re.compile(r'^(?:Starts?\s+At\s+)?(\d{1,2}:\d{2}(?:\s*[AP]M)?)\s+(.*?)\s+v(?:s\.?)?\s+(.*?)$', re.I)

def clock(value):
    value = value.strip().upper()
    for fmt in ('%H:%M', '%I:%M %p', '%I:%M%p'):
        try:
            return datetime.strptime(value, fmt).strftime('%H:%M')
        except ValueError:
            pass
    raise ValueError('EXPLICIT_CLOCK_TIME_REQUIRED')

def parse_paste(text, context, now):
    rows = []
    lines = [(n, s.strip()) for n,s in enumerate(text.splitlines(), 1) if s.strip()]
    normalized = []
    index = 0
    while index < len(lines):
        number, line = lines[index]
        time_line = re.fullmatch(r'(?:Starts?\s+At\s+)?(\d{1,2}:\d{2}(?:\s*[AP]M)?)', line, re.I)
        if time_line and index+3<len(lines) and re.fullmatch(r'v(?:s\.?)?', lines[index+2][1], re.I):
            normalized.append((number,time_line[1]+' '+lines[index+1][1]+' vs '+lines[index+3][1]))
            index += 4
        else:
            normalized.append((number,line)); index += 1
    for number, raw in normalized:
        line = raw.strip()
        if not line:
            continue
        if re.search(r'followed by|not before|TBD|to be announced|winner of|loser of', line, re.I):
            raise ValueError(f'LINE_{number}:UNCONFIRMED_START_OR_PLAYER')
        if '|' in line or '\t' in line:
            parts = [p.strip() for p in re.split(r'\||\t', line)]
            if len(parts) != 4:
                raise ValueError(f'LINE_{number}:EXPECTED_TIME_PLAYER_PLAYER_MATCH_ID')
            local_time, name_a, name_b, match_id = parts
        else:
            match = LINE.fullmatch(line)
            if not match:
                raise ValueError(f'LINE_{number}:UNSUPPORTED_PASTE_FORMAT')
            local_time, name_a, name_b = match.groups()
            # Source match IDs must be supplied in context; never synthesize one.
            match_id = context.get('match_ids', {}).get(name_a + ' vs ' + name_b)
        try:
            ids = [context['players'][name_a], context['players'][name_b]]
            if not match_id:
                raise ValueError('SOURCE_MATCH_ID_REQUIRED')
            local_time = clock(local_time)
            row = {k: context[k] for k in ('tour', 'regime', 'tournament', 'tournament_key',
                    'surface', 'round', 'source_event_id', 'best_of', 'deciding_tiebreak_target',
                    'surface_source', 'format_source', 'local_date', 'venue_timezone')}
            row.update(name_a=name_a, name_b=name_b, source_player_ids=ids,
                       source_match_id=match_id, event_source=context['source_url'],
                       local_time=local_time,
                       starts_at=local_start(context['local_date'], local_time, context['venue_timezone']))
            rows.append(row)
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f'LINE_{number}:{exc}') from exc
    if not rows and context.get('confirmed_empty') is not True:
        raise ValueError('EMPTY_PASTE_REQUIRES_EXPLICIT_EMPTY_SLATE_REVIEW')
    source = {'url': context['source_url'], 'observed_at': context['observed_at'],
              'reviewed_at': now.isoformat(), 'reviewer': context['reviewer'],
              'paste_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
              'complete_buckets': context.get('complete_buckets', []), 'fixtures': rows}
    validate_source(source, now)
    return source

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest='command', required=True)
    paste = sub.add_parser('paste', help='Parse a single reviewed source page into a receipt')
    paste.add_argument('--input', default='-', help='UTF-8 text file, or - for stdin')
    paste.add_argument('--context', required=True, help='Reviewed tournament, timezone and identity JSON')
    paste.add_argument('--output', required=True, help='Source receipt JSON; not yet a verified ledger')
    assemble = sub.add_parser('assemble', help='Compare independent receipts and write the production ledger')
    assemble.add_argument('--sources', nargs='+', required=True)
    assemble.add_argument('--start-date', required=True, help='First America/Los_Angeles calendar date')
    assemble.add_argument('--days', type=int, default=1)
    assemble.add_argument('--output', default='data/tennis_fixture_ledger.json')
    assemble.add_argument('--report', default='work/ledger-coverage.json')
    args = cli.parse_args()
    now = datetime.now(timezone.utc)
    try:
        if args.command == 'paste':
            raw = sys.stdin.read() if args.input == '-' else Path(args.input).read_text(encoding='utf-8-sig')
            context = json.loads(Path(args.context).read_text(encoding='utf-8-sig'))
            source = parse_paste(raw, context, now)
            write_json(args.output, source)
            print(json.dumps({'status': 'PARSED_UNVERIFIED', 'rows': len(source['fixtures']), 'output': args.output}))
        else:
            doc = {'schema_version': 1, 'sources': [json.loads(Path(p).read_text(encoding='utf-8')) for p in args.sources]}
            _, report = evaluate(doc, window(args.start_date, args.days), now)
            write_json(args.report, report)
            print(json.dumps(report))
            if report['status'] == 'FAILED':
                raise ValueError('FAILED_LEDGER_NOT_WRITTEN; see coverage report')
            write_json(args.output, doc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        cli.exit(1, str(exc) + '\n')

if __name__ == '__main__':
    main()
