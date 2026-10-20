import unittest
from nba_engine.core import Team, Game, scan

class TestNBAEngine(unittest.TestCase):
    def setUp(self):
        self.a=Team("Home",115,110,99,2,2,0,True)
        self.b=Team("Away",110,115,101,-2,1,0,True)
        self.game=Game("g1","2026-10-20T19:00:00Z",self.a,self.b,"2026-10-20T12:00:00Z")
    def test_probabilities_and_totals(self):
        r=scan(self.game)
        for key in ("champion","experimental","devils_advocate"):
            self.assertGreater(r[key]["home_win_probability"],0)
            self.assertLess(r[key]["home_win_probability"],1)
        self.assertGreater(r["champion"]["total"],150)
    def test_point_in_time_leakage(self):
        from dataclasses import replace
        with self.assertRaises(ValueError):
            scan(replace(self.game,asof_utc="2026-10-21T12:00:00Z"))
    def test_prediction_at_tipoff_is_leakage(self):
        from dataclasses import replace
        with self.assertRaises(ValueError):
            scan(replace(self.game,asof_utc=self.game.tipoff_utc))
    def test_nonfinite_input_rejected(self):
        from dataclasses import replace
        with self.assertRaises(ValueError):
            scan(replace(self.game,home=replace(self.a,net_rating_recent=float("nan"))))
    def test_bad_ratings_rejected(self):
        from dataclasses import replace
        with self.assertRaises(ValueError):
            scan(replace(self.game,home=replace(self.a,pace=0)))
    def test_adversary_stresses_favorite(self):
        r=scan(self.game)
        self.assertLess(r["devils_advocate"]["home_win_probability"],r["experimental"]["home_win_probability"])

if __name__=="__main__":
    unittest.main()
