"""Fit the complete-province minimum-rectangle long-side distribution."""
import csv
from collections import defaultdict
import numpy as np
from scipy import stats,special
from common import ROOT,rng_for,write_json,write_csv,read_json,sha

def training_records():
    source=ROOT/'sources/G/landmass-provinces.csv'
    with source.open(encoding='utf-8-sig') as f:original=list(csv.DictReader(f))
    groups=defaultdict(list)
    for rowno,r in enumerate(original,2):
        if r['prov_type']=='orogenic belt' and r['in_primary_34']=='True':groups[r['province_key']].append((rowno,r))
    records=[]
    for key,rr in sorted(groups.items()):
        values=np.array([float(r['full_long_km']) for _,r in rr])
        records.append({'province_key':key,'province_name':rr[0][1]['prov_name'],'source_rows':';'.join(str(i) for i,r in rr),
          'landmasses':';'.join(r['landmass_name'] for _,r in rr),'measurements':len(rr),
          'full_long_km':float(np.median(values)),'minimum_measurement_km':float(values.min()),'maximum_measurement_km':float(values.max()),
          'relative_projection_spread':float(np.ptp(values)/np.median(values)),
          'grain':'one complete source province, equal weight; median across local projections',
          'unit':'km','quantity':'long side of minimum rotated rectangle of complete orogenic province'})
    assert len(records)==15 and sum(r['measurements'] for r in records)==17
    return records

def log_kde_logpdf(x,centers,h):
    a=np.atleast_1d(np.asarray(x,float));z=np.log(a)
    val=special.logsumexp(-.5*((z[:,None]-centers)/h)**2,axis=1)-np.log(len(centers)*h*np.sqrt(2*np.pi))-z
    return val if np.ndim(x) else float(val[0])

def cdf(x,model):
    a=np.asarray(x,float)
    if model['family']=='log_kde':
        vals=stats.norm.cdf((np.log(np.maximum(a[...,None],np.finfo(float).tiny))-np.array(model['log_centers']))/model['bandwidth_log']).mean(axis=-1)
        return np.where(a>0,vals,0.)
    d={'lognormal':stats.lognorm,'gamma':stats.gamma,'weibull':stats.weibull_min}[model['family']]
    return d.cdf(a,*model['parameters'])

def fit():
    rr=training_records();x=np.array([r['full_long_km'] for r in rr]);z=np.log(x);n=len(x)
    scores=[]
    for name,d in [('lognormal',stats.lognorm),('gamma',stats.gamma),('weibull',stats.weibull_min)]:
        loo=[]
        for i in range(n):
            par=d.fit(np.delete(x,i),floc=0);loo.append(float(d.logpdf(x[i],*par)))
        par=d.fit(x,floc=0)
        scores.append({'family':name,'parameters':[float(v) for v in par],'loo_mean_log_density_per_km':float(np.mean(loo)),
           'loo_values':loo,'aicc':float(4-2*d.logpdf(x,*par).sum()+12/(n-3))})
    # Design search grid in log-km; all candidates use the same held-out source provinces.
    bandwidths=np.geomspace(.05,1.,61)
    bandwidth_scores=[]
    for h in bandwidths:
        loo=[log_kde_logpdf(x[i],np.delete(z,i),h) for i in range(n)]
        bandwidth_scores.append({'bandwidth_log':float(h),'loo_mean_log_density_per_km':float(np.mean(loo))})
    best_h=max(bandwidth_scores,key=lambda r:r['loo_mean_log_density_per_km'])
    scores.append({'family':'log_kde',**best_h,'log_centers':z.tolist(),'aicc':None})
    best=max(scores,key=lambda r:r['loo_mean_log_density_per_km'])
    model={'version':'G-long-side-v1',**best,'source_sha256':sha(ROOT/'sources/G/landmass-provinces.csv'),
      'sample_size':n,'raw_primary_rows':17,'population':'34 primary reference landmasses; orogenic belt source provinces',
      'weighting':'one source province one vote; repeated local projections summarized by median',
      'unit':'km','quantity':'complete province minimum rotated rectangle long side',
      'axis_mapping':'Use sampled province long side as target minimum-rectangle long side of complete generated axis graph; explicit geometric proxy assumption',
      'support':'positive; fitted distribution tails are model extrapolation, no manual clipping',
      'selection':'highest leave-one-source-province-out mean log density, same variable and Jacobian for every candidate',
      'uncertainty':'15 source provinces; exploratory model comparison, not a global representativeness claim',
      'all_candidates':scores,'bandwidth_candidates':bandwidth_scores,'training_values_km':x.tolist()}
    write_csv(ROOT/'tables/G_scale_training.csv',rr);write_json(ROOT/'tables/scale_model.json',model)
    print('G scale model:',model['family'],'n=',n,'bandwidth=',model.get('bandwidth_log'),flush=True)
    return model

def sample(seed,model=None):
    model=model or read_json(ROOT/'tables/scale_model.json');r=rng_for(seed,101)
    if model['family']=='log_kde':
        i=int(r.integers(model['sample_size']));normal=float(r.normal())
        value=float(np.exp(model['log_centers'][i]+model['bandwidth_log']*normal))
        draw={'mixture_component':i,'standard_normal':normal}
    else:
        q=float(r.uniform());d={'lognormal':stats.lognorm,'gamma':stats.gamma,'weibull':stats.weibull_min}[model['family']]
        value=float(d.ppf(q,*model['parameters']));draw={'uniform_quantile':q}
    assert np.isfinite(value) and value>0
    return value,{'seed':int(seed),'stream':101,'value_km':value,'cdf_at_value':float(cdf(value,model)),**draw}

if __name__=='__main__':fit()
