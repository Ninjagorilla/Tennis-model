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
if __name__=='__main__':unittest.main()
