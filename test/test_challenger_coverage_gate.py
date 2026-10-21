import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from challenger_coverage_gate import assess
class CoverageTests(unittest.TestCase):
 def test_empty(self):self.assertTrue(assess({"matches":[]})["challenger_missing"])
 def test_main_only(self):self.assertTrue(assess({"matches":[{"tour":"ATP","regime":"main"}]})["challenger_missing"])
 def test_present(self):self.assertFalse(assess({"matches":[{"tour":"ATP","regime":"challenger"}]})["challenger_missing"])
 def test_source_down(self):self.assertTrue(assess({"matches":[{"regime":"challenger"}],"coverage":{"unavailable_scopes":["ATP Challenger"]}})["challenger_missing"])
if __name__=="__main__":unittest.main()
