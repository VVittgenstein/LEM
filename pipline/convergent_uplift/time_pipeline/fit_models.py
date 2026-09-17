"""Small-sample duration likelihood and source-limited epoch calibration."""
import csv
from scipy import optimize, stats
from tcontext import *

DESIGN={
 'trigger_shape':2., 'trigger_reference_median_wait_Myr':8., 'epoch_shrinkage_exposure_Myr':12.,
 'hold_probability':.5, 'hold_fraction_beta':[2.,6.], 'rise_share_of_nonhold_beta':[3.,3.],
 'fluctuation_cv':.25, 'fluctuation_time_correlation_Myr':1.,
 'fluctuation_along_correlation_km':50., 'fluctuation_across_correlation_km':30.,
 'fluctuation_modes':96, 'clock_modes':32, 'axis_step_km':5.,
 'additional_origins_per_axis_km':1/1200., 'growth_last_onset_fraction':.70,
 'decay_local_duration_fraction':.35,
}

def distribution(family,par):
    if family=='lognormal':return stats.lognorm(s=np.exp(par[1]),scale=np.exp(par[0]))
    return stats.weibull_min(c=np.exp(par[0]),scale=np.exp(par[1]))

def log_likelihood(rows,family,par,upper_censor=False):
    d=distribution(family,par);total=0.
    for r in rows:
        lo=float(r['duration_low_Myr']);hi=float(r['duration_high_Myr']);w=float(r['weight'])
        if r['kind']=='ongoing':v=d.logsf(hi if upper_censor else lo)
        elif r['kind']=='interval':v=np.log(max(float(d.cdf(hi)-d.cdf(lo)),1e-300))
        else:v=d.logpdf(lo)
        total+=w*float(v)
    return total

def fit(rows,family,upper_censor=False):
    bounds=[(-4,7),(-3,1.6)] if family=='lognormal' else [(-2.5,3.5),(-4,7)]
    starts=[[np.log(16),np.log(.65)]] if family=='lognormal' else [[np.log(1.8),np.log(20)]]
    starts+= [[np.mean(b),np.mean(c)] for b,c in [(bounds[0],bounds[1])]]
    sols=[optimize.minimize(lambda p:-log_likelihood(rows,family,p,upper_censor),s,method='L-BFGS-B',bounds=bounds) for s in starts]
    sol=min(sols,key=lambda x:x.fun)
    if not np.isfinite(sol.fun):raise ValueError('Duration fit is not finite')
    return sol.x

