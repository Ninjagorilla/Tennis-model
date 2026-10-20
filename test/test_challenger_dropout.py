import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_challenger_dropout import audit
class ChallengerCoverageTests(unittest.TestCase):
 def test_expired_history_cannot_be_published_as_live(self):
  previous={"matches":[{"regime":"challenger","starts_at":"2026-10-20T18:30:00Z"}]}
  current={"generated_at":"2026-10-20T04:30:00Z","matches":[]}
  r=audit(current,previous)
  self.assertEqual(r["status"],"DEGRADED_CHALLENGER_COVERAGE")
  self.assertEqual(r["current_challenger_matches"],0)
 def test_no_false_dropout_when_challengers_are_not_future(self):
  previous={"matches":[{"regime":"challenger","starts_at":"2026-10-19T18:30:00Z"}]}
  current={"generated_at":"2026-10-20T04:30:00Z","matches":[]}
  self.assertEqual(audit(current,previous)["status"],"NO_TOTAL_CHALLENGER_DROPOUT_DETECTED")
if __name__=="__main__":unittest.main()
