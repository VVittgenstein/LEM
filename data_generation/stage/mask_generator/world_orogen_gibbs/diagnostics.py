"""Rank-normalized split R-hat and initial-positive-sequence bulk ESS.

All chains in a comparison must share the SAME fixed field and partition map.
Finite diagnostics provide evidence, not a proof of convergence.
"""
import numpy as np
from scipy.stats import rankdata,norm
from .sampler import METRICS


def _split(x):
    half=x.shape[1]//2
    return np.concatenate([x[:,:half],x[:,-half:]],axis=0)


def _rank(x):
    return norm.ppf((rankdata(x,method='average').reshape(x.shape)-.375)/(x.size+.25))


def _rhat(x):
    n=x.shape[1];within=np.var(x,axis=1,ddof=1).mean()
    between=n*np.var(x.mean(axis=1),ddof=1)
    if within<1e-30:return 1. if between<1e-30 else float('inf')
    return float(np.sqrt(((n-1)*within/n+between/n)/within))


def _ess(x):
    c,n=x.shape
    centered=x-x.mean(axis=1,keepdims=True)
    fft=np.fft.rfft(centered,n=2*n,axis=1)
    acov=np.fft.irfft(fft*fft.conj(),n=2*n,axis=1)[:,:n]/n
    within=np.var(x,axis=1,ddof=1).mean()
    varplus=(n-1)/n*within+np.var(x.mean(axis=1),ddof=1)
    if varplus<1e-30:return float(x.size)
    rho=1-(within-acov.mean(axis=0))/varplus;rho[0]=1.
    pairs=[]
    for t in range(0,n-1,2):
        pair=rho[t]+rho[t+1]
        if pair<0:break
        pairs.append(min(pair,pairs[-1] if pairs else pair))
    tau=max(1.,-1+2*sum(pairs))
    return float(min(x.size,x.size/tau))


def diagnose(statistics):
    rows=[]
    for index,name in enumerate(METRICS):
        values=statistics[:,:,index]
        z=_rank(_split(values))
        folded=_rank(_split(np.abs(values-np.median(values))))
        r=max(_rhat(z),_rhat(folded));ess=_ess(z)
        tails=[]
        for q in (.05,.95):
            tails.append(_ess(_split((values<=np.quantile(values,q)).astype(float))))
        rows.append(dict(metric=name,rhat=r if np.isfinite(r) else None,bulk_ess=ess,
            tail_ess=min(tails),constant=bool(np.ptp(values)==0),mean=float(values.mean()),
            chain_means=values.mean(axis=1).tolist(),passes=bool(np.isfinite(r) and r<=1.05 and ess>=100)))
    # Spatial occurrence per region checks stable shape/location, beyond global scores.
    return dict(method='rank-normalized split and folded R-hat; initial positive monotone sequence ESS',
                rhat_limit=1.05,minimum_bulk_ess=100,checks=rows,passed=all(r['passes'] for r in rows),
                interpretation='finite diagnostic evidence; not a convergence proof')


def spatial_diagnose(states,forbidden):
    # Restrict to variable bits; constants are recorded separately.
    r=[];constant=0
    for i in np.flatnonzero(~forbidden):
        x=states[:,:,i].astype(float)
        if not np.ptp(x):constant+=1;continue
        value=_rhat(_rank(_split(x)))
        r.append((int(i)+1,value if np.isfinite(value) else None))
    bad=[i for i,v in r if v is None or v>1.05]
    return dict(variable_regions=len(r),constant_regions=constant,
                maximum_rhat=max([v for i,v in r if v is not None],default=1.),
                failed_region_ids=bad,passed=not bad)
