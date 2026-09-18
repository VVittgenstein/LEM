"""Inspectable probability laws and spatial correlation fits."""
import numpy as np
from scipy import stats, special
from scipy.optimize import minimize_scalar

def fit_positive(x, groups=None):
    x=np.asarray(x,float);x=x[np.isfinite(x)&(x>0)]
    if len(x)<5: raise ValueError('At least five positive reference values required')
    z=np.log(x);groups=np.arange(len(x)) if groups is None else np.asarray(groups)
    unique=np.unique(groups);scores=[]
    for name,dist in [('lognormal',stats.lognorm),('gamma',stats.gamma),('weibull',stats.weibull_min)]:
        ll=[]
        for g in unique:
            tr=x[groups!=g];te=x[groups==g]
            if len(tr)<3:continue
            try:
                p=dist.fit(tr,floc=0);ll.extend(dist.logpdf(te,*p))
            except (ValueError,FloatingPointError): ll.append(-1e6)
        p=dist.fit(x,floc=0)
        scores.append(dict(family=name,parameters=list(map(float,p)),cv_log_density=float(np.mean(ll))))
    bandwidths=np.geomspace(max(.05,float(z.std())*.15),max(.1,float(z.std())*1.2),20)
    for h in bandwidths:
        ll=[]
        for g in unique:
            tr=z[groups!=g];te=x[groups==g]
            a=-.5*((np.log(te)[:,None]-tr)/h)**2
            ll.extend(special.logsumexp(a,axis=1)-np.log(len(tr)*h*np.sqrt(2*np.pi))-np.log(te))
        scores.append(dict(family='log_kde',bandwidth=float(h),log_centers=z.tolist(),cv_log_density=float(np.mean(ll))))
    best=max(scores,key=lambda p:p['cv_log_density'])
    best={**best,'n':len(x),'training_values':x.tolist(),'candidates':scores,
          'validation':'held-out reference group log predictive density; spatial blocks for DS5',
          'scope':'conditional reference population, no claim of independent geological events'}
    return best

def cdf(x,m):
    a=np.asarray(x,float)
    if m['family']=='log_kde':
        return np.mean(stats.norm.cdf((np.log(np.maximum(a[...,None],1e-300))-m['log_centers'])/m['bandwidth']),axis=-1)
    return {'lognormal':stats.lognorm,'gamma':stats.gamma,'weibull':stats.weibull_min}[m['family']].cdf(a,*m['parameters'])

def ppf(q,m):
    q=np.clip(np.asarray(q,float),1e-7,1-1e-7)
    if m['family']=='log_kde':
        z=np.asarray(m['log_centers']);h=m['bandwidth'];grid=np.linspace(z.min()-6*h,z.max()+6*h,4097)
        c=np.mean(stats.norm.cdf((grid[:,None]-z)/h),axis=1)
        return np.exp(np.interp(q,c,grid))
    return {'lognormal':stats.lognorm,'gamma':stats.gamma,'weibull':stats.weibull_min}[m['family']].ppf(q,*m['parameters'])

def normal_scores(x):
    return stats.norm.ppf((stats.rankdata(x)-.5)/len(x))

def fit_correlation(sequences, maxlag, unit):
    """Variograms of normal scores; one contribution per source per bin."""
    edges=np.linspace(0,maxlag,9);targets=[];lags=[];counts=[]
    for lo,hi in zip(edges[:-1],edges[1:]):
        contributions=[];distances=[];npairs=0
        for s,z in sequences:
            s=np.asarray(s);z=np.asarray(z)
            d=abs(s[:,None]-s[None,:]);diff=.5*(z[:,None]-z[None,:])**2
            ok=(d>lo)&(d<=hi)&np.triu(np.ones_like(d,bool),1)
            if ok.any():contributions.append(float(diff[ok].mean()));distances.append(float(d[ok].mean()));npairs+=int(ok.sum())
        if contributions:targets.append(float(np.mean(contributions)));lags.append(float(np.mean(distances)));counts.append(npairs)
    h=np.asarray(lags);target=np.asarray(targets)
    def loss(l):return float(np.mean((1-np.exp(-.5*(h/np.exp(l))**2)-target)**2))
    opt=minimize_scalar(loss,bounds=(np.log(maxlag/100),np.log(maxlag*3)),method='bounded')
    ell=float(np.exp(opt.x))
    return dict(family='squared_exponential',length=ell,unit=unit,lags=h.tolist(),variogram=target.tolist(),
      model_variogram=(1-np.exp(-.5*(h/ell)**2)).tolist(),pairs=counts,rmse=float(np.sqrt(opt.fun)),
      at_upper_bound=bool(ell>maxlag*2.9),assumption='stationary normal-score correlation; long-distance behavior is model extrapolation')

def survival(x,family,p):
    x=np.maximum(np.asarray(x,float),0)
    if family=='weibull': return np.exp(-np.log(2)*x**p)
    if family=='loglogistic': return 1/(1+x**p)
    if family=='linear':return np.maximum(1-x/2,0)
    raise ValueError(family)

def compact_profile(r,p,family,cutoff=.05,rounding=.02):
    """Finite profile: fitted shape plus an explicitly supplied tail closure.

    A positive monotone coordinate warp removes the point singularity at r=0;
    the final 10% is a C1 Hermite join to zero with a flat boundary tangent.
    """
    r=np.clip(np.asarray(r,float),0,1);p=np.asarray(p,float)
    def base(t):
        # Round the powered distance itself: quadratic behavior at the origin
        # for every p>0, including exponents below one half.
        powered=((t*t+rounding**2)**(p/2)-rounding**p)/((1+rounding**2)**(p/2)-rounding**p)
        v=np.exp(-np.log(1/cutoff)*powered) if family=='weibull' else 1/(1+(1/cutoff-1)*powered)
        return (v-cutoff)/(1-cutoff)
    y=base(r);join=.9;v=base(join);eps=1e-5;der=(base(join+eps)-base(join-eps))/(2*eps)
    slope=np.maximum(der,-3*v/(1-join));t=np.clip((r-join)/(1-join),0,1)
    tail=(2*t**3-3*t*t+1)*v+(t**3-2*t*t+t)*(1-join)*slope
    y=np.where(r>join,tail,y)
    return np.where(r>=1,0,np.maximum(y,0))
