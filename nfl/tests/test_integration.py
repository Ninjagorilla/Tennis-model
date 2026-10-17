from pathlib import Path
from datetime import datetime,timezone,timedelta
import copy,json,sys
import numpy as np
import pandas as pd
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'nfl'),str(ROOT/'nfl/engine')]
from nfl.research import first_label,valid_plays,history_summary,candidate_table,hazard_features,from_portable,distribution,metrics,unknown,outcome_id
from nfl.portable import load_numeric
from nfl.pipeline import public_status,verified,compact_forecast
from nfl_champion_v9.model import means
from nfl_champion_v9.engine import split,probability

@pytest.fixture
def record():
    p={'p1':{'name':'Player One','stats':[[1,4,2,3,20],[0,0,0,0,0]]},'p2':{'name':'Player Two','stats':[[0,0,0,0,0],[1,5,2,8,30]]}}
    state={'players':p,'team':[.8,1.5,.9,.2,.8,1.5,.9,.2],'last_date':'2026-10-01'}
    return {'home':'BUF','away':'NYJ','home_state':copy.deepcopy(state),'away_state':copy.deepcopy(state),'game_first':{'quarter':1,'team':'BUF','player_id':'p1','channel':'rush'}}

@pytest.fixture
def fitted():return from_portable(json.loads((ROOT/'nfl/first_td_parameters.json').read_text()))

def test_sequence_over_play_id():
    p=pd.DataFrame([{'play_id':999,'order_sequence':10,'qtr':1,'touchdown':1,'td_team':'BUF','td_player_id':'a','pass_touchdown':1,'rush_touchdown':0},
                    {'play_id':100,'order_sequence':20,'qtr':1,'touchdown':1,'td_team':'NYJ','td_player_id':'b','pass_touchdown':0,'rush_touchdown':1}])
    assert first_label(p)['player_id']=='a'
    assert first_label(p,'NYJ')['player_id']=='b'

def test_ambiguous_scoring_sequence_rejected():
    p=pd.DataFrame([{'play_id':i,'order_sequence':10,'qtr':1,'touchdown':1,'td_team':t,'td_player_id':t,'pass_touchdown':1,'rush_touchdown':0} for i,t in enumerate(['BUF','NYJ'])])
    with pytest.raises(ValueError,match='Ambiguous'):first_label(p)

def test_nullified_and_conversions():
    p=pd.DataFrame({'play_deleted':[0,1,0,0,0],'play_type':['pass','pass','no_play','pass','pass'],
                    'extra_point_attempt':[0,0,0,1,0],'two_point_attempt':[0,0,0,0,1]})
    assert len(valid_plays(p))==1

def test_quarter_risk_sets(fitted):
    assert len(fitted['game']['model'].classes_)==7
    assert len(fitted['team']['model'].classes_)==4

def test_unseen_scorer_residual(record,fitted):
    p=distribution(record,fitted,'game');lab={'player_id':'new-player','team':'BUF','channel':'rush'}
    assert metrics(p,lab)['observed_bucket']==unknown('BUF')

def test_trade_identity_not_merged(record):
    a=candidate_table(record,'BUF','rush')[0];b=candidate_table(record,'NYJ','rush')[0]
    assert set(a).isdisjoint(b)

def test_out_player_removed(record):
    ids,*_=candidate_table(record,'BUF','rush',{'p1':{'status':'out'}})
    assert ids==[unknown('BUF')]

def test_unknown_roster_new_player(record):
    ids,*_=candidate_table(record,'BUF','receive',{'new':{'status':'active'}})
    assert ids==[unknown('BUF')]

def test_outcome_cannot_change_features(record):
    a=hazard_features(record,1,'game');r=copy.deepcopy(record);r['game_first']={'quarter':5,'team':'NYJ','player_id':'new','channel':'other'}
    assert a==hazard_features(r,1,'game')

@pytest.mark.parametrize('market,team',[('game',None),('team','BUF'),('team','NYJ')])
@pytest.mark.parametrize('baseline',[False,True])
def test_complete_probabilities(record,fitted,market,team,baseline):
    p=distribution(record,fitted,market,team=team,baseline=baseline)
    assert sum(p.values())==pytest.approx(1,abs=1e-10)
    assert min(p.values())>=0
    assert '__no_touchdown__' in p
    if team:assert not any(k.startswith(('NYJ|' if team=='BUF' else 'BUF|')) for k in p)

@pytest.mark.parametrize('n',[1,2,20,100])
def test_random_mass_conservation(record,fitted,n):
    rng=np.random.default_rng(n)
    for _ in range(n):
        r=copy.deepcopy(record)
        r['home_state']['team']=(rng.random(8)*3).tolist();r['away_state']['team']=(rng.random(8)*3).tolist()
        assert sum(distribution(r,fitted,'game').values())==pytest.approx(1,abs=1e-10)

def test_live_fixture_contract():
    g={'home':'BUF','away':'NYJ','kickoff_utc':'2030-01-01T18:00:00+00:00'}
    e={('BUF','NYJ'):{'starts_at':'2030-01-01T18:00:00Z','state':'pre','completed':False}}
    assert verified(g,e)
    e[('BUF','NYJ')]['state']='in';assert not verified(g,e)
    assert not verified(g,{})

def test_kickoff_mismatch_rejected():
    g={'home':'BUF','away':'NYJ','kickoff_utc':'2030-01-01T18:00:00+00:00'}
    e={('BUF','NYJ'):{'starts_at':'2030-01-01T20:00:00Z','state':'pre','completed':False}}
    assert not verified(g,e)

def test_publication_stays_closed():
    s=public_status('verified',paper_games=16,games=[{'fake_probability':.99}])
    assert s['publication_approved'] is False and s['games']==[] and s['prediction_status']=='gated'
    assert s['validation']['prospective_games_graded']==0

def test_real_dataset_report():
    d=json.loads((ROOT/'nfl/evidence/dataset_report.json').read_text())
    assert d['verified_games']==1504 and d['exclusions']==[]
    assert all(r['verified']==r['scheduled_completed'] for r in d['coverage'])

def test_no_retroactive_promotion():
    d=json.loads((ROOT/'nfl/evidence/first_td_evaluation.json').read_text())
    assert d['promotion_approved'] is False
    assert d['results']['game']['games']==365
    assert d['results']['team']['contracts']==730

def test_original_parameter_identity():
    b=load_numeric(ROOT/'nfl/original_parameters.json')
    assert b['version']=='NFL-v9.1-integrated-1'
    assert b['protocol']['fit_seasons']==[2022,2023]
    assert b['protocol']['as_of']=='2026-10-01'

def test_preservation_receipt():
    r=json.loads((ROOT/'nfl/evidence/runtime_repair.json').read_text())
    assert r['original_files_checked']==123 and r['original_files_changed']==[]
    b=json.loads((ROOT/'nfl/evidence/numeric_bridge.json').read_text())
    assert b['feature_rows_compared']==1473 and b['parameter_bridge_max_mean_difference']==0

def test_original_count_math():
    counts=np.arange(50);draws=split(np.random.default_rng(1),counts,[.2,.3,.5],30)
    assert np.array_equal(draws.sum(axis=1),counts)
    assert probability(np.array([0,1,2]),np.array([.2,.3,.5]),1)=={'win':.5,'push':.3,'loss':.2}
