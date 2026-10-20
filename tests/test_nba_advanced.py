import unittest
from nba_engine.advanced import RotationPlayer,allocate_minutes,usage_shares,recency_projection,matchup_pace
from nba_engine.ledger import freeze_forecast

class AdvancedTests(unittest.TestCase):
    def test_injury_redistribution(self):
        ps=[RotationPlayer("a",30,25,False),RotationPlayer("b",30,20),RotationPlayer("c",20,10)]
        mins=allocate_minutes(ps)
        self.assertEqual(mins["a"],0)
        self.assertAlmostEqual(sum(mins.values()),240)
        self.assertAlmostEqual(sum(usage_shares(ps,mins).values()),1)
    def test_decay_lookahead(self):
        with self.assertRaises(ValueError):
            recency_projection([("2026-10-21T00:00:00Z",10)],"2026-10-20T00:00:00Z")
    def test_pace(self):
        self.assertGreater(matchup_pace(100,102,99),0)
    def test_market_firewall(self):
        forecast={"game_id":"x","asof_utc":"2026-10-20T12:00:00Z",
                  "tipoff_utc":"2026-10-20T19:00:00Z","home_win_probability":.6,
                  "market_home_probability":.7}
        evidence={"source":"official","retrieved_at_utc":"2026-10-20T11:00:00Z"}
        result=freeze_forecast(forecast,evidence,{"home":.7})
        self.assertNotIn("market_home_probability",result["frozen"]["forecast"])
        self.assertTrue(result["market_isolated"])

if __name__=="__main__":unittest.main()
