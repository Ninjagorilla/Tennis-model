import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from forecast_ledger import extract,append,stable_id

SHA="a"*40
def example():
    match={"tour":"WTA","tournament_key":"osaka","regime":"main",
           "starts_at":"2026-11-01T12:00:00Z","name_a":"Player A","name_b":"Player B",
           "results":{}}
    for role in ("champion","challenger","experimental"):
        match["results"][role]={"status":"ok","p_a":0.65,"p_b":0.35,
                                "model_id":role,"state_date":"2026-10-05",
                                "artifact_sha256":"a"*64}
    return {"prediction_status":"available","generated_at":"2026-10-30T11:00:00Z","matches":[match]}

class LedgerTests(unittest.TestCase):
    def test_capture_orientation_and_provenance(self):
        r=extract(example(),"2026-10-30T12:00:00Z",SHA)
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]["results"]["champion"]["p_a"],0.65)
        self.assertEqual(r[0]["name_a"],"Player A")
        self.assertEqual(r[0]["commit"],SHA)
    def test_after_start_is_not_recorded(self):
        self.assertEqual(extract(example(),"2026-11-01T12:00:00Z",SHA),[])
    def test_nan_fails_closed(self):
        d=example();d["matches"][0]["results"]["champion"]["p_a"]=float("nan")
        with self.assertRaises(ValueError):extract(d,"2026-10-30T12:00:00Z",SHA)
    def test_blocked_scan_rejected(self):
        d=example();d["prediction_status"]="blocked"
        with self.assertRaises(ValueError):extract(d,"2026-10-30T12:00:00Z",SHA)
    def test_repeat_append_idempotent(self):
        r=extract(example(),"2026-10-30T12:00:00Z",SHA)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"ledger.jsonl"
            append(p,r);append(p,r)
            self.assertEqual(len(p.read_text().splitlines()),1)
    def test_identity_is_order_independent(self):
        row=example()["matches"][0];other=copy.deepcopy(row)
        other["name_a"],other["name_b"]=row["name_b"],row["name_a"]
        self.assertEqual(stable_id(row),stable_id(other))
    def test_invalid_sha_rejected(self):
        with self.assertRaises(ValueError):extract(example(),"2026-10-30T12:00:00Z","unverified")

if __name__=="__main__":unittest.main()
