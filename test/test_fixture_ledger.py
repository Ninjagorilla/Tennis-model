import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import fixture_ledger as ledger
from import_order_of_play import parse_paste
import scan
import import_order_of_play as importer

NOW = datetime(2026,10,21,7,tzinfo=timezone.utc)

def context(url='https://www.atptour.com/en/scores/current/example/schedule'):
    return {'source_url':url,'observed_at':NOW.isoformat(),'reviewer':'test reviewer',
            'tour':'ATP','regime':'main','tournament':'Example Open','tournament_key':'example-2026',
            'surface':'Hard','round':'R16','source_event_id':'source-event-1','best_of':3,
            'deciding_tiebreak_target':7,'surface_source':url,'format_source':url,
            'local_date':'2026-10-21','venue_timezone':'America/Los_Angeles',
            'players':{'Player Alpha':'source-player-a','Player Beta':'source-player-b',
                       'Player Gamma':'source-player-c','Player Delta':'source-player-d'},
            'match_ids':{'Player Alpha vs Player Beta':'source-match-1'},
            'complete_buckets':[{'tour':tour,'utc_date':day,'whole_tour_date_reviewed':True}
                                for day in ('2026-10-21','2026-10-22') for tour in ledger.TOURS]}

def document(text='10:00 | Player Alpha | Player Beta | match-1', full=True):
    a=context();b=context('https://www.tennis.com/tournaments/example')
    if not full: a['complete_buckets']=[];b['complete_buckets']=[]
    return {'schema_version':1,'sources':[parse_paste(text,c,NOW) for c in (a,b)]}

class ImportTests(unittest.TestCase):
    def test_paste_converts_venue_time_across_utc_date(self):
        source=parse_paste('8:30 PM | Player Alpha | Player Beta | match-1',context(),NOW)
        row=source['fixtures'][0]
        self.assertEqual(row['starts_at'],'2026-10-22T03:30:00+00:00')
        self.assertEqual(row['event_source'],context()['source_url'])
        self.assertEqual(row['source_player_ids'],['source-player-a','source-player-b'])
    def test_multiline_and_versus_text(self):
        for text in ('Starts At 10:00\nPlayer Alpha\nVs\nPlayer Beta','10:00 Player Alpha vs Player Beta'):
            self.assertEqual(len(parse_paste(text,context(),NOW)['fixtures']),1)
    def test_unknown_line_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_PASTE_FORMAT'):
            parse_paste('10:00 Player Alpha vs Player Beta\nUnparsed match',context(),NOW)
    def test_ambiguous_times_and_players_rejected(self):
        for text in ('Followed by Player Alpha vs Player Beta','Not before 10:00 Player Alpha vs Player Beta',
                     '10:00 | Qualifier | Player Beta | id','10:00 | Player Alpha | Player Alpha | id'):
            with self.subTest(text=text),self.assertRaises(ValueError): parse_paste(text,context(),NOW)
    def test_bad_date_timezone_gap_and_fold(self):
        for day,clock,zone in [('2026-03-08','02:30','America/Los_Angeles'),
                               ('2026-11-01','01:30','America/Los_Angeles'),
                               ('2026-02-30','10:00','UTC')]:
            with self.assertRaises(ValueError):ledger.local_start(day,clock,zone)
    def test_empty_requires_confirmed_zero(self):
        with self.assertRaises(ValueError):parse_paste('',context(),NOW)
        ctx=context();ctx['confirmed_empty']=True
        self.assertEqual(parse_paste('',ctx,NOW)['fixtures'],[])
    def test_duplicate_row_rejected(self):
        with self.assertRaises(ValueError):parse_paste('10:00 Player Alpha vs Player Beta\n10:00 Player Alpha vs Player Beta',context(),NOW)
    def test_untrusted_url_rejected(self):
        for url in ('http://www.atptour.com/schedule','https://atptour.com.evil.test/', 'https://localhost/', 'https://www.atptour.com:8443/'):
            with self.assertRaises(ValueError):parse_paste('10:00 Player Alpha vs Player Beta',context(url),NOW)
    def test_unsupported_scoring_formats_remain_withheld(self):
        for field,value in [('best_of',5),('deciding_tiebreak_target',10)]:
            ctx=context();ctx[field]=value
            with self.assertRaises(ValueError):parse_paste('10:00 Player Alpha vs Player Beta',ctx,NOW)

