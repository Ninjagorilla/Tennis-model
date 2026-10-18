import copy
import numpy as np
import pytest
from nfl.devils_advocate import analyze, stress_weights


def fixture():
    samples={'weights':np.array([.2,.3,.5]),'teams':{'home':{'score':np.array([0,7,14])},'away':{'score':np.array([7,7,0])}},
             'players':{'H':{'p':{'receptions':np.array([0,1,2]),'tds':np.array([0,1,1])}}}}
    forecast={'event_id':'test','totals':[{'line':14}], 'spreads':[{'home_line':0}],
              'team_totals':{'home':[{'line':7}]}, 'players':{'H':[{'player_id':'p','ladders':{'receptions':[{'at_least':1}]}}]}}
    return samples,forecast


def test_conservation_and_no_mutation():
    s,f=fixture();before=copy.deepcopy(s);report=analyze(s,f)
    assert np.array_equal(s['weights'],before['weights'])
    assert report['independent_model'] is False and report['calibrated'] is False
    assert report['first_td']['status']=='unsupported_draw_order'
    for r in report['contracts']:
        assert sum(r['champion'].values())==pytest.approx(1)
        for v in r['stress_scenarios'].values():assert sum(v.values())==pytest.approx(1)
        assert r['first_td_challenger']['probability'] is None
    ml=report['contracts'][0]
    assert ml['champion']==pytest.approx({'win':.5,'push':.3,'loss':.2})
    assert ml['stress_scenarios']['home_margin_low']['win']<.5
    assert ml['stress_scenarios']['home_margin_high']['win']>.5


def test_inclusive_props_have_no_push():
    s,f=fixture();rows=analyze(s,f)['contracts']
    r=next(x for x in rows if x['contract'].get('stat')=='receptions')
    assert r['champion']==pytest.approx({'win':.8,'push':0,'loss':.2})
    assert {r['contract']['kind'] for r in rows}=={'moneyline','total','spread','team_total','player'}


@pytest.mark.parametrize('weights',[[.2,.3,.4],[-.1,.4,.7],[float('nan'),0,1]])
def test_invalid_weights_fail(weights):
    s,_=fixture();s['weights']=np.array(weights)
    with pytest.raises(ValueError):stress_weights(s)


def test_zero_variance():
    s,_=fixture();s['teams']['home']['score'][:]=7;s['teams']['away']['score'][:]=7
    for w in stress_weights(s).values():assert np.array_equal(w,s['weights'])
