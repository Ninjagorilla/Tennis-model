import unittest,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from recovery_controller import retry,evaluate
class RecoveryTests(unittest.TestCase):
 def test_recovers_after_one_failure(self):
  attempts=[]
  def scan():
   attempts.append(1)
   if len(attempts)==1:raise RuntimeError("SCAN_PROCESS_FAILED")
   return {"fixture_count":7}
  called=[]
  ok,r=retry(scan,lambda:called.append(1),pause=lambda _:None)
  self.assertTrue(ok);self.assertEqual(len(attempts),2);self.assertFalse(called)
 def test_bounded_and_backup_never_labeled_live(self):
  c=[]
  def fail():c.append(1);raise RuntimeError("SCAN_PROCESS_FAILED")
  ok,r=retry(fail,lambda:{"status":"verified_backup","matches":4})
  self.assertFalse(ok);self.assertEqual(len(c),2);self.assertEqual(r["status"],"degraded")
  self.assertEqual(r["backup"]["status"],"verified_backup")
 def test_offline_backup_reports_unavailable(self):
  ok,r=retry(lambda:(_ for _ in ()).throw(RuntimeError("SCANNER_FAILED")),
             lambda:(_ for _ in ()).throw(RuntimeError("NO_BACKUP")))
  self.assertFalse(ok);self.assertEqual(r["backup"]["status"],"unavailable")
 def test_invalid_retry_count(self):
  for count in (0,3,50):
   with self.assertRaises(ValueError):retry(lambda:None,lambda:None,attempts=count)
 def test_no_feed_failure_is_not_success(self):
  now=datetime.now(timezone.utc).isoformat()
  d={"schema_version":2,"prediction_status":"unavailable","generated_at":now,
     "models":[{"id":k,"predictions":0,"preflight":{"passed":4,"total":4}} for k in ("champion","challenger","experimental")],
     "matches":[],"coverage":{"sources":[{"status":"unavailable"}]}}
  errors,_=evaluate(d);self.assertIn("ALL_FIXTURE_SOURCES_UNAVAILABLE",errors)
 def test_healthy_http_feed_does_not_verify_empty_ledger(self):
  now=datetime.now(timezone.utc).isoformat()
  d={"schema_version":2,"prediction_status":"unavailable","generated_at":now,
     "models":[{"id":k,"predictions":0,"preflight":{"passed":4,"total":4}} for k in ("champion","challenger","experimental")],
     "matches":[],"coverage":{"sources":[{"status":"ok"}]}}
  errors,_=evaluate(d);self.assertIn('FAILED_OR_MISSING_LEDGER_GATE',errors)
if __name__=="__main__":unittest.main()
