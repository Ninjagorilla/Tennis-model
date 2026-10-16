import copy,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect import parse,fingerprint
from scan import project
class Gates(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,16,20,tzinfo=timezone.utc)
        self.c={'id':'1','date':'2026-10-17T09:00Z','timeValid':True,'status':{'type':{'state':'pre','name':'STATUS_SCHEDULED','completed':False}},'competitors':[{'id':'101','athlete':{'displayName':'Jelena Ostapenko'}},{'id':'102','athlete':{'displayName':'Iga Swiatek'}}]}
        self.config={'381-2026':{'tour':'WTA','from':'2026-10-12','through':'2026-10-18','key':'wuhan','regime':'main','surface':'Hard','source':'https://www.wtatennis.com/'}}
    def rows(self,c=None,slug='womens-singles',config=None):
        doc={'events':[{'id':'381-2026','name':'Wuhan','groupings':[{'grouping':{'slug':slug},'competitions':[c or self.c]}]}]}
        return parse(doc,'WTA',self.now,self.config if config is None else config)[0]
    def test_real_feed_id_shape_and_orientation(self):
        a=self.rows()[0];self.c['competitors'].reverse();b=self.rows()[0];self.assertEqual(fingerprint(a),fingerprint(b));self.assertEqual(a['player_a'],'WTA:jelena ostapenko')
    def test_reject_started_cancelled_unknown_time_doubles_and_unknown_surface(self):
        for name,state in [('STATUS_IN_PROGRESS','in'),('STATUS_CANCELED','pre'),('STATUS_FINAL','post')]:
            c=copy.deepcopy(self.c);c['status']['type'].update(name=name,state=state);self.assertEqual(self.rows(c),[])
        c=copy.deepcopy(self.c);c['timeValid']=False;self.assertEqual(self.rows(c),[])
        self.assertEqual(self.rows(slug='womens-doubles'),[]);self.assertEqual(self.rows(config={}),[])
    def test_past_and_far_future_excluded(self):
        for d in ['2026-10-16T19:00Z','2026-10-18T09:00Z']:
            c=copy.deepcopy(self.c);c['date']=d;self.assertEqual(self.rows(c),[])
    def test_qualifying_uses_registered_scope(self):
        self.c['round']={'displayName':'Qualifying 1st Round'}
        self.assertEqual(self.rows()[0]['regime'],'main_qualifying')
    def test_no_placeholder_player_or_private_worker_fields(self):
        c=copy.deepcopy(self.c);c['competitors'][0]['id']='-1';self.assertEqual(self.rows(c),[])
        r={'p_a':.6,'p_b':.4,'model_id':'test','state_date':'2026-10-05','artifact_sha256':'a'*64,'research_only':True,'private':'DO_NOT_PUBLISH'}
        self.assertNotIn('private',project({'result':r}));r['p_a']=float('nan');self.assertEqual(project({'result':r})['status'],'unavailable')
    def test_missing_worker_result_is_not_probability(self):self.assertEqual(project(None),{'status':'unavailable','reason':'EXECUTION_UNAVAILABLE'})
if __name__=='__main__':unittest.main()
