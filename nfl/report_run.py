"""Render saved NFL paper evidence without inferring execution from publication.

Standard-library only. This does not run a model, fetch odds, or approve release.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return result


def probabilities(values):
    if not values or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError('Invalid probabilities')
    if abs(sum(values) - 1) > 1e-8:
        raise ValueError('Probability mass does not sum to one')


def verify(freeze, receipt, root):
    payload = freeze['payload']
    if freeze['sha256'] != digest(payload) or receipt['freeze_sha256'] != freeze['sha256']:
        raise ValueError('Freeze or receipt hash mismatch')
    if payload['schema'] != 'nfl-paper-freeze-1' or payload['evidence_class'] != 'PREGAME_TWO_SOURCE_PAPER':
        raise ValueError('Verified pregame paper evidence required')
    if receipt['execution_status'] != 'verified' or receipt['created_at_utc'] != payload['created_at_utc']:
        raise ValueError('Execution receipt mismatch')
    for obj in (payload, receipt):
        if obj.get('quotes_verified') is not False:
            raise ValueError('Quote verification is unsupported by this report')
    if payload.get('promotion_approved') is not False or receipt.get('publication_approved') is not False or receipt.get('public_forecasts') != 0:
        raise ValueError('Publication or promotion gate mismatch')
    games = payload['games']
    if not games or receipt['paper_games'] != len(games):
        raise ValueError('Missing games or receipt count mismatch')
    ids = [g['event_id'] for g in games]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate event')
    created = stamp(payload['created_at_utc'])
    for g in games:
        if created >= stamp(g['starts_at']):
            raise ValueError('Forecast was not frozen before kickoff')
        probabilities([g['game'][k] for k in ('home_win', 'away_win', 'tie')])
        for market in ('game', g['home'], g['away']):
            probabilities(list(g['first_td'][market]['probabilities'].values()))
    for key, scope in [('champion', 'game_lines_and_player_props'), ('challenger', 'first_touchdown_only')]:
        layer = receipt['layers'][key]
        if layer != {'status': 'executed', 'games': len(games), 'scope': scope}:
            raise ValueError('Layer execution or scope mismatch')
    # Compare the immutable Champion implementation and both fitted parameter files.
    protected = {n: h for n, h in payload['code_hashes'].items() if n.startswith('nfl/engine/nfl_champion_v9/')}
    if not protected:
        raise ValueError('Champion implementation hashes missing')
    protected.update({'nfl/original_parameters.json': payload['model_parameter_sha256'],
                      'nfl/first_td_parameters.json': payload['first_td_parameter_sha256']})
    for name, expected in protected.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Protected runtime mismatch: ' + name)
    return payload


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def pct(value):
    return f'{100 * value:.2f}%'


def render(payload, receipt):
    lines = ['# Corrected NFL execution report', '',
             'Archived pregame research, not a new model run or current betting recommendation.', '',
             'Saved forecast: ' + payload['created_at_utc'] + '. Report generated: ' + datetime.now(timezone.utc).isoformat() + '.', '',
             'Freeze integrity, receipt linkage, pre-kickoff timing, Champion implementation and fitted parameter hashes checked against this checkout. Hash checks establish consistency, not independent proof of the original data retrieval.', '',
             '| Layer | Recorded execution | Scope |', '|---|---|---|']
    for key, label in [('champion', 'Champion'), ('challenger', 'Research Challenger'), ('devils_advocate', "Devil’s Advocate")]:
        layer = receipt['layers'].get(key, {})
        lines.append(f"| {label} | {cell(layer.get('status', 'Unavailable'))} | {cell(layer.get('scope', 'Unavailable'))} |")
    lines += ['', 'The Challenger only covers first touchdowns. Devil’s Advocate reweights Champion draws and is not an independent third model. No three-model average is valid for game lines or ordinary player props.', '',
              'Sportsbook quotes remain unverified. Market-specific calibration is incomplete. Publication and promotion remain gated. Player availability is assumed, not confirmed. The saved shadow receipt is reported as recorded; this report does not re-execute or authenticate its separate scenario file.', '']
    for g in payload['games']:
        game = g['game']
        lines += ['## ' + cell(g['away']) + ' at ' + cell(g['home']), '', 'Scheduled kickoff: ' + g['starts_at'], '',
                  f"Simulation: {g['simulation']['draws']:,} draws; effective sample size {g['simulation']['effective_sample_size']:.1f}.", '',
                  '| Result | Champion |', '|---|---:|',
                  f"| {g['away']} win | {pct(game['away_win'])} |", f"| {g['home']} win | {pct(game['home_win'])} |", f"| Tie | {pct(game['tie'])} |",
                  f"| {g['away']} mean points | {game['away_score']['mean']:.2f} |", f"| {g['home']} mean points | {game['home_score']['mean']:.2f} |", f"| Mean total | {game['total']['mean']:.2f} |", '',
                  'These replace the screenshot’s external market baseline. They are not confirmed market prices or newly calibrated probabilities.', '',
                  '### Player means', '', '| Team | Player | Pass yards | Pass TD | Rush yards | Carries | Rec yards | Receptions | Anytime TD |', '|---|---|---:|---:|---:|---:|---:|---:|---:|']
        names = {}
        for team, players in g['players'].items():
            for player in players:
                names[team + '|' + player['player_id']] = player['name']
                means = player['mean']
                values = [f"{means[k]:.2f}" for k in ('passing_yards', 'passing_tds', 'rushing_yards', 'carries', 'receiving_yards', 'receptions')]
                lines.append('| ' + ' | '.join([cell(team), cell(player['name'])] + values + [pct(player['atd'])]) + ' |')
        lines += ['', '### First-touchdown Challenger', '', 'Game-first and team-first are separate outcomes. No-touchdown and unknown-scorer outcomes remain included.', '', '| Market | Scorer / outcome | Probability |', '|---|---|---:|']
        for market, result in g['first_td'].items():
            for identity, p in sorted(result['probabilities'].items(), key=lambda item: -item[1]):
                lines.append(f'| {cell(market)} | {cell(names.get(identity, identity))} | {pct(p)} |')
        lines += ['', '### Recorded input limitations', ''] + ['- ' + cell(w) for w in g['warnings']] + ['']
    lines += ['## Change summary', '', '- Located the NFL implementation inside Tennis-model.', '- Replaced the screenshot’s unexecuted status with the later saved execution evidence.', '- Recovered genuine Champion game and player projections and first-TD Challenger outputs.', '- Kept model scopes, archive time, unverified odds and publication limits explicit.', '- No Champion changes, refit, deployment, publication approval or new live run.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    freeze = json.loads(args.freeze.read_text())
    receipt = json.loads(args.receipt.read_text())
    payload = verify(freeze, receipt, Path(__file__).resolve().parents[1])
    report = render(payload, receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(args.output)


if __name__ == '__main__':
    main()
