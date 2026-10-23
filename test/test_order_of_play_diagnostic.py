import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_order_of_play import probe, inspect_html, diagnose, SafeRedirect
from fixture_ledger import window

class Response(io.BytesIO):
    def __init__(self,body,code=200,content_type='text/html'):
        super().__init__(body);self.code=code;self.headers={'Content-Type':content_type}
    def geturl(self):return 'https://www.atptour.com/schedule'

class DiagnosticsTests(unittest.TestCase):
    def test_http_success_without_rows_not_ingestible(self):
        result,_=probe('https://www.atptour.com/schedule',lambda *a,**k:Response(b'<html>Loading Order Of Play</html>'))
        self.assertEqual(result['status_code'],200)
        self.assertFalse(result['match_rows_present']);self.assertFalse(result['automatic_ingestion_verified'])
        self.assertEqual(result['content_length'],len(b'<html>Loading Order Of Play</html>'))
    def test_http_error_records_body_length(self):
        def blocked(*args,**kwargs):
            raise urllib.error.HTTPError('https://www.atptour.com/schedule',403,'Forbidden',{'Content-Type':'text/html'},io.BytesIO(b'blocked'))
        result,_=probe('https://www.atptour.com/schedule',blocked)
        self.assertEqual(result['status_code'],403);self.assertEqual(result['content_length'],7)
        self.assertIsNone(result['match_rows_present'])
    def test_timeout_and_pdf_are_not_empty_slates(self):
        def timeout(*a,**k):raise TimeoutError('timed out')
        self.assertEqual(probe('https://www.atptour.com/schedule',timeout)[0]['outcome'],'FETCH_FAILED')
        result,_=probe('https://www.atptour.com/schedule',lambda *a,**k:Response(b'%PDF',content_type='application/pdf'))
        self.assertIsNone(result['match_rows_present'])
    def test_visible_match_signals_and_navigation_only(self):
        html='<a href="/players/a">Player Alpha</a><span>Vs</span><a href="/players/b">Player Beta</a>'
        self.assertEqual(inspect_html(html)[0],1)
        self.assertEqual(inspect_html('<nav>Scores Schedule Players</nav>')[0],0)
    def test_structured_match_rows(self):
        html='<script type="application/json">'+json.dumps({'matches':[{'competitors':[{'id':'a'},{'id':'b'}],'startDate':'2026-10-21'}]})+'</script>'
        self.assertEqual(inspect_html(html)[0],1)
    def test_nextjs_rows_after_unrelated_documents(self):
        payload='0:'+json.dumps({'navigation':[]})+'\n1:'+json.dumps({'initialMatches':[{'id':'match-1'}]})+'\n'
        html='<script>self.__next_f.push('+json.dumps([1,payload])+')</script>'
        self.assertEqual(inspect_html(html)[:2],(1,'TENNIS_COM_INITIAL_MATCHES'))
    def test_specific_event_does_not_follow_archived_years(self):
        requested=[]
        def fetch(url):requested.append(url);return {'url':url},['/2025/order-of-play']
        diagnose(['https://www.wtatennis.com/2026/order-of-play'],window('2026-10-21'),fetch)
        self.assertEqual(len(requested),1)
    def test_date_templates_fetch_every_overlapping_utc_day(self):
        requested=[]
        def fetch(url):requested.append(url);return {'url':url},[]
        diagnose(['https://www.tennis.com/?date={date}'],window('2026-10-21'),fetch)
        self.assertEqual(requested,['https://www.tennis.com/?date=2026-10-21','https://www.tennis.com/?date=2026-10-22'])
    def test_discovery_stays_on_publisher_and_is_bounded(self):
        requested=[]
        def fetch(url):
            requested.append(url)
            return {'url':url},[f'/en/{i}/daily-schedule' for i in range(10)]+['https://evil.test/order-of-play']
        diagnose(['https://www.atptour.com/scores'],window('2026-10-21'),fetch)
        self.assertEqual(len(requested),4)
    def test_redirect_cannot_escape_publisher(self):
        import urllib.request
        with self.assertRaises(ValueError):
            SafeRedirect().redirect_request(urllib.request.Request('https://www.atptour.com/'),None,302,'',{},'https://evil.test/')

if __name__=='__main__':unittest.main()
