import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from reliability_dashboard import summarize,render

class DashboardTests(unittest.TestCase):
    def test_missing_reports_never_look_successful(self):
        r=summarize(None,None,None,None,None,None)
        self.assertEqual(r["archive_status"],"not_verified")
        self.assertIsNone(r["verified_settlements"])
        self.assertEqual(r["prospective_accuracy"],"not_established")
        self.assertIn("Not checked",render(r))
    def test_counts_only_actual_complete_three_model_fixtures(self):
        d={"prediction_status":"available","models":[{"id":"champion","predictions":2}],
           "matches":[{"results":{role:{"status":"ok"} for role in ("champion","challenger","experimental")}},
                      {"results":{"champion":{"status":"ok"},"challenger":{"status":"unavailable"},"experimental":{"status":"ok"}}}]}
        r=summarize(d,None,{"remote_verified":True},{"verified":2,"status":"healthy"},
                    {"health":[{"status":"ok"},{"status":"unavailable"}],"settlements":[{}],"exclusions":{"x":"NO_RESULT"}},None)
        self.assertEqual(r["three_model_coverage"],1)
        self.assertEqual(r["verified_settlements"],1)
        self.assertEqual(r["excluded_settlements"],1)
        self.assertEqual(r["provider_health"],{"healthy":1,"checked":2})
    def test_seven_day_metrics_are_read_only_and_not_imputed(self):
        weekly={"status":"verified_results","forecast_fixtures":12,"verified_settlements":2,
                "exclusion_reasons":{"MISSING_ONE_INDEPENDENT_PROVIDER":3},
                "paired":{"paired_by_tour":{"ATP":{"paired_fixtures":1}}},
                "model_decisions":{"champion":{"accuracy":0.5,"market_upsets_correct":None}}}
        result=summarize(None,None,None,None,None,None,None,weekly)
        self.assertEqual(result["seven_day_verified_results"],2)
        self.assertEqual(result["seven_day_paired_models"]["ATP"]["paired_fixtures"],1)
        self.assertFalse(result["champion_promoted"])
        self.assertIn("Seven-day verified settlements",render(result))
    def test_html_escapes_untrusted_source_values(self):
        result=summarize({"prediction_status":"<script>alert(1)</script>"},None,None,None,None,None)
        output=render(result)
        self.assertNotIn("<script>",output)
        self.assertIn("&lt;script&gt;",output)
if __name__=="__main__":unittest.main()
