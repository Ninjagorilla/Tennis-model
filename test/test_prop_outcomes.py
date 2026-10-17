import pytest,pandas as pd
from nfl.prop_outcomes import actuals,threshold
def sample():
 b=dict(game_id='2026_06_NYJ_BUF',home_team='BUF',away_team='NYJ',total_home_score=21,total_away_score=14,pass_attempt=0,complete_pass=0,passing_yards=0,receiving_yards=0,rushing_yards=0,passer_player_id=None,receiver_player_id=None,rusher_player_id=None,rush_attempt=0,touchdown=0,pass_touchdown=0,rush_touchdown=0,td_player_id=None,play_type='pass',play_deleted=0,two_point_attempt=0,extra_point_attempt=0,sack=0,posteam='BUF')
 return pd.DataFrame([dict(b,play_id=1,pass_attempt=1,complete_pass=1,passing_yards=19,receiving_yards=19,passer_player_id='qb',receiver_player_id='wr',pass_touchdown=1,td_player_id='wr'),dict(b,play_id=2,rush_attempt=1,rushing_yards=11,rusher_player_id='rb',play_type='run'),dict(b,play_id=3,pass_attempt=1,passer_player_id='qb',receiver_player_id='wr')])
def test_player_stats():
 stats,played=actuals(sample(),'BUF','NYJ',(21,14))
 assert stats['BUF|qb']['pass_attempts']==2
 assert stats['BUF|qb']['completions']==1
 assert stats['BUF|qb']['passing_tds']==1
 assert stats['BUF|wr']['targets']==2
 assert stats['BUF|wr']['receptions']==1
 assert stats['BUF|rb']['rushing_yards']==11
 assert 'NYJ|missing' not in played
def test_disallow_conflicting_scores_and_nullified_plays():
 with pytest.raises(ValueError):actuals(sample(),'BUF','NYJ',(20,14))
 f=sample();f.loc[1,'play_deleted']=1
 stats,_=actuals(f,'BUF','NYJ',(21,14));assert 'BUF|rb' not in stats
def test_binary_calibration_is_not_sportsbook_settlement():
 assert threshold(.7,19,20)['hit']==0
 assert threshold(.7,20,20)['hit']==1
 assert threshold(.5,20,20)['brier']==.25
 with pytest.raises(ValueError):threshold(1.5,12,10)
