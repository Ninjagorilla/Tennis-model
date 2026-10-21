"""Direct HTTP diagnostics only. Never imports schedules or runs predictions."""
import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo
from fixture_ledger import publisher, window
from tenniscom import documents, matches, walk

MAX_BYTES = 5_000_000
DEFAULTS = ['https://www.atptour.com/en/scores/current',
            'https://www.wtatennis.com/tournaments/2092/Ningbo/2026/order-of-play',
            'https://www.tennis.com/?date={date}']

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if publisher(req.full_url) != publisher(newurl):
            raise ValueError('CROSS_PUBLISHER_REDIRECT')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.text, self.scripts = [], [], []
        self.script = None
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'script':
            self.script = []
        if tag in ('style', 'script'):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(''.join(self.script)); self.script = None
        if tag in ('style', 'script'):
            self.hidden = max(0, self.hidden - 1)
    def handle_data(self, value):
        if self.script is not None:
            self.script.append(value)
        if not self.hidden and value.strip():
            self.text.append(value.strip())

def inspect_html(html):
    page = Page(); page.feed(html)
    count, method = 0, 'NO_RECOGNIZED_MATCH_ROWS'
    try:
        docs, _ = documents(html)
        found = matches(docs)
        count = len({str(r.get('id', json.dumps(r, sort_keys=True))) for r in found})
        if count: method = 'TENNIS_COM_INITIAL_MATCHES'
    except (ValueError, KeyError, TypeError):
        pass
    for script in page.scripts:
        try:
            obj = json.loads(script)
        except ValueError:
            continue
        found = [r for r in walk(obj) if isinstance(r.get('competitors'), list)
                 and len(r['competitors']) == 2 and (r.get('startDate') or r.get('date'))]
        if len(found) > count:
            count, method = len(found), 'STRUCTURED_COMPETITORS_WITH_START'
    # A visible Vs delimiter plus two player links is a schedule-row signal,
    # not proof of current singles or completeness. Navigation text alone fails.
    player_links = {u for u in page.links if re.search(r'/players?/[^/]+', u)}
    delimiters = sum(bool(re.fullmatch(r'v(?:s\.?)?', t, re.I)) for t in page.text)
    if not count and delimiters and len(player_links) >= 2:
        count, method = min(delimiters, len(player_links) // 2), 'VISIBLE_VS_AND_PLAYER_LINKS'
    return count, method, page.links

def probe(url, opener=None):
    result = {'url': url, 'status_code': None, 'content_length': 0,
              'match_rows_present': None, 'match_row_count': 0,
              'checked_at': datetime.now(timezone.utc).isoformat()}
    links = []
    try:
        publisher(url)
        opener = opener or urllib.request.build_opener(SafeRedirect()).open
        request = urllib.request.Request(url, headers={'User-Agent': 'Courtside/1.0 schedule availability diagnostic',
                                                       'Accept-Encoding': 'identity'})
        try:
            response = opener(request, timeout=25)
        except urllib.error.HTTPError as exc:
            response = exc  # HTTP errors still carry useful status/body-length evidence.
        with response:
            result.update(status_code=response.code, final_url=response.geturl(),
                          content_type=response.headers.get('Content-Type', ''),
                          declared_content_length=response.headers.get('Content-Length'))
            if publisher(url) != publisher(result['final_url']):
                raise ValueError('CROSS_PUBLISHER_REDIRECT')
            raw = response.read(MAX_BYTES + 1)
        result.update(content_length=len(raw), content_sha256=hashlib.sha256(raw).hexdigest())
        if len(raw) > MAX_BYTES:
            result['outcome'] = 'RESPONSE_TOO_LARGE'
        elif not 200 <= result['status_code'] < 300:
            result['outcome'] = 'HTTP_ERROR'
        elif 'html' not in result['content_type'].lower():
            result['outcome'] = 'UNSUPPORTED_CONTENT_TYPE'
        else:
            count, method, links = inspect_html(raw.decode('utf-8', errors='replace'))
            result.update(match_rows_present=bool(count), match_row_count=count, detection=method,
                          outcome='MATCH_ROWS_DETECTED' if count else 'NO_ROWS_DETECTED_JS_OR_SCHEMA_OR_EMPTY')
    except (OSError, ValueError, TypeError) as exc:
        result.update(outcome='FETCH_FAILED', error=type(exc).__name__ + ':' + str(exc)[:160])
    result['automatic_ingestion_verified'] = False
    return result, links

def diagnose(urls, scan_window, fetch=probe):
    results, visited = [], set()
    for template in urls:
        targets = [template.replace('{date}', d) for d in scan_window['utc_dates']] if '{date}' in template else [template]
        for url in targets:
            if url in visited: continue
            visited.add(url)
            result, links = fetch(url); results.append(result)
            candidates = []
            # Specific event pages can link to archived years. Only discover
            # schedules when the supplied URL itself is a landing page.
            for link in ([] if re.search(r'daily-schedule|order-of-play',urlsplit(url).path) else links):
                target = urljoin(url, link)
                try:
                    if publisher(target) == publisher(url) and re.search(r'daily-schedule|order-of-play', urlsplit(target).path) and target not in visited:
                        candidates.append(target)
                except ValueError:
                    continue
            for target in sorted(set(candidates))[:3]:
                visited.add(target)
                result, _ = fetch(target); results.append(result)
    return {'window': scan_window, 'sources': results,
            'note': 'HTTP and row-detection diagnostics only; no fixture verification, completeness claim or predictions.'}

def markdown(report):
    lines = ['# Order-of-play HTTP diagnostic', '', report['note'], '',
             '| URL | HTTP | Bytes read | Match rows present | Row signals | Outcome |',
             '| --- | --- | --- | --- | --- | --- |']
    for r in report['sources']:
        values = [r['url'], r['status_code'], r['content_length'], r['match_rows_present'], r['match_row_count'], r['outcome']]
        lines.append('| ' + ' | '.join(str(v).replace('|', '%7C').replace('\n', ' ') for v in values) + ' |')
    return '\n'.join(lines) + '\n'

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--url', action='append', help='Repeat for ATP, WTA and Tennis.com; optional {date} expands every overlapping UTC date')
    cli.add_argument('--start-date', default=datetime.now(timezone.utc).astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat())
    cli.add_argument('--days', type=int, default=1)
    cli.add_argument('--output', default='work/order-of-play-diagnostic.json')
    args = cli.parse_args()
    report = diagnose(args.url or DEFAULTS, window(args.start_date, args.days))
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    path.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(markdown(report))
    print(json.dumps(report))

if __name__ == '__main__':
    main()
