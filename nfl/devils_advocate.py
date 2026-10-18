"""Shadow sensitivity analysis of Champion draws, never an independent fitted model.

Four declared exponential tilts emphasize high/low totals and home/away margins.
The strength is a stress parameter, not a probability of that scenario occurring.
No input, fitted coefficient, or original simulation weight is modified.
"""
from __future__ import annotations
import numpy as np

VERSION = 'NFL-Devils-Advocate-Shadow-0.1'
STRENGTH = 0.5


def stress_weights(samples):
    w = np.asarray(samples['weights'], dtype=float)
    h = np.asarray(samples['teams']['home']['score'], dtype=float)
    a = np.asarray(samples['teams']['away']['score'], dtype=float)
    if w.ndim != 1 or not len(w) or h.shape != w.shape or a.shape != w.shape:
        raise ValueError('Inconsistent draws')
    if not all(np.isfinite(x).all() for x in [w, h, a]) or (w < 0).any() or not np.isclose(w.sum(), 1):
        raise ValueError('Invalid simulation weights or scores')
    result = {}
    for label, values in [('total', h+a), ('home_margin', h-a)]:
        mean = np.dot(w, values)
        sd = np.sqrt(np.dot(w, (values-mean)**2))
        z = (values-mean)/sd if sd > 0 else np.zeros_like(w)
        for direction, sign in [('high', 1), ('low', -1)]:
            tilted = w*np.exp(np.clip(sign*STRENGTH*z, -20, 20))
            result[f'{label}_{direction}'] = tilted/tilted.sum()
    return result


def analyze(samples, forecast):
    stresses = stress_weights(samples)
    base = np.asarray(samples['weights'])
    h = np.asarray(samples['teams']['home']['score'])
    a = np.asarray(samples['teams']['away']['score'])
    rows = []

    def add(contract, values, line, side='over', inclusive=False):
        values = np.asarray(values)
        if values.shape != base.shape or not np.isfinite(values).all():
            raise ValueError('Invalid market draws')
        if inclusive:
            win = values >= line
            push = np.zeros(len(base), dtype=bool)
        else:
            push = np.isclose(values, line, rtol=0, atol=1e-10)
            win = ((values > line) if side == 'over' else (values < line)) & ~push
        p = float(base[win].sum())
        outcomes = {name: {'win': float(w[win].sum()), 'push': float(w[push].sum()),
                           'loss': float(w[~win & ~push].sum())} for name, w in stresses.items()}
        worst = min(outcomes, key=lambda name: outcomes[name]['win'])
        rows.append({'contract': contract, 'champion': {'win': p, 'push': float(base[push].sum()),
                     'loss': float(base[~win & ~push].sum())}, 'stress_scenarios': outcomes,
                     'adverse_scenario': worst, 'adverse_delta': outcomes[worst]['win']-p,
                     'first_td_challenger': {'status': 'unsupported_market', 'probability': None}})

    for side, margin in [('home', h-a), ('away', a-h)]:
        add({'kind': 'moneyline', 'side': side, 'tie': 'separate_push_mass'}, margin, 0)
    for row in forecast['totals']:
        for side in ['over', 'under']:
            add({'kind': 'total', 'line': row['line'], 'side': side}, h+a, row['line'], side)
    for row in forecast['spreads']:
        for side, margin, line in [('home', h-a, row['home_line']), ('away', a-h, -row['home_line'])]:
            add({'kind': 'spread', 'line': line, 'side': side}, margin+line, 0)
    for team_side, lines in forecast['team_totals'].items():
        for row in lines:
            for side in ['over', 'under']:
                add({'kind': 'team_total', 'team_side': team_side, 'side': side, 'line': row['line']},
                    samples['teams'][team_side]['score'], row['line'], side)
    for team, players in forecast['players'].items():
        for player in players:
            draws = samples['players'][team][player['player_id']]
            ladders = {**player['ladders'], 'tds': [{'at_least': 1}, {'at_least': 2}]}
            for stat, lines in ladders.items():
                for row in lines:
                    line = row['at_least']
                    add({'kind': 'player', 'team': team, 'player_id': player['player_id'],
                         'stat': stat, 'at_least': line, 'participation': 'assumed'}, draws[stat], line, inclusive=True)
    return {'version': VERSION, 'status': 'executed_shadow', 'independent_model': False,
            'calibrated': False, 'promotion_approved': False, 'scenario_strength': STRENGTH,
            'event_id': forecast['event_id'], 'contracts': rows,
            'scenario_effective_sample_size': {k: float(1/np.dot(w,w)) for k,w in stresses.items()},
            'first_td': {'status': 'unsupported_draw_order',
                         'reason': 'Champion final-score draws do not establish touchdown ordering.'},
            'quotes_verified': False,
            'limits': ['Stress tilts are declared assumptions, not fitted scenario probabilities.',
                       'Same Champion draws; no independent third-model agreement claim.',
                       'Threshold ladders are research contracts, not verified sportsbook offerings.',
                       'Tie/push mass requires bookmaker-specific settlement rules.']}
