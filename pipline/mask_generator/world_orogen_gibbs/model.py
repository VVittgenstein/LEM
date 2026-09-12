"""Explicit target law for nonempty subsets of eligible partitions."""
import numpy as np
from scipy.special import expit,logsumexp


def terms(state,g,field,settings):
    z=np.asarray(state,bool)
    if np.any(z & g.forbidden) or not z.any():
        return dict(total=float('inf'))
    a=float(g.areas@z);mx=float(g.mx@z);my=float(g.my@z)
    c=(mx*mx+my*my)/(a*a)
    r=float(g.m2@z)/a-c
    p=float(g.lengths@(z[g.edges[:,0]]!=z[g.edges[:,1]]))
    f=float((g.areas*field)@z)
    gap=max(settings.area_low-a,0.,a-settings.area_high)
    values=dict(area=settings.area_weight*.5*(gap/settings.area_softness)**2,
        center=settings.center_weight*c,spread=settings.spread_weight*r,
        perimeter=settings.perimeter_weight*p,field=-settings.field_weight*f)
    return dict(values,total=sum(values.values()),fraction=a,C=c,R=r,P=p,F=f)


def conditional(state,index,g,field,settings,temperature=None):
    if g.forbidden[index]: return 0.
    z=np.array(state,bool);z[index]=False
    e0=terms(z,g,field,settings)['total'];z[index]=True
    e1=terms(z,g,field,settings)['total']
    return float(expit((e0-e1)/(settings.temperature if temperature is None else temperature)))


def enumerate_distribution(g,field,settings):
    eligible=np.flatnonzero(~g.forbidden)
    if len(eligible)>20: raise ValueError('enumeration limited to 20 eligible bits')
    integers=np.arange(1,2**len(eligible),dtype=np.int64)
    states=np.zeros((len(integers),len(g.areas)),bool)
    states[:,eligible]=((integers[:,None] >> np.arange(len(eligible))) & 1).astype(bool)
    scores=np.array([terms(z,g,field,settings)['total'] for z in states])
    logits=-scores/settings.temperature
    return states,np.exp(logits-logsumexp(logits))
