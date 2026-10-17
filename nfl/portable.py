"""Read-only, numeric JSON bridge for the recovered NFL-v9.1 engine.

No pickle loading, deserialization code execution, or model substitution in the
scheduled service. Array equality and prediction parity are tested separately.
"""
from __future__ import annotations
import copy,json,hashlib
from pathlib import Path
import numpy as np
from scipy.special import expit

class NumericModel:
    def __init__(self,spec):
        self.s=spec
        for field in ['coef','intercept','scale']:
            if not np.isfinite(np.asarray(spec[field],float)).all():raise ValueError('Nonfinite model parameters')
        if np.any(np.asarray(spec['scale'])<=0):raise ValueError('Invalid scale')
    def decision_function(self,x):
        x=np.asarray(x,float)
        if self.s.get('with_mean',False):x=x-np.asarray(self.s['mean'])
        x=x/np.asarray(self.s['scale'])
        return x@np.asarray(self.s['coef']).reshape(-1)+float(self.s['intercept'])
    def predict(self,x):
        z=self.decision_function(x)
        if self.s['link']!='exp':raise ValueError('Only Poisson prediction is supported here')
        return np.exp(z)
    def predict_proba(self,x):
        if self.s['link']!='logit':raise ValueError('Only logistic class probabilities are supported here')
        p=expit(self.decision_function(x));return np.column_stack([1-p,p])

def load_numeric(path):
    raw=json.loads(Path(path).read_text());b=copy.deepcopy(raw['bundle'])
    b['models']={k:NumericModel(s) for k,s in b['models'].items()}
    b['ml']=NumericModel(b['ml']);b['calibrator']=NumericModel(b['calibrator'])
    if b['version']!='NFL-v9.1-integrated-1':raise ValueError('Unexpected original model identity')
    return b

def export_original(bundle):
    def pipeline(m,link):
        scaler,est=m.steps[0][1],m.steps[-1][1]
        return {'link':link,'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),'with_mean':scaler.with_mean,
                'coef':np.asarray(est.coef_).reshape(-1).tolist(),'intercept':float(np.asarray(est.intercept_).reshape(-1)[0])}
    c=bundle['calibrator'];b={k:v for k,v in bundle.items() if k not in ['models','ml','calibrator']}
    b['models']={k:pipeline(m,'exp') for k,m in bundle['models'].items()};b['ml']=pipeline(bundle['ml'],'logit')
    b['calibrator']={'link':'logit','mean':[0.],'scale':[1.],'with_mean':False,'coef':c.coef_.reshape(-1).tolist(),'intercept':float(c.intercept_[0])}
    return {'schema':'nfl-v9.1-numeric-bridge-1','original_parameter_identity':'NFL-v9.1-integrated-1','bundle':b}
