"""Saved-evidence reporting must fail closed on tampering and scope confusion."""
import copy
import hashlib
import tempfile
from pathlib import Path
import unittest
from nfl.report_run import digest, verify, probabilities


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        names = ['nfl/engine/nfl_champion_v9/engine.py', 'nfl/original_parameters.json', 'nfl/first_td_parameters.json']
        h = hashlib.sha256(b'fixture').hexdigest()
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
        g = {'event_id': '2026_06_DAL_GB', 'starts_at': '2026-10-19T00:20:00+00:00', 'home': 'GB', 'away': 'DAL',
             'game': {'home_win': .4, 'away_win': .59, 'tie': .01},
             'first_td': {k: {'probabilities': {'scorer': .8, 'none': .2}} for k in ('game', 'GB', 'DAL')}}
        self.p = {'schema': 'nfl-paper-freeze-1', 'evidence_class': 'PREGAME_TWO_SOURCE_PAPER', 'created_at_utc': '2026-10-18T22:55:00+00:00',
                  'games': [g], 'code_hashes': {names[0]: h}, 'model_parameter_sha256': h, 'first_td_parameter_sha256': h,
                  'quotes_verified': False, 'promotion_approved': False}
        self.r = {'execution_status': 'verified', 'created_at_utc': self.p['created_at_utc'], 'paper_games': 1, 'public_forecasts': 0,
                  'quotes_verified': False, 'publication_approved': False,
                  'layers': {'champion': {'status': 'executed', 'games': 1, 'scope': 'game_lines_and_player_props'},
                             'challenger': {'status': 'executed', 'games': 1, 'scope': 'first_touchdown_only'}}}

    def check(self):
        self.r['freeze_sha256'] = digest(self.p)
        return verify({'payload': self.p, 'sha256': digest(self.p)}, self.r, self.root)

    def test_gated_execution_is_not_missing_execution(self):
        self.assertEqual(len(self.check()['games']), 1)

    def test_tampered_freeze(self):
        self.r['freeze_sha256'] = digest(self.p)
        with self.assertRaises(ValueError):
            verify({'payload': self.p, 'sha256': 'changed'}, self.r, self.root)

    def test_started_game_cannot_be_pregame(self):
        self.p['games'][0]['starts_at'] = self.p['created_at_utc']
        with self.assertRaises(ValueError): self.check()

    def test_wrong_challenger_scope(self):
        self.r['layers']['challenger']['scope'] = 'all_markets'
        with self.assertRaises(ValueError): self.check()

    def test_champion_change_rejected(self):
        (self.root / 'nfl/original_parameters.json').write_text('changed')
        with self.assertRaises(ValueError): self.check()

    def test_offline_not_pregame(self):
        self.p['evidence_class'] = 'LOCAL_SNAPSHOT_TIME_UNVERIFIED'
        with self.assertRaises(ValueError): self.check()

    def test_bad_probability_mass(self):
        for values in ([.6, .6], [float('nan'), .5], [True, 0], [-.1, 1.1]):
            with self.assertRaises(ValueError): probabilities(values)

    def test_duplicate_game_rejected(self):
        self.p['games'].append(copy.deepcopy(self.p['games'][0]))
        self.r['paper_games'] = 2
        with self.assertRaises(ValueError): self.check()

    def test_mismatched_receipt_time(self):
        self.r['created_at_utc'] = '2026-10-18T23:00:00+00:00'
        with self.assertRaises(ValueError): self.check()

    def test_release_cannot_be_inferred(self):
        self.r['publication_approved'] = True
        with self.assertRaises(ValueError): self.check()
