"""Exact standard-scoring probability recursion, conditional on match completion.

No Monte Carlo counts, retirement assumptions, or post-hoc scoreline reweighting.
Server order carries between sets. A deciding-set tiebreak may target 7 or 10.
"""
from __future__ import annotations
import numpy as np
from numba import njit

@njit(cache=True)
def hold(p):
    q=1-p
    return p**4*(1+4*q+10*q*q)+20*p**3*q**3*(p*p/(p*p+q*q))

@njit(cache=True)
def tiebreak(pa,pb,first,target=7):
    # At a tied deuce stage each next pair contains one serve from each player.
    a=pa*(1-pb);b=(1-pa)*pb
    tail=a/(a+b)
    dp=np.zeros((target+2,target+2))
    for i in range(target,-1,-1):
        for j in range(target,-1,-1):
            if i>=target and i-j>=2: dp[i,j]=1.;continue
            if j>=target and j-i>=2: continue
            if i==j and i>=target-1: dp[i,j]=tail;continue
            k=i+j
            s=first if k==0 or ((k-1)//2)%2==1 else 1-first
            p=pa if s==0 else 1-pb
            dp[i,j]=p*dp[i+1,j]+(1-p)*dp[i,j+1]
    return dp[0,0]

@njit(cache=True)
def set_kernel(pa,pb,target=7):
    # [initial server, winner, next server, total games]
    out=np.zeros((2,2,2,14));ha=hold(pa);hb=hold(pb)
    for first in range(2):
        mass=np.zeros((8,8));mass[0,0]=1.
        for total in range(13):
            for a in range(8):
                b=total-a
                if b<0 or b>7:continue
                m=mass[a,b]
                if m==0:continue
                server=(first+total)%2
                if a>=6 and a-b>=2:out[first,0,server,total]+=m;continue
                if b>=6 and b-a>=2:out[first,1,server,total]+=m;continue
                if a==6 and b==6:
                    t=tiebreak(pa,pb,server,target)
                    out[first,0,1-server,13]+=m*t;out[first,1,1-server,13]+=m*(1-t);continue
                p=ha if server==0 else 1-hb
                if a<7:mass[a+1,b]+=m*p
                if b<7:mass[a,b+1]+=m*(1-p)
    return out

@njit(cache=True)
def distribution(pa,pb,best_of=3,deciding_target=7):
    needed=best_of//2+1
    normal=set_kernel(pa,pb,7)
    final=normal if deciding_target==7 else set_kernel(pa,pb,deciding_target)
    dp=np.zeros((needed+1,needed+1,2)); eg=np.zeros_like(dp);no_tb=np.zeros_like(dp)
    dp[0,0,0]=.5;dp[0,0,1]=.5;no_tb[0,0,0]=.5;no_tb[0,0,1]=.5
    scores=np.zeros((needed+1,needed+1));expected=0.;any_tb=0.
    for total in range(best_of+1):
        for a in range(needed+1):
            b=total-a
            if b<0 or b>needed:continue
            for server in range(2):
                m=dp[a,b,server]
                if m==0:continue
                if a==needed or b==needed:
                    scores[a,b]+=m;expected+=eg[a,b,server];any_tb+=m-no_tb[a,b,server];continue
                k=final if a==needed-1 and b==needed-1 else normal
                for w in range(2):
                    na=a+(w==0);nb=b+(w==1)
                    for ns in range(2):
                        for games in range(6,14):
                            pr=k[server,w,ns,games]
                            dp[na,nb,ns]+=m*pr
                            eg[na,nb,ns]+=(eg[a,b,server]+m*games)*pr
                            if games!=13:no_tb[na,nb,ns]+=no_tb[a,b,server]*pr
    return scores,expected,any_tb

@njit(cache=True)
def match_p(pa,pb,best_of=3,deciding_target=7):
    scores,_,_=distribution(pa,pb,best_of,deciding_target)
    return np.sum(scores[best_of//2+1,:])

@njit(cache=True)
def batch_match(eta_a,eta_b,best_of,targets,scale=1.,form=None,beta=0.):
    ans=np.empty(len(eta_a))
    for i in range(len(ans)):
        common=(eta_a[i]+eta_b[i])/2
        advantage=(eta_a[i]-eta_b[i])/2*scale
        if form is not None:advantage+=beta*form[i]
        pa=1/(1+np.exp(-common-advantage));pb=1/(1+np.exp(-common+advantage))
        ans[i]=match_p(pa,pb,int(best_of[i]),int(targets[i]))
    return ans

def predict_distribution(pa:float,pb:float,best_of:int=3,deciding_target:int=7):
    if not all(np.isfinite(x) and 0<x<1 for x in (pa,pb)):raise ValueError('invalid_service_probability')
    if best_of not in (3,5) or deciding_target not in (7,10):raise ValueError('unsupported_match_format')
    scores,expected,tb=distribution(pa,pb,best_of,deciding_target)
    needed=best_of//2+1
    return {'p_a':float(scores[needed,:].sum()),'p_b':float(scores[:,needed].sum()),
            'scorelines':{f'{i}-{j}':float(scores[i,j]) for i in range(needed+1) for j in range(needed+1) if (i==needed)^(j==needed)},
            'expected_total_games':float(expected),'p_at_least_one_tiebreak':float(tb),
            'conditional_on_completion':True,'settlement_model':'not_inferred'}
