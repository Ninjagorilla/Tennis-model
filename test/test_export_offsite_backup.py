import base64
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from export_offsite_backup import export

RAW=b'{"verified":"tennis evidence"}'
SHA=hashlib.sha256(RAW).hexdigest()
PATH="evidence/forecasts/2026/10/19/1/"+SHA+".json"
class BackupTests(unittest.TestCase):
    def test_verified_zip_contains_original_bytes_and_manifest(self):
        def read(route):
            if "/git/trees/" in route:return {"truncated":False,"tree":[{"type":"blob","path":PATH}]}
            return {"encoding":"base64","content":base64.b64encode(RAW).decode()}
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"offline.zip"
            r=export(read,out)
            self.assertEqual(r["status"],"verified")
            with zipfile.ZipFile(out) as z:
                self.assertEqual(z.read(PATH),RAW)
                self.assertEqual(json.loads(z.read("manifest.json"))["files"][PATH],SHA)
    def test_corrupt_primary_falls_back_to_verified_mirror(self):
        def read(route):
            if "/git/trees/" in route:return {"truncated":False,"tree":[{"type":"blob","path":PATH}]}
            if "tennis-evidence" in route:return {"encoding":"base64","content":base64.b64encode(b"tampered").decode()}
            return {"encoding":"base64","content":base64.b64encode(RAW).decode()}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(export(read,Path(d)/"b.zip")["branch"],"scan-results")
    def test_both_corrupt_fail_closed(self):
        def read(route):
            if "/git/trees/" in route:return {"truncated":False,"tree":[{"type":"blob","path":PATH}]}
            return {"encoding":"base64","content":base64.b64encode(b"tampered").decode()}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,"OFFLINE_BACKUP_UNAVAILABLE"):
                export(read,Path(d)/"b.zip")
if __name__=="__main__":unittest.main()
