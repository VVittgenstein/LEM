"""Fit reviewed variables; keep force and transfer priors explicitly separate."""
from __future__ import annotations
import csv,json,math
from collections import defaultdict
import numpy as np
from scipy import stats,optimize
from .common import ROOT,OUT,save
from .numerical_profile import apply_profile

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def fit_lognormal(values,groups=None):
    values=np.asarray(values,float);ok=np.isfinite(values)&(values>0);values=values[ok]
    groups=np.asarray(groups if groups is not None else np.arange(len(ok)))[ok]
    weight=np.array([1/np.sum(groups==g) for g in groups]);weight/=weight.sum()
    z=np.log(values);mu=float(np.sum(weight*z));sigma=float(np.sqrt(np.sum(weight*(z-mu)**2)))
    return dict(family='lognormal',log_mean=mu,log_std=max(sigma,.05),n=len(values),groups=len(np.unique(groups)),
                min=float(values.min()),median=float(np.median(values)),max=float(values.max()))

def main():
    faults=json.loads((ROOT/'sources/new/N02/MSSM_faults.geojson').read_text(encoding='utf-8'))['features']
    p=[f['properties'] for f in faults if f['properties']['dip_lower']<=f['properties']['dip_int']<=f['properties']['dip_upper']]
    length=np.array([f['length'] for f in p]);rate=np.array([f['slip_rate'] for f in p]);basin=[f['basin'] for f in p]
    w=np.array([1/basin.count(b) for b in basin]);w/=w.sum()
    X=np.column_stack([np.ones(len(p)),np.log(length)])
    beta=np.linalg.lstsq(X*np.sqrt(w[:,None]),np.log(rate)*np.sqrt(w),rcond=None)[0]
    residual=np.log(rate)-X@beta
    equal_dips=[f['dip_int'] for f in p if f['dip_lower']==f['dip_upper']]
    wsm=rows(ROOT/'output/tables/WSM_ABC_NF.csv')
    independent=[r for r in wsm if r['TYPE'] in ['BO','DIF','HF','OC','FMF']]
    groups=defaultdict(list)
    for r in independent:groups[r['REF1']].append(r)
    spreads=[]
    for key,rr in groups.items():
        if len(rr)<3:continue
        a=np.deg2rad([float(r['AZI']) for r in rr]);mean=.5*np.angle(np.mean(np.exp(2j*a)))
        delta=.5*np.angle(np.exp(2j*(a-mean)))
        spreads.append(float(np.sqrt(np.mean(delta**2))))
    mag=rows(ROOT/'output/tables/Germany_stress_magnitudes.csv')
    gradient=[];magnitude_ids=[]
    for r in mag:
        if r['QUALITY'] in ['A','B','C'] and r['REG']=='NF' and r['Sv'] and r['Shmin'] and float(r['DEPTH'])>=.5:
            gradient.append((float(r['Sv'])-float(r['Shmin']))/float(r['DEPTH']));magnitude_ids.append(r['id'])
    records=rows(ROOT/'sources/existing/tables/activity_records.csv')
    duration=[];duration_ids=[]
    for r in records:
        if r['record_id'] in ['R01_01','R03_01','R05_01']:
            d=float(r['record_span_Myr']) if r['record_span_Myr'] else (float(r['record_span_min_Myr'])+float(r['record_span_max_Myr']))/2
            duration.append(d);duration_ids.append(r['record_id'])
    assert len(gradient)==2 and len(duration)==3
    model=dict(
        status='research implementation; fitted variables and transfer assumptions separately recorded',
        length_km=fit_lognormal(length,basin),
        slip_mm_per_year_given_length=dict(log_intercept=beta[0],log_length_slope=beta[1],log_residual_std=float(np.sqrt(np.sum(w*residual**2))),
                                         source='MSSM regional model estimates; not all direct measurements',n=len(p)),
        dip_deg=dict(values=equal_dips,source='MSSM equal lower/central/upper values; regional constraints, not a global dip distribution'),
        orientation_scatter_rad=dict(value=float(np.median(spreads)),source='WSM ABC NF, non-FMS selected indicators, equal reference groups',records=len(independent),reference_groups=len(spreads)),
        stress_gradient_mpa_per_km=dict(value=float(np.mean(gradient)),values=gradient,record_ids=magnitude_ids,
                                      source='two records at Gt1, one case; depth transfer is a hypothesis'),
        duration_Myr=dict(**fit_lognormal(duration),record_ids=duration_ids,
                          source='three rifting phases used as forcing-duration proxies; midpoint of R01 interval is a design approximation'),
        design_priors=dict(auxiliary_km=2000,stress_solver_nodes=65,stress_depth_layers=5,reference_thickness_km=40,diagnostic_depth_km=10,
            local_duration_fraction=.25,far_mean_interval_Myr=16,local_mean_interval_Myr=6,source_count_max=40,
            far_contact_fraction=[.18,.35],local_radius_fraction=[.06,.12],local_peak_fraction=.35,
            reference_azimuth_uniform_deg=[0,180],local_force_azimuth_uniform_deg=[0,360],uniformity_limit=.30,minimum_distance_km=250,
            fault_birth_rate_per_Myr_at_reference_stress=.24,fault_clock_step_Myr=.125,
            fault_curvature_fraction=.07,
            elastic_young_GPa=30,elastic_poisson=.25,response_buffer_km=250,response_nodes=41,response_depth_layers=9,
            response_regularization_width_km=30,response_minimum_patch_half_length_km=16.25,source_quadrature_order=3,trace_patch_count=3,
            lifecycle_plateau_probability=.5,lifecycle_plateau_beta=[2,6],lifecycle_rise_beta=[3,3],
            strength_log_std=.20,strength_periods_Myr=[2,4,7,11]),
        withheld=['Pan Model B/E duplicate geometry and conflicting ages','Pan ambiguous dip column','MSSM fault316 dip interval','T01 unreviewed size qualifiers'],
        limits=['Force counts, source positions, local scales, recurrence, probability transfer and constitutive response are explicit design assumptions.',
                'Modern direction and magnitude evidence is not a measured 48 Myr force history.',
                'No observed valley depth or sediment thickness is fitted as U.'])
    apply_profile(model)
    save(OUT/'models.json',model)
    print('Fitted reviewed length/slip/orientation variables; saved proxy and design identities.',flush=True)
    return model

if __name__=='__main__':main()
