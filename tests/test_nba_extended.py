import unittest
from unittest.mock import Mock
from nba_engine.player_sim import Player,simulate
from nba_engine.evaluation import grade,walk_forward
from nba_engine.providers import NBAStatProvider,ProviderError

class ExtendedTests(unittest.TestCase):
    def test_sim_deterministic(self):
        p=[Player("7","Example",30,20,7,5,2)]
        a=simulate(p,{"7":{"points":18.5,"pra":29.5}},1000,123)
        self.assertEqual(a,simulate(p,{"7":{"points":18.5,"pra":29.5}},1000,123))
        self.assertTrue(0<=a["7"]["over_probability"]["points"]<=1)
    def test_duplicate_player_rejected(self):
        p=Player("7","Example",30,20,7,5,2)
        with self.assertRaises(ValueError):simulate([p,p],{},100)
    def test_grading(self):
        r=grade([{"game_id":"1","asof_utc":"2026-01-01T12:00:00Z","tipoff_utc":"2026-01-02T12:00:00Z","home_win_probability":.8}],
                [{"game_id":"1","home_won":True}])
        self.assertAlmostEqual(r["brier"],.04)
    def test_missing_outcome_not_silently_dropped(self):
        with self.assertRaises(ValueError):
            grade([{"game_id":"1","asof_utc":"2026-01-01T12:00:00Z",
                    "tipoff_utc":"2026-01-02T12:00:00Z","home_win_probability":.8}],[])
    def test_duplicate_outcome_not_overwritten(self):
        p=[{"game_id":"1","asof_utc":"2026-01-01T12:00:00Z",
            "tipoff_utc":"2026-01-02T12:00:00Z","home_win_probability":.8}]
        with self.assertRaises(ValueError):
            grade(p,[{"game_id":"1","home_won":True},{"game_id":"1","home_won":False}])
    def test_prediction_at_tipoff_forbidden(self):
        p=[{"game_id":"1","asof_utc":"2026-01-02T12:00:00Z",
            "tipoff_utc":"2026-01-02T12:00:00Z","home_win_probability":.8}]
        with self.assertRaises(ValueError):
            grade(p,[{"game_id":"1","home_won":True}])
    def test_no_holdout(self):
        with self.assertRaises(ValueError):walk_forward([],minimum_train=2)
    def test_token_required(self):
        from unittest.mock import patch
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(ProviderError):NBAStatProvider()
    def test_path_rejection(self):
        provider=NBAStatProvider(token="dummy")
        with self.assertRaises(ValueError):provider.get("/../secrets")

if __name__=="__main__":unittest.main()
