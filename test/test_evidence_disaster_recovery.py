"""Disaster recovery simulation: no network, no model mutation, deterministic faults."""
import base64
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from evidence_resilience import repair

RAW=b'{"source":"verified research evidence","predictions":3}'
DIGEST=hashlib.sha256(RAW).hexdigest()
PATH="evidence/forecasts/2026/10/19/123/"+DIGEST+".json"
REPORT={"path":PATH,"sha256":DIGEST}

class FakeGitHub:
    def __init__(self,primary=True,mirror=True,blocked=(),tampered=()):
        self.docs={}
        for branch,present in (("tennis-evidence",primary),("scan-results",mirror)):
            if present:self.docs[(branch,PATH)]=b'corrupt' if branch in tampered else RAW
        self.blocked=set(blocked)
        self.calls=[]
    def api(self,method,route):
        assert method=="GET"
        branch=route.split("?ref=")[1]
        data=self.docs.get((branch,PATH))
        if data is None:return None
        return {"encoding":"base64","content":base64.b64encode(data).decode()}
    def save(self,branch,path,raw):
        self.calls.append((branch,path))
        if branch in self.blocked:raise RuntimeError("SIMULATED_GITHUB_OUTAGE")
        if (branch,path) in self.docs and self.docs[(branch,path)]!=raw:
            raise RuntimeError("NO_OVERWRITE")
        self.docs[(branch,path)]=raw
        return "verified"

class RecoveryDrills(unittest.TestCase):
    def test_primary_failure_repaired_from_mirror(self):
        c=FakeGitHub(primary=False)
        result=repair(REPORT,c)
        self.assertEqual(result["status"],"healthy")
        self.assertEqual(result["repaired"],["tennis-evidence"])
        self.assertFalse(result["alert"])
    def test_mirror_failure_repaired_from_primary(self):
        c=FakeGitHub(mirror=False)
        self.assertEqual(repair(REPORT,c)["verified"],2)
    def test_both_branches_lost_blocks_grading_and_recovery(self):
        c=FakeGitHub(primary=False,mirror=False)
        r=repair(REPORT,c)
        self.assertEqual(r["status"],"critical")
        self.assertEqual(c.calls,[])
    def test_primary_write_blocked_after_bounded_attempts(self):
        c=FakeGitHub(primary=False,blocked=("tennis-evidence",))
        r=repair(REPORT,c)
        self.assertEqual(r["status"],"degraded")
        self.assertTrue(r["alert"])
        self.assertEqual(len(c.calls),2)
    def test_corrupt_mirror_never_overwritten(self):
        c=FakeGitHub(tampered=("scan-results",))
        r=repair(REPORT,c)
        self.assertEqual(r["status"],"degraded")
        self.assertEqual(c.docs[("scan-results",PATH)],b"corrupt")
    def test_corrupt_primary_with_good_mirror_is_not_accepted(self):
        c=FakeGitHub(tampered=("tennis-evidence",))
        self.assertEqual(repair(REPORT,c)["status"],"degraded")
    def test_idempotent_both_good(self):
        c=FakeGitHub()
        self.assertEqual(repair(REPORT,c)["status"],"healthy")
        self.assertEqual(c.calls,[])
    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            repair({"path":"../"+PATH,"sha256":DIGEST},FakeGitHub())
    def test_digest_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            repair({"path":PATH,"sha256":"f"*64},FakeGitHub())
if __name__=="__main__":unittest.main()
