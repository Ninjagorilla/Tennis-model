import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from verify_rollback import check_rollback
SHA="69d997c4c6a1f8765f05014fdb6a898d8701bd91"
class RollbackTests(unittest.TestCase):
 def test_same_registered_models_allow_rollback(self):
  x=check_rollback(SHA,reader=lambda commit,path:b"immutable-data:"+path.encode())
  self.assertTrue(x["approved"]);self.assertEqual(x["reason"],"IMMUTABLE_MODEL_FILES_MATCH")
 def test_changed_champion_rejected(self):
  def read(commit,path):
   if commit==SHA and path=="engine/manifest.json":return b"old model"
   return b"current model"
  x=check_rollback(SHA,reader=read)
  self.assertFalse(x["approved"]);self.assertIn("engine/manifest.json",x["mismatches"])
 def test_reject_ambiguous_branch_names(self):
  x=check_rollback("main",reader=lambda a,b:b"")
  self.assertFalse(x["approved"]);self.assertEqual(x["reason"],"EXPLICIT_FULL_COMMIT_SHA_REQUIRED")
 def test_unavailable_commit_rejected(self):
  def fail(a,b):raise ValueError("MISSING")
  self.assertFalse(check_rollback(SHA,reader=fail)["approved"])
if __name__=="__main__":unittest.main()
