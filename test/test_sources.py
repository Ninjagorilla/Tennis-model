import copy,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tenniscom import documents,matches,metadata,parse_match,full_name,match_espn_metadata
from collect import merge
from explanations import sanitize
class Sources(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2027,2,1,12,tzinfo=timezone.utc)
        self.meta={'slug':'test-open','name':'Test Open','officialName':None,'surface':'hard_indoor','tourLevel':'Challenger','location':'Test City, France','timezone':'Europe/Paris','startDate':'2027-02-01','endDate':'2027-02-07','competitions':[{'type':'singles','gender':'men','category':'Challenger'}]}
        self.row={'matchScoreKey':'sr:sport_event:123','status':'scheduled','startTimeConfirmed':True,'startTime':'2027-02-02T08:00:00Z','round':'Semifinal','eventCategory':"Men's Singles",'competitionGender':'men','competitionCategory':'Challenger','homeCompetitor':{'id':'player-one','name':'One, Player'},'awayCompetitor':{'id':'player-two','name':'Two, Player'},'homeWinProbability':99,'market_price':1.1}
    def event(self):return parse_match(self.row,metadata([self.meta],'test-open'),self.now,'https://www.tennis.com/?date=2027-02-02')
    def test_future_edition_needs_no_dated_configuration(self):
        e=self.event();self.assertEqual(e['regime'],'challenger');self.assertEqual(e['surface'],'Hard');self.assertEqual(e['name_a'],'Player One');self.assertNotIn('homeWinProbability',e);self.assertNotIn('market_price',e)
    def test_decode_literals_never_execute_javascript(self):
        payload='1:'+json.dumps({'initialMatches':[self.row]})+'\n';html='<script>self.__next_f.push('+json.dumps([1,payload])+')</script><script>throw new Error("do not execute")</script>'
        doc,_=documents(html);self.assertEqual(len(matches(doc)),1)
        with self.assertRaises(ValueError):documents('<script>self.__next_f.push(eval("danger"))</script>')
    def test_schema_drift_is_not_empty_success(self):
        with self.assertRaises(ValueError):matches([{'changedMatches':[]}])
    def test_unknown_surface_and_special_format_rejected(self):
        self.meta['surface']='carpet'
        with self.assertRaises(ValueError):metadata([self.meta],'test-open')
        self.meta['surface']='hard';self.meta['tourLevel']='Next Gen Finals'
        with self.assertRaises(ValueError):metadata([self.meta],'test-open')
    def test_conflicting_metadata_rejected(self):
        other=copy.deepcopy(self.meta);other['surface']='clay'
        with self.assertRaises(ValueError):metadata([self.meta,other],'test-open')
    def test_started_unconfirmed_doubles_and_placeholder_rejected(self):
        self.row['status']='live';self.assertIsNone(self.event());self.row['status']='scheduled'
        self.row['startTimeConfirmed']=False;self.assertIsNone(self.event());self.row['startTimeConfirmed']=True
        self.row['eventCategory']="Men's Doubles";self.assertIsNone(self.event())
        with self.assertRaises(ValueError):full_name({'id':'tbd','name':'TBD'})
    def test_stale_edition_rejected(self):
        self.meta['startDate']='2026-02-01';self.meta['endDate']='2026-02-07';self.assertIsNone(self.event())
    def test_duplicate_and_disagreement_handling(self):
        a=self.event();b=copy.deepcopy(a);b['source_match_id']='espn:123'
        self.assertEqual(len(merge([a,b])[0]),1)
        b['starts_at']='2027-02-02T09:00:00+00:00';self.assertEqual(merge([a,b]),([],1))
    def test_exact_location_join_requires_unique_edition(self):
        spec=metadata([self.meta],'test-open');e={'name':'Sponsor Test','venue':{'displayName':'Test City, France'},'date':'2027-02-01T00:00Z','endDate':'2027-02-07T23:59Z'}
        self.assertIsNotNone(match_espn_metadata(e,'ATP',[spec]));self.assertIsNone(match_espn_metadata(e,'ATP',[spec,spec]))
    def test_explanations_are_numeric_allowlist_only(self):
        self.assertEqual(sanitize('champion',{'sr_p_a':.6,'private':'secret','rating_a':float('nan'),'elo_weight':.4}),{'sr_p_a':.6,'elo_weight':.4})

