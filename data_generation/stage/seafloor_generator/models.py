"""Four fitted generative functions. No reference-row resampling or replay."""
from dataclasses import dataclass
import numpy as np
from scipy import stats
from scipy.optimize import minimize


@dataclass
class FittedFunctions:
    record: dict

    def environment(self,rng):
        """Function 1: multinomial fitted probabilities and a fresh uniform variate."""
        names=('all_shallow','mixed','all_deep')
        p=np.asarray(self.record['environment']['probabilities'])
        return names[min(2,int(np.searchsorted(np.cumsum(p),rng.random(),side='right')))]

    def mixed_deep_fraction(self,rng):
        """Function 2: a newly generated value of the fitted beta law."""
        r=self.record['mixed_ratio'];return float(rng.beta(r['alpha'],r['beta']))

    def deep_length(self,rng,size=None):
        """Function 3: fitted lognormal deep-run length, kilometres."""
        r=self.record['deep_length'];return rng.lognormal(r['mu_log_km'],r['sigma_log'],size=size)

    def shallow_length(self,rng,size=None):
        """Function 4: fitted lognormal shallow-run length, kilometres."""
        r=self.record['shallow_length'];return rng.lognormal(r['mu_log_km'],r['sigma_log'],size=size)


def fit_functions(landmasses,segments):
    names=('all_shallow','mixed','all_deep')
    counts=np.array([sum(r['regime']==k for r in landmasses) for k in names])
    ratios=np.array([r['deep_share_known_water'] for r in landmasses if r['regime']=='mixed'])
    if len(ratios)<3:raise ValueError('Insufficient mixed references to fit the ratio function')
    a,c,_,_=stats.beta.fit(ratios,floc=0,fscale=1)
    record=dict(environment=dict(family='multinomial MLE',classes=names,counts=counts.tolist(),
                                 probabilities=(counts/counts.sum()).tolist(),n=int(counts.sum())),
                mixed_ratio=dict(family='beta MLE',alpha=float(a),beta=float(c),n=len(ratios),
                                 mean=float(a/(a+c)),observed_mean=float(ratios.mean()),
                                 empirical_cdf_max_error=float(stats.kstest(ratios,'beta',args=(a,c)).statistic)),
                evidence_state='source-derived fitted models; family choices are engineering assumptions',
                generation='fresh random variates from fitted analytic functions; no observed row or quantile lookup')
    for typ in ('deep','shallow'):
        rows=[r for r in segments if r['used_for_fit'] and r['environment']==typ]
        if len(rows)<4:raise ValueError(f'Insufficient complete {typ} runs')
        x=np.array([r['length_km'] for r in rows]); log=np.log(x)
        censored=np.array([r['censored'] for r in rows],bool)
        if (~censored).sum()<4:raise ValueError(f'Insufficient complete {typ} observations for censored fitting')
        # Every reference landmass contributing this type has equal total weight.
        ids=[r['landmass_id'] for r in rows]; ns={k:ids.count(k) for k in set(ids)}
        weight=np.array([1/ns[k] for k in ids]);weight/=weight.sum()
        mu0=float(weight@log);sd0=max(.1,float(np.sqrt(weight@((log-mu0)**2))))
        def loss(params):
            mu,ls=params;sd=np.exp(ls)
            ll=np.where(censored,stats.lognorm.logsf(x,sd,scale=np.exp(mu)),stats.lognorm.logpdf(x,sd,scale=np.exp(mu)))
            return float(-weight@ll)
        fitted=minimize(loss,[mu0,np.log(sd0)],method='L-BFGS-B',bounds=[(np.log(.1),np.log(100000)),(np.log(.05),np.log(5.))])
        if not fitted.success:raise ValueError(f'Length fit failed: {fitted.message}')
        mu=float(fitted.x[0]);sd=float(np.exp(fitted.x[1]))
        record[typ+'_length']=dict(family='landmass-equal weighted lognormal censored MLE',mu_log_km=mu,sigma_log=sd,
              n=len(x),landmasses=len(ns),median_km=float(np.exp(mu)),mean_km=float(np.exp(mu+sd*sd/2)),
              n_complete=int((~censored).sum()),n_lower_bounds=int(censored.sum()),
              fit_success=bool(fitted.success),weighted_negative_log_likelihood=float(fitted.fun),
              observed_min_km=float(x.min()),observed_max_km=float(x.max()),
              notes='Unknown-adjacent segments provide lower bounds; complete observations provide densities. Family and censor interpretation are assumptions.')
    return FittedFunctions(record)


def create_targets(functions,seed,coast):
    """Condition generated lengths on this circumference and generated ratio.

Alternating renewal runs determine segment count without an extra class quota.
Per-type rescaling closes the ring and realizes the target share; unscaled
draws and scale factors are retained so that this conditioning is inspectable.
"""
    streams=[np.random.default_rng(s) for s in np.random.SeedSequence([seed,9241]).spawn(4)]
    regime=functions.environment(streams[0]);p=len(coast.xy)
    q=functions.mixed_deep_fraction(streams[1]) if regime=='mixed' else float(regime=='all_deep')
    if regime!='mixed':
        return np.full(p,q,dtype=bool),dict(seed=seed,regime=regime,deep_fraction_target=q,perimeter_km=p,
             raw_deep_lengths_km=[],raw_shallow_lengths_km=[],joint_conditioning='uniform type')
    rng=streams[2];best=None
    # Independent analytic draws, choosing a count that needs the least closure scaling.
    expected=max(1,p/(functions.record['deep_length']['mean_km']+functions.record['shallow_length']['mean_km']))
    max_n=min(100,max(8,int(np.ceil(4*expected))))
    for n in range(1,max_n+1):
        for _ in range(8):
            d=np.asarray(functions.deep_length(rng,n));s=np.asarray(functions.shallow_length(rng,n))
            fd=q*p/d.sum();fs=(1-q)*p/s.sum()
            penalty=float(np.log(fd)**2+np.log(fs)**2)
            if best is None or penalty<best[0]:best=(penalty,d,s,fd,fs)
    penalty,d,s,fd,fs=best
    lens=np.column_stack([d*fd,s*fs]).ravel();ends=np.cumsum(lens)
    phase=float(streams[3].uniform(0,p))
    at=(np.arange(p)+.5+phase)%p
    state=(np.searchsorted(ends,at,side='right')%2)==0
    return state,dict(seed=seed,regime=regime,deep_fraction_target=q,perimeter_km=p,
        raw_deep_lengths_km=d.tolist(),raw_shallow_lengths_km=s.tolist(),deep_scale=float(fd),shallow_scale=float(fs),
        conditioned_deep_lengths_km=(d*fd).tolist(),conditioned_shallow_lengths_km=(s*fs).tolist(),
        phase_km=phase,closure_log_error=penalty,
        joint_conditioning='minimum log-rescaling over run counts and analytic proposals; concatenate outer rings, retain per-ring closure in measured targets')
