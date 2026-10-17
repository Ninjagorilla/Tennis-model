from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,copy
import pytest
from nfl.research import canonical,save
from nfl.paper import grade,read_freeze,score

@pytest.fixture
def frozen():
    p={'__unknown__:BUF':.2,'BUF|p1':.6,'__no_touchdown__':.2}
    g={'event_id':'2026_06_NYJ_BUF','home':'BUF','away':'NYJ','starts_at':'2026-10-18T17:00:00+00:00',
       'game':{'home_win':.5,'away_win':.49,'tie':.01},'first_td':{'game':{'probabilities':p,'baseline_probabilities':p}}}
    return {'schema':'nfl-paper-freeze-1','evidence_class':'PREGAME_TWO_SOURCE_PAPER','created_at_utc':'2026-10-17T10:00:00+00:00',
            'model_parameter_sha256':'a'*64,'first_td_parameter_sha256':'b'*64,'games':[g]}

def write(path,p):save(path,{'payload':p,'sha256':hashlib.sha256(canonical(p)).hexdigest()})

def labels():return [{'game_id':'2026_06_NYJ_BUF','home':'BUF','away':'NYJ','home_score':21,'away_score':14,
                     'game_first':{'player_id':'p1','team':'BUF'}}]

def test_modified_freeze_rejected(tmp_path,frozen):
    f=tmp_path/'forecast_one.json';write(f,frozen);v=json.loads(f.read_text());v['payload']['games'][0]['home']='ATL';save(f,v)
    with pytest.raises(ValueError,match='Changed'):read_freeze(f)

def test_offline_not_prospective(tmp_path,frozen):
    frozen['evidence_class']='LOCAL_SNAPSHOT_TIME_UNVERIFIED';f=tmp_path/'forecast_one.json';write(f,frozen)
    assert read_freeze(f) is None

def test_pregame_required(tmp_path,frozen):
    frozen['created_at_utc']='2026-10-19T10:00:00+00:00';f=tmp_path/'forecast_one.json';write(f,frozen)
    assert read_freeze(f)['games']==[]

def test_earliest_forecast_once(tmp_path,frozen):
    write(tmp_path/'forecast_1.json',frozen);v=copy.deepcopy(frozen);v['created_at_utc']='2026-10-17T11:00:00+00:00';write(tmp_path/'forecast_2.json',v)
    s=grade(tmp_path,labels(),tmp_path/'out');assert s['unique_games_graded']==1 and s['parameter_game_pairs_graded']==1
    r=json.loads((tmp_path/'out/grades.json').read_text())['rows'][0]['result'];assert r['forecast_at_utc']==frozen['created_at_utc']
    assert r['game_winner']['outcome']=='home'

def test_pending_preserves_bytes(tmp_path,frozen):
    write(tmp_path/'forecast_1.json',frozen);s=grade(tmp_path,[],tmp_path/'out');assert s['pending_games']==1 and s['unique_games_graded']==0
    f=list((tmp_path/'out').glob('forecast_*'))[0];assert f.read_bytes()==(tmp_path/'forecast_1.json').read_bytes()

def test_missing_player_residual(tmp_path,frozen):
    write(tmp_path/'forecast_1.json',frozen);r=labels();r[0]['game_first']['player_id']='new'
    grade(tmp_path,r,tmp_path/'out');d=json.loads((tmp_path/'out/grades.json').read_text())['rows'][0]['result']
    assert d['first_td']['game']['outcome']=='__unknown__:BUF'

def test_invalid_distribution():
    with pytest.raises(ValueError):score({'a':.5},'a')
    with pytest.raises(ValueError):score({'a':float('nan')},'a')

def test_prior_ledger_retained(tmp_path,frozen):
    write(tmp_path/'forecast_1.json',frozen);grade(tmp_path,labels(),tmp_path/'out')
    s=grade(tmp_path/'out',[],tmp_path/'next');assert s['unique_games_graded']==1 and not s['publication_approved']