class IngestionRecovery(unittest.TestCase):
    def setUp(self):
        self.meta={'slug':'atp-challenger-fort-worth-usa','name':'ATP Challenger Fort Worth, USA','officialName':None,'surface':'hard','tourLevel':'Challenger','location':None,'timezone':None,'year':2026,'startDate':'2026-10-18','endDate':'2026-10-25','competitions':[{'type':'singles','gender':'men','category':'Challenger'}]}
    def test_reviewed_null_location_and_timezone(self):
        old=copy.deepcopy(self.meta);m=metadata([self.meta],self.meta['slug'])
        self.assertEqual(m['timezone'],'America/Chicago');self.assertEqual(m['key'],'fort worth')
        self.assertEqual(m['metadata_supplement']['fields'],['location','timezone']);self.assertEqual(self.meta,old)
    def test_unknown_edition_has_no_default(self):
        for field,value in [('slug','unknown-open'),('startDate','2027-10-18'),('endDate','2026-10-26')]:
            with self.subTest(field=field):
                m=copy.deepcopy(self.meta);m[field]=value
                with self.assertRaisesRegex(ValueError,'LOCATION_METADATA_MISSING'):metadata([m],m['slug'])
    def test_conflicting_review_fails_closed(self):
        for field,value in [('location','Dallas, United States'),('timezone','UTC'),('surface','clay'),('name','Other Open'),('tourLevel','ATP 250'),('year',2027),('competitions',[{'type':'singles','gender':'women','category':'WTA'}])]:
            with self.subTest(field=field):
                m=copy.deepcopy(self.meta);m[field]=value
                with self.assertRaisesRegex(ValueError,'REVIEWED_EDITION_CONFLICT'):metadata([m],m['slug'])
    def test_provider_supplied_metadata_needs_no_supplement(self):
        self.meta.update(location='Fort Worth, United States',timezone='America/Chicago')
        self.assertIsNone(metadata([self.meta],self.meta['slug'])['metadata_supplement'])
    def test_timezone_conflict_across_nodes(self):
        other=copy.deepcopy(self.meta);other['timezone']='America/Chicago'
        with self.assertRaisesRegex(ValueError,'METADATA_CONFLICT'):metadata([self.meta,other],self.meta['slug'])
    def test_unknown_invalid_timezone_explicit(self):
        self.meta.update(slug='other',location='Paris, France',timezone='invalid/timezone')
        with self.assertRaisesRegex(ValueError,'TIMEZONE_METADATA_INVALID'):metadata([self.meta],'other')
        self.meta['timezone']=None
        with self.assertRaisesRegex(ValueError,'TIMEZONE_METADATA_MISSING'):metadata([self.meta],'other')
    def test_exact_wolf_alias_and_conflicts(self):
        p={'id':'jj-wolf','name':'Wolf, J.J.','countryCode':'USA'}
        self.assertEqual(full_name(p),'J J Wolf')
        for change in [{'id':'other-wolf'},{'name':'Wolf, John'},{'countryCode':'CAN'},{'countryCode':None}]:
            with self.subTest(change=change),self.assertRaises(ValueError):full_name(p|change)
    def test_score_objects_fail_closed(self):
        from tenniscom import unstarted_score
        blank={'currentSetNumber':None,'homeSetsWon':0,'awaySetsWon':0,'sets':[],'currentGame':None}
        for good in [None,{},blank]:self.assertTrue(unstarted_score(good))
        for bad in [[],False,0,'',blank|{'currentSetNumber':1},blank|{'sets':[{}]},blank|{'currentGame':{}},blank|{'homeSetsWon':False},blank|{'awaySetsWon':0.0},blank|{'newField':0},{'sets':[]}]:
            with self.subTest(bad=bad):self.assertFalse(unstarted_score(bad))
    def test_empty_score_does_not_override_live_started_or_unconfirmed(self):
        from tenniscom import unstarted_score
        case=Sources();case.setUp();case.row['score']={'currentSetNumber':None,'homeSetsWon':0,'awaySetsWon':0,'sets':[],'currentGame':None}
        self.assertIsNotNone(case.event())
        for change in [{'status':'live'},{'winnerId':'player-one'},{'startTimeConfirmed':False},{'startTime':'2027-02-01T11:00:00Z'}]:
            old=copy.deepcopy(case.row);case.row.update(change);self.assertIsNone(case.event());case.row=old
    def test_discovery_exposes_metadata_failure(self):
        from unittest.mock import patch
        from tenniscom import discover
        case=Sources();case.setUp();r=case.row|{'tournamentSlug':'test-open'};m=case.meta|{'location':None}
        def page(url):return url,{'url':url,'status':'ok'}
        def docs(html):return ([m] if html.endswith('/test-open') else [{'initialMatches':[r]}]),[]
        with patch('tenniscom.read',side_effect=page),patch('tenniscom.documents',side_effect=docs):
            events,_,diag=discover(case.now)
        self.assertEqual(events,[]);self.assertEqual(diag['metadata_failures']['test-open'],'LOCATION_METADATA_MISSING')
        self.assertEqual(len(diag['rejected_scheduled_matches']),1);self.assertEqual(diag['incomplete_scopes'],['Challenger'])
    def test_discovery_recovers_reviewed_wolf_without_manual_runner(self):
        from unittest.mock import patch
        from tenniscom import discover
        case=Sources();case.setUp();r=case.row|{'tournamentSlug':self.meta['slug'],'startTime':'2026-10-20T21:20:00Z','homeCompetitor':{'id':'jj-wolf','name':'Wolf, J.J.','countryCode':'USA'},'awayCompetitor':{'id':'tyler-zink','name':'Zink, Tyler'},'score':{'currentSetNumber':None,'homeSetsWon':0,'awaySetsWon':0,'sets':[],'currentGame':None}}
        def page(url):return url,{'url':url,'status':'ok'}
        def docs(html):return ([self.meta] if html.endswith('/'+self.meta['slug']) else [{'initialMatches':[r]}]),[]
        with patch('tenniscom.read',side_effect=page),patch('tenniscom.documents',side_effect=docs):
            events,_,diag=discover(datetime(2026,10,20,20,tzinfo=timezone.utc))
        self.assertTrue(events);self.assertTrue(all(e['player_a']=='ATP:j j wolf' for e in events));self.assertEqual(diag['rejected_scheduled_matches'],[])
        self.assertIn(self.meta['slug'],diag['metadata_supplements'])

if __name__=='__main__':unittest.main()
