import sys,unittest,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from verify_fixture_receipts import verify_receipts
from challenger_independent_sources import sources_for,probe
from datetime import date
class ReceiptTests(unittest.TestCase):
 def test_real_bytes_checked_and_opponents_found(self):
  data=b"<html><body>Alpha Player vs Beta Player Hard singles</body></html>"
  sha=hashlib.sha256(data).hexdigest()
  row={"name_a":"Alpha Player","name_b":"Beta Player","independent_receipts":[
   {"url":"https://www.atptour.com/test","sha256":sha},
   {"url":"https://en.tennistemple.com/test","sha256":sha}]}
  self.assertTrue(verify_receipts(row,lambda url:data))
 def test_changed_page_fails_closed(self):
  row={"name_a":"Alpha Player","name_b":"Beta Player","independent_receipts":[
   {"url":"https://www.atptour.com/test","sha256":"a"*64}]}
  with self.assertRaisesRegex(ValueError,"SOURCE_CONTENT_CHANGED"):
   verify_receipts(row,lambda _:b"<html>Alpha Player vs Beta Player</html>")
 def test_one_opponent_missing_fails(self):
  data=b"<html>Alpha Player vs Other Player</html>"
  row={"name_a":"Alpha Player","name_b":"Beta Player","independent_receipts":[
   {"url":"https://www.atptour.com/test","sha256":hashlib.sha256(data).hexdigest()}]}
  with self.assertRaisesRegex(ValueError,"PLAYER_ABSENT_FROM_SOURCE"):
   verify_receipts(row,lambda _:data)
 def test_tournament_urls_follow_requested_date(self):
  links=sources_for(date(2026,10,21))
  self.assertIn("2026-10-21",links["tennistemple"])
  self.assertIn("day=21",links["tennisexplorer"])
  self.assertIn("month=10",links["tennisexplorer"])
if __name__=="__main__":unittest.main()
