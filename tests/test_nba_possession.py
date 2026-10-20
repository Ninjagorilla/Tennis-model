import unittest
from nba_engine.possession_sim import Actor,simulate_game,summarize
from nba_engine.calibration import rolling_shadow,fit_platt,apply_platt

def roster(prefix):
    return [Actor(prefix+str(i),48,1,.50,.36,.35,1,1) for i in range(5)]

class PossessionTests(unittest.TestCase):
    def test_conservation_and_determinism(self):
        a=simulate_game(roster("h"),roster("a"),70,20,42)
        self.assertEqual(a,simulate_game(roster("h"),roster("a"),70,20,42))
        for game in a:
            self.assertEqual(sum(v.get("points",0) for k,v in game["players"].items() if k.startswith("h")),game["home_score"])
            self.assertEqual(sum(v.get("points",0) for k,v in game["players"].items() if k.startswith("a")),game["away_score"])
            self.assertLessEqual(sum(v.get("assists",0) for v in game["players"].values()),140)
        self.assertEqual(summarize(a,{"h0":{"points":10.5}})["iterations"],20)
    def test_bad_minutes(self):
        r=roster("h")
        from dataclasses import replace
        r[0]=replace(r[0],minutes=47)
        with self.assertRaises(ValueError):simulate_game(r,roster("a"))
    def test_calibration_requires_history(self):
        with self.assertRaises(ValueError):fit_platt([])
        rows=[{"tipoff_utc":f"2026-01-{i+1:02d}T00:00:00Z","raw_probability":.6,
               "home_won":i%2} for i in range(10)]
        with self.assertRaises(ValueError):rolling_shadow(rows)

if __name__=="__main__":unittest.main()
