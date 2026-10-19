import base64
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from gh_evidence import payload
from retrieve_evidence import historical_records

def row():
    return {"fixture_id":"one","tour":"WTA","name_a":"Test A","name_b":"Test B",
            "issued_at":"2026-10-19T00:00:00+00:00",
            "starts_at":"2026-10-20T12:00:00+00:00",
            "commit":"a"*40,"results":{"champion":{"status":"ok","p_a":0.6}}}

class Reader:
    def __init__(self,receipt="2026-10-19T01:00:00Z",primary=False):
        self.path,self.body,_=payload([row()],"123")
        self.receipt=receipt;self.primary=primary
    def api(self,method,route):
        if "/git/trees/" in route:
            if "tennis-evidence" in route and not self.primary:
                return {"truncated":False,"tree":[]}
            return {"truncated":False,"tree":[{"path":self.path,"type":"blob"}]}
        if route.startswith("/contents/"):
            return {"encoding":"base64","content":base64.b64encode(self.body).decode()}
        if route.startswith("/commits?"):
            return [{"commit":{"committer":{"date":self.receipt}}}]
        raise ValueError(route)

class EvidenceReadbackTests(unittest.TestCase):
    def test_uses_mirror_after_primary_missing(self):
        result=historical_records(Reader(),now=datetime(2026,10,21,tzinfo=timezone.utc))
        self.assertEqual(result["source"],"scan-results")
        self.assertEqual(len(result["forecasts"]),1)
    def test_server_receipt_after_start_disqualifies_backdated_forecast(self):
        with self.assertRaisesRegex(RuntimeError,"ALL_EVIDENCE_READ_PATHS_UNAVAILABLE"):
            historical_records(Reader(receipt="2026-10-20T13:00:00Z",primary=True),
                               now=datetime(2026,10,21,tzinfo=timezone.utc))
    def test_digest_mismatch_blocks_records(self):
        reader=Reader(primary=True)
        reader.body=b'{"tampered":true}'
        with self.assertRaisesRegex(RuntimeError,"ALL_EVIDENCE_READ_PATHS_UNAVAILABLE"):
            historical_records(reader,now=datetime(2026,10,21,tzinfo=timezone.utc))
if __name__=="__main__":unittest.main()
