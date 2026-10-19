import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from gh_evidence import payload,archive,GitHub

def record():
    return {"fixture_id":"fixture","issued_at":"2026-10-19T00:00:00+00:00",
            "starts_at":"2026-10-20T00:00:00+00:00","commit":"a"*40,
            "results":{"champion":{"status":"ok","p_a":0.6}}}

class FakeClient:
    def __init__(self,fail=()):self.fail=set(fail);self.saved={}
    def save(self,branch,path,raw):
        if branch in self.fail:raise RuntimeError("BLOCKED_BACKEND")
        old=self.saved.get((branch,path))
        if old is not None and old!=raw:raise RuntimeError("IMMUTABLE_COLLISION")
        self.saved[(branch,path)]=raw
        return "existing" if old==raw else "verified"

class EvidenceTests(unittest.TestCase):
    def test_receipt_is_deterministic_and_sha_checked(self):
        path,raw,digest=payload([record()],123)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
        self.assertTrue(path.endswith(digest+".json"))

    def test_mirror_recovers_primary_failure(self):
        client=FakeClient(fail=("tennis-evidence",))
        report=archive([record()],123,client)
        self.assertTrue(report["remote_verified"])
        self.assertEqual(report["destinations"]["tennis-evidence"]["status"],"failed")
        self.assertEqual(report["destinations"]["scan-results"]["status"],"verified")

    def test_both_remote_destinations_fail_without_false_success(self):
        report=archive([record()],123,FakeClient(fail=("tennis-evidence","scan-results")))
        self.assertFalse(report["remote_verified"])
        self.assertEqual(report["artifact_backup"],"workflow_upload_required")

    def test_repeat_is_idempotent(self):
        client=FakeClient()
        archive([record()],123,client)
        result=archive([record()],123,client)
        self.assertEqual(result["destinations"]["tennis-evidence"]["status"],"existing")

    def test_empty_and_duplicate_rejected(self):
        with self.assertRaises(ValueError):payload([],123)
        with self.assertRaises(ValueError):payload([record(),record()],123)

if __name__=="__main__":unittest.main()