class CoverageTests(unittest.TestCase):
    def check(self,doc,now=NOW):return ledger.evaluate(doc,ledger.window('2026-10-21'),now)
    def test_complete_includes_explicit_zero_tour_date_counts(self):
        rows,report=self.check(document())
        self.assertEqual(report['status'],'COMPLETE');self.assertEqual(len(rows),1)
        self.assertEqual(len(report['counts']),8)
        self.assertTrue(any(r['source_counts']=={'ATP':0,'TENNIS_COM':0} for r in report['counts']))
    def test_october21_pacific_october22_only_failure(self):
        doc=document('10:00 | Player Alpha | Player Beta | match-1\n20:00 | Player Gamma | Player Delta | match-2')
        doc['sources'][1]['fixtures']=doc['sources'][1]['fixtures'][1:]
        rows,report=self.check(doc)
        self.assertEqual(report['window']['utc_dates'],['2026-10-21','2026-10-22'])
        self.assertEqual(report['status'],'PARTIAL');self.assertEqual(len(rows),1)
        count=next(r for r in report['counts'] if r['tour']=='ATP' and r['utc_date']=='2026-10-21')
        self.assertEqual(count['source_counts'],{'ATP':1,'TENNIS_COM':0})
        self.assertIn('SOURCE_COUNT_MISMATCH',count['reasons'])
    def test_missing_date_receipt_not_zero(self):
        doc=document();doc['sources'][1]['complete_buckets']=[r for r in doc['sources'][1]['complete_buckets'] if r['utc_date']=='2026-10-22']
        rows,report=self.check(doc)
        self.assertEqual(report['status'],'PARTIAL')
        self.assertIsNone(report['counts'][0]['source_counts']['TENNIS_COM'])
    def test_equal_counts_with_different_matches_are_unverified(self):
        doc=document();doc['sources'][1]['fixtures'][0]['name_b']='Player Delta'
        rows,report=self.check(doc)
        self.assertEqual(rows,[]);self.assertEqual(report['status'],'FAILED')
    def test_same_publisher_is_not_two_sources(self):
        doc=document();doc['sources'][1]=copy.deepcopy(doc['sources'][0])
        self.assertEqual(self.check(doc)[1]['status'],'FAILED')
    def test_stale_future_invalid_or_empty_sources_fail(self):
        variants=[{'schema_version':1,'sources':[]},None]
        for field,value in [('observed_at',(NOW-timedelta(hours=13)).isoformat()),
                            ('observed_at',(NOW+timedelta(hours=1)).isoformat()),('reviewer',''),('paste_sha256','bad')]:
            doc=document();doc['sources'][0][field]=value;variants.append(doc)
        for doc in variants:
            rows,report=self.check(doc);self.assertEqual(rows,[]);self.assertEqual(report['status'],'FAILED')
    def test_dst_window_lengths(self):
        for day,hours in [('2026-03-08',23),('2026-11-01',25)]:
            w=ledger.window(day)
            self.assertEqual((ledger.stamp(w['end_utc'])-ledger.stamp(w['start_utc'])).total_seconds(),hours*3600)
    def test_half_open_window_excludes_next_pacific_midnight(self):
        doc=document()
        for source in doc['sources']:
            row=source['fixtures'][0];row.update(local_date='2026-10-22',local_time='00:00',starts_at='2026-10-22T07:00:00+00:00')
        self.assertEqual(self.check(doc)[0],[])
    def test_past_matches_count_but_are_not_predicted(self):
        rows,report=self.check(document(),NOW+timedelta(hours=11))
        self.assertEqual(rows,[]);self.assertEqual(report['status'],'FAILED')
        self.assertEqual(report['counts'][0]['verified_count'],1)