def main():
    init();rows=list(csv.DictReader((SOURCES/'duration_evidence.csv').open(encoding='utf-8-sig')))
    families=sorted(set(r['family'] for r in rows));comparisons=[]
    for family in ('lognormal','weibull'):
        par=fit(rows,family);folds=[]
        for group in families:
            train=[r for r in rows if r['family']!=group];test=[r for r in rows if r['family']==group]
            p=fit(train,family);folds.append(dict(group=group,log_score=log_likelihood(test,family,p),parameters=p.tolist()))
        comparisons.append(dict(family=family,parameters=par.tolist(),log_likelihood=log_likelihood(rows,family,par),
                                leave_family_out_score=sum(r['log_score'] for r in folds),folds=folds))
    best=max(comparisons,key=lambda c:c['leave_family_out_score']);dist=distribution(best['family'],best['parameters'])
    quantiles={f'P{int(p*100):02d}':float(dist.ppf(p)) for p in (.05,.10,.25,.50,.75,.90,.95,.99)}
    sensitivity=[]
    for group in families:
        p=fit([r for r in rows if r['family']!=group],best['family']);d=distribution(best['family'],p)
        sensitivity.append(dict(omitted_family=group,P10=float(d.ppf(.1)),P50=float(d.ppf(.5)),P90=float(d.ppf(.9))))
    pc=fit(rows,best['family'],True);dc=distribution(best['family'],pc)
    save(MODELS/'duration.json',dict(selected=best,comparisons=comparisons,quantiles_Myr=quantiles,
          family_sensitivity=sensitivity,upper_elapsed_bound_sensitivity_Myr=dc.ppf([.1,.5,.9]).tolist(),
          rows=len(rows),families=len(families),unit='Myr',epoch_conditioning='shared across all six epochs; separate estimates unsupported',
          interpretation='Proxy-constrained duration model for one sustained mountain-growth/deformation regime. Small selected case set; population representativeness unestablished.',
          ongoing_method='Right censor at conservative reported elapsed lower bound; alternative upper bound in sensitivity.',
          interval_method='CDF difference; published range retained; no invented Gaussian age error.',
          observation_weights='Each region/study family totals one; constituent regimes share this weight.',
          right_tail='Unbounded positive family; durations above 48 Myr retained.'))
    counts=np.zeros(6);onsets=[]
    for r in rows:
        old=float(r['start_old_Ma']);young=float(r['start_young_Ma']);w=float(r['weight'])
        allocations=np.zeros(6)
        for i,(_,_,a,b) in enumerate(EPOCHS):
            if old==young:allocations[i]=w*float(b<old<=a)
            else:allocations[i]=w*max(0.,min(old,a)-max(young,b))/(old-young)
        counts+=allocations;onsets.append(dict(id=r['id'],weights=allocations.tolist(),outside_48Ma=bool(old>48)))
    lengths=np.array([a-b for _,_,a,b in EPOCHS]);rate0=float(counts.sum()/48)
    prior=DESIGN['epoch_shrinkage_exposure_Myr'];rates=(counts+rate0*prior)/(lengths+prior)
    multipliers=rates/np.average(rates,weights=lengths)
    save(MODELS/'trigger.json',dict(shape=DESIGN['trigger_shape'],reference_median_wait_Myr=DESIGN['trigger_reference_median_wait_Myr'],
      epochs=[dict(id=n,name=cn,old_Ma=a,young_Ma=b,length_Myr=a-b,catalogue_weight=float(counts[i]),growth_multiplier=float(multipliers[i])) for i,(n,cn,a,b) in enumerate(EPOCHS)],
      onset_allocation=onsets,shrinkage_exposure_Myr=prior,forbidden_combinations=[],
      status='Source-constrained relative design calibration; absolute physical occurrence probability is unidentified.',
      age_interval_allocation='Uniform allocation across reported onset ranges is an explicit approximation.',
      geographic_exposure='Unknown; epoch duration alone does not correct geographic sampling or preservation biases.',
      baseline_and_increasing_hazard='Design choices, not fitted geological frequencies.',
      waiting_rule='Retain eligible waiting time across epoch switches; reset after an event; end epoch is entirely embargoed.'))
    # Fit a one-case empirical distribution of normalized local onset delays.
    east=[r for r in csv.DictReader((SOURCES/'C05_paired_constraints.csv').open(encoding='utf-8-sig')) if r['onset_age_Ma']]
    ages=np.array([float(r['onset_age_Ma']) for r in east]);delays=(ages.max()-ages)/np.ptp(ages)
    save(MODELS/'onset_delay.json',dict(normalized_delays=np.sort(delays).tolist(),ages_range_Ma=[float(ages.min()),float(ages.max())],
        rows=len(east),independent_direct_constraints=14,family='Southern_Alps',
        use='Empirical marginal shape for relative local activation delays; spatial placement and scaling to the synthetic growth duration are design.',
        excluded_use='These rows do not contribute separate event lifetimes or initiation counts.'))
    save(MODELS/'design.json',DESIGN)
    provenance=[
      ('duration','weighted censored/interval likelihood','C05;W21;M10;S07','proxy-constrained fit; four selected families'),
      ('epoch_relative_growth','smoothed onset weights / epoch lengths','same source families','case-constrained design; exposure unknown'),
      ('absolute_trigger_and_wait_shape','median wait 8 Myr; Weibull shape 2','user increasing-probability rule','design'),
      ('local_onset_marginal','empirical normalized age offsets','C05 45 eastern estimates from 14 direct constraints','one-case marginal fit; spatial assignment is design'),
      ('hold_presence','Bernoulli(0.5)','no comparable resolved phase census','design; unknown records are not zero-duration cases'),
      ('hold_fraction','Beta(2,6) when present','no comparable lifetime-normalized hold sample','design'),
      ('rise_vs_fall','Beta(3,3) share of remaining lifetime','no paired complete growth-decay sample','design'),
      ('fluctuation_amplitude','CV 0.25, positive mean-one multiplier','DS5 has no million-year time series','design; sensitivity 0.125/0.5'),
      ('fluctuation_time','1 Myr squared-exponential correlation length','C05 acceleration dated 1.3+/-0.3 Ma; S07 changes at 4/1.5 Ma','case-informed order-of-magnitude design, no autocorrelation fit'),
      ('fluctuation_space','50 km along / 30 km across','C03 strong-region dimensions are spatial context','design, not a measured temporal-variation correlation'),
      ('DS5_reference','independent mature reference field per event from fixed spatial models','prior accepted field pipeline','no use of DS7; temporal marginal broadening measured separately'),
      ('spatial_clocks','axis-network propagation; smooth off-axis interpolation','prior accepted auxiliary graph','geometric construction; speed and origins are design'),
    ]
    csvsave(MODELS/'parameter_provenance.csv',[dict(parameter=p,method=m,source=s,status=st) for p,m,s,st in provenance])
    print('duration',best['family'],quantiles,flush=True)
    print('epoch multipliers',multipliers.tolist(),flush=True)

if __name__=='__main__':main()
