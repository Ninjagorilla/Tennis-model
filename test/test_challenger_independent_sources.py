import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from challenger_independent_sources import probe,SOURCES
class SourceProbeTests(unittest.TestCase):
 def test_third_party_mentions_never_become_forecasts(self):
  def reader(url):
   if "tennistemple" in url:return b"<html><body>Fort Worth Florence Guangzhou singles schedule</body></html>"
   if "tennisexplorer" in url:return b"<html><body>Florence challenger Fort Worth challenger Cali Lisbon</body></html>"
   return b"<html><script>Fort Worth Florence</script><body>ATP Tour</body></html>"
  r=probe(reader,observed_at="2026-10-19T20:00:00+00:00")
  self.assertTrue(r["sources"]["tennistemple"]["mentions"]["fort_worth"])
  self.assertTrue(r["sources"]["tennisexplorer"]["mentions"]["florence"])
  self.assertFalse(r["sources"]["official_atp"]["mentions"]["florence"])
  self.assertEqual(r["confirmed_live_fixtures"],[])
  self.assertFalse(r["probabilities_modified"])
 def test_partial_failure_is_explicit(self):
  def reader(url):
   if "tennisexplorer" in url:raise OSError("offline")
   return b"<html><body>Fort Worth Challenger</body></html>"
  r=probe(reader)
  self.assertEqual(r["sources"]["tennisexplorer"]["status"],"unavailable")
  self.assertTrue(r["sources"]["official_atp"]["mentions"]["fort_worth"])
  self.assertEqual(len(r["sources"]),3)
if __name__=="__main__":unittest.main()