class ScanLedgerTests(unittest.TestCase):
    def test_collector_has_no_automatic_or_legacy_fallback(self):
        import collect
        with tempfile.TemporaryDirectory() as tmp:
            previous=os.getcwd()
            try:
                os.chdir(tmp);Path('data').mkdir()
                Path('data/manual_challenger_fixtures.json').write_text(json.dumps([{'legacy':'fixture'}]))
                with patch.object(collect,'discover',side_effect=AssertionError('network fallback')):
                    rows,report=collect.collect(NOW,ledger.window('2026-10-21'))
                self.assertEqual(rows,[]);self.assertEqual(report['status'],'FAILED')
            finally:os.chdir(previous)
    def test_failed_assembly_preserves_previous_ledger(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.json';output=root/'ledger.json';report=root/'report.json'
            source.write_text(json.dumps(document()['sources'][0]));output.write_text('previous ledger')
            argv=['import_order_of_play.py','assemble','--sources',str(source),'--start-date','2026-10-21','--output',str(output),'--report',str(report)]
            with patch.object(sys,'argv',argv),patch.object(importer,'datetime',SimpleNamespace(now=lambda _:NOW)),redirect_stdout(io.StringIO()),patch('sys.stderr',new_callable=io.StringIO):
                with self.assertRaises(SystemExit):importer.main()
            self.assertEqual(output.read_text(),'previous ledger')
            self.assertEqual(json.loads(report.read_text())['status'],'FAILED')
    def run_scan(self,doc,recheck=None):
        now=NOW
        first=ledger.evaluate(doc,ledger.window('2026-10-21'),now)
        second=ledger.evaluate(recheck if recheck is not None else doc,ledger.window('2026-10-21'),now)
        with tempfile.TemporaryDirectory() as tmp:
            previous=os.getcwd()
            try:
                os.chdir(tmp)
                checks={r:{'passed':4,'total':4} for r in scan.ROLES}
                result={'p_a':.6,'p_b':.4,'model_id':'test','state_date':'2026-10-05','artifact_sha256':'a'*64,'research_only':True}
                output={r:{i:{'result':result} for i,_ in enumerate(first[0])} for r in scan.ROLES}
                with patch.object(scan,'collect',side_effect=[first,second]),patch.object(scan,'utc',return_value=now),patch.object(scan,'stage') as stage,patch.object(scan,'preflight',return_value=checks),patch.object(scan,'execute',return_value=output) as execute,redirect_stdout(io.StringIO()):
                    scan.scan()
                    saved=json.loads(Path('work/snapshot.json').read_text())
                    return saved,stage.call_count,execute.call_count
            finally:os.chdir(previous)
    def test_empty_or_one_source_never_stages_or_predicts(self):
        one=document();one['sources']=one['sources'][:1]
        for doc in ({'schema_version':1,'sources':[]},one):
            saved,staged,executed=self.run_scan(doc)
            self.assertEqual((staged,executed),(0,0));self.assertEqual(saved['scan_status'],'FAILED');self.assertEqual(saved['matches'],[])
    def test_verified_ledger_executes_and_reports_complete(self):
        saved,_,executed=self.run_scan(document())
        self.assertEqual(executed,1);self.assertEqual(saved['scan_status'],'COMPLETE');self.assertEqual(len(saved['matches']),1)
        from verify_scan import verify
        self.assertEqual(verify(saved)[0],[])
    def test_failed_second_observation_withholds_all_results(self):
        saved,_,executed=self.run_scan(document(),{'schema_version':1,'sources':[]})
        self.assertEqual(executed,1);self.assertEqual(saved['matches'],[]);self.assertEqual(saved['scan_status'],'FAILED')
    def test_partial_only_predicts_independently_verified_rows(self):
        doc=document();doc['sources'][1]['complete_buckets']=[]
        saved,_,executed=self.run_scan(doc)
        self.assertEqual(executed,1);self.assertEqual(saved['scan_status'],'PARTIAL');self.assertTrue(saved['coverage']['reasons'])

if __name__=='__main__':unittest.main()
