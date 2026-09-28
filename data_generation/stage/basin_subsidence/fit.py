"""Source-constrained distributions; all unobserved relationships are identified."""
from scipy import optimize, stats, special
import numpy as np
from .common import *

DESIGN = dict(mesh_side=49, auxiliary_span=2., boundary_layers=2, active_fraction_range=[.20, .34],
              area_sd=.045, area_weight=200., centroid_weight=5000., spread_weight=1600.,
              interface_weight=1.3, rate_smooth_weight=2.5, preference_strength=2.0, magnitude_weight=12.,
              burn_sweeps=2400, draw_sweeps=4800, thin=8, chains=4,
              temperatures=[float(1.10**k) for k in range(24)],
              length_median_km=200., length_log_sd=float(np.log(2)),
              temporal_space_fraction=.20, onset_last_fraction=.7,
              hold_probability=.5, hold_fraction_beta=[2., 6.], rise_beta=[3., 3.],
              wait_median_Myr=8., hazard_shape=2., epoch_shrinkage_Myr=12.,
              profile_rate_unit='m/Myr', output_rate_unit='m/yr', seed_policy='fixed consecutive seeds; no appearance selection')

def weighted_quantile(values, q, weights):
    order = np.argsort(values)
    v = np.asarray(values)[order]
    w = np.asarray(weights)[order]
    p = (np.cumsum(w)-.5*w)/w.sum()
    return np.interp(q, p, v)

def distribution(family, parameters):
    if family == 'lognormal':
        return stats.lognorm(s=np.exp(parameters[1]), scale=np.exp(parameters[0]))
    return stats.weibull_min(c=np.exp(parameters[0]), scale=np.exp(parameters[1]))

def duration_likelihood(rows, family, parameters):
    d = distribution(family, parameters)
    result = 0.
    for row in rows:
        low, high = row['low'], row['high']
        if row['kind'] == 'ongoing':
            value = d.logsf(low)
        else:
            # log CDF difference, with a lower positive floor for optimizer trials.
            value = np.log(max(float(d.cdf(high)-d.cdf(low)), 1e-300))
        result += row['weight']*float(value)
    return result

def fit_duration(rows, family):
    bounds = [(-1, 7), (-3, 1.6)] if family == 'lognormal' else [(-2.5, 3.5), (-1, 7)]
    starts = [[np.log(35), np.log(.7)], [np.log(50), np.log(1.)]] if family == 'lognormal' else [[np.log(1.5), np.log(45)], [0., np.log(60)]]
    answers = [optimize.minimize(lambda p: -duration_likelihood(rows, family, p), start,
               bounds=bounds, method='L-BFGS-B') for start in starts]
    best = min(answers, key=lambda s: s.fun)
    if not np.isfinite(best.fun):
        raise ValueError('Duration likelihood failed')
    return best.x

def fit_models():
    initialize()
    data = np.load(MODELS / 'reference.npz')
    x, rates, w = data['distance_km'], data['rates_m_per_Myr'], data['spatial_weights']
    dt = data['old_Ma']-data['young_Ma']
    average = rates @ dt / dt.sum()
    if np.any(average <= 0):
        raise ValueError('Reference interval-average magnitude must be positive')
    q = np.linspace(.0001, .9999, 2049)
    magnitude = weighted_quantile(average, q, w)
    # Same-place histories stay paired with their average magnitudes.
    ratio = rates / average[:, None]
    marginals = np.array([weighted_quantile(ratio[:, j], q, w) for j in range(7)])
    variables = np.column_stack([average, ratio])
    normal = np.column_stack([special.ndtri(np.clip(stats.rankdata(variables[:, j])/(len(x)+1), .001, .999)) for j in range(8)])
    cov = np.cov(normal.T, aweights=w)
    corr = cov/np.sqrt(np.outer(np.diag(cov), np.diag(cov)))
    corr = .9*corr+.1*np.eye(8)
    # Distance variogram uses actual km, never treats interpolated nodes as independent events.
    uniform = np.arange(0., x[-1]+.001, 2.)
    profile = np.interp(uniform, x, np.log(average))
    variance = float(np.var(profile))
    lags = np.array([4., 8., 16., 32., 64., 96.])
    vg = np.array([.5*np.mean((profile[int(lag/2):]-profile[:-int(lag/2)])**2)/variance for lag in lags])
    opt = optimize.minimize_scalar(lambda le: np.mean((np.log(np.maximum(vg, 1e-6))-
                 np.log(np.maximum(1-np.exp(-lags**2/(2*np.exp(le)**2)), 1e-6)))**2), bounds=(np.log(2), np.log(200)), method='bounded')
    spatial = dict(magnitude_quantiles_m_per_Myr=magnitude.tolist(), quantile_probabilities=q.tolist(),
        reference_mean_m_per_Myr=float(np.average(average, weights=w)),
        profile_correlation_km=float(np.exp(opt.x)), observed_variogram=vg.tolist(), variogram_lags_km=lags.tolist(),
        marginal_identity='45 Myr local mean unloaded subsidence used as mature-reference magnitude proxy',
        correlation_identity='one-profile along-line log-magnitude variogram; extending to 2D is a design assumption',
        full_extent=dict(median_km=200., log_sd=DESIGN['length_log_sd'],
            identity='B03 complete basin length 200 km anchors median; log scatter is a design value; not fitted global basin sizes'),
        sources=['B07 original paired .dat files', 'B03 whole-basin size, not 35 x 62 km study window'])
    save(MODELS / 'spatial.json', spatial)
    centers = (45-(data['old_Ma']+data['young_Ma'])/2)/45
    save(MODELS / 'temporal.json', dict(phase_nodes=centers.tolist(), ratio_quantiles=marginals.tolist(),
        quantile_probabilities=q.tolist(), joint_normal_correlation=corr.tolist(),
        conditioning='seven signed rate/mean ratios conditioned on the same-position reference magnitude',
        time_migration='45 Myr observational history normalized onto synthetic natural lifetime; explicit proxy',
        spatial_assignment='continuous graph-correlated residual normal fields; source constrains one direction only',
        sign_changes='signed ratios retain local reverse motion; no truncation of negative observed subsidence rates'))
    rows = [dict(id='B01_01', family='Canterbury', kind='interval', low=56., high=66., weight=1., onset_old=76., onset_young=76.),
            dict(id='B03_B05', family='Vienna', kind='interval', low=8., high=9., weight=1., onset_old=17., onset_young=16.,
                 identity='interpreted principal subsidence phase; finite phase proxy, not total basin age'),
            dict(id='B07_Zengmu', family='B07', kind='ongoing', low=40.4, high=40.4, weight=.5, onset_old=40.4, onset_young=40.4),
            dict(id='B07_Beikang', family='B07', kind='ongoing', low=16.4, high=16.4, weight=.5, onset_old=16.4, onset_young=16.4)]
    families = sorted(set(r['family'] for r in rows))
    comparisons = []
    for family in ('lognormal', 'weibull'):
        par = fit_duration(rows, family)
        folds = []
        for group in families:
            train = [r for r in rows if r['family'] != group]
            test = [r for r in rows if r['family'] == group]
            pars = fit_duration(train, family)
            folds.append(dict(group=group, score=duration_likelihood(test, family, pars), parameters=pars.tolist()))
        comparisons.append(dict(family=family, parameters=par.tolist(), log_likelihood=duration_likelihood(rows, family, par),
                                leave_family_out_score=sum(r['score'] for r in folds), folds=folds))
    selected = max(comparisons, key=lambda c: c['leave_family_out_score'])
    d = distribution(selected['family'], selected['parameters'])
    save(MODELS / 'duration.json', dict(selected=selected, comparisons=comparisons, evidence=rows,
        quantiles_Myr=dict(zip(['P10', 'P50', 'P90'], map(float, d.ppf([.1, .5, .9])))),
        identity='censored/interval fit to three selected research families; not global natural lifetime frequency'))
    counts = np.zeros(6)
    for row in rows:
        a, b = row['onset_old'], row['onset_young']
        for i, (_, _, old, young) in enumerate(EPOCHS):
            counts[i] += row['weight']*((young < a <= old) if a == b else max(0., min(old, a)-max(young, b))/(a-b))
    lengths = np.array([a-b for _, _, a, b in EPOCHS])
    prior = counts.sum()/48
    adjusted = (counts+prior*DESIGN['epoch_shrinkage_Myr'])/(lengths+DESIGN['epoch_shrinkage_Myr'])
    adjusted /= np.average(adjusted, weights=lengths)
    save(MODELS / 'trigger.json', dict(shape=DESIGN['hazard_shape'], reference_median_wait_Myr=DESIGN['wait_median_Myr'],
        epochs=[dict(id=n, name=cn, old_Ma=a, young_Ma=b, growth_multiplier=float(adjusted[i]), onset_weight=float(counts[i]))
                for i, (n, cn, a, b) in enumerate(EPOCHS)],
        identity='new basin onset evidence with shrinkage; relative case calibration; absolute wait is a design value',
        zero_record_epochs_disabled=False, same_type_rule='pause while active; resume in epoch after natural end epoch'))
    save(MODELS / 'design.json', DESIGN)
    provenance = [
        ('reference_magnitude', 'B07 45 Myr average per position', 'paired source calculation and weighted empirical distribution; mature-state proxy'),
        ('spatial_correlation', 'B07 along-profile log magnitude', 'fitted 1D distance variogram; 2D isotropy/anisotropy is design'),
        ('signed_temporal_ratios', 'B07 seven same-place intervals', 'empirical marginals and regularized normal-score correlation'),
        ('duration', 'B01, B03/B05, B07', 'three-family interval/right-censored proxy fit'),
        ('epoch_trigger', 'same onset evidence', 'relative calibration with 12 Myr shrinkage; wait 8 Myr and shape 2 design'),
        ('complete_scale', 'B03 complete length 200 km', 'single-case median with design log scatter ln(2)'),
        ('graph_probability', 'approved planar joint-state design', 'explicit implementation prior; weights calibrated on separate pilot seeds'),
        ('hold_and_phases', 'convergent event structure', 'hold probability .5; beta stage fractions are reused design values'),
        ('zero_boundary', 'finite complete event', 'outer computational nodes zero; active support tested away from frame'),
        ('B01_magnitude', 'existing four well reconstructions', 'diagnostic only; anomalous adjacent differences excluded'),
        ('B03_B05_maps', 'published interpolated tectonic-rate maps', 'structural evidence; no fabricated digital grids'),
    ]
    csvsave(MODELS / 'parameter_provenance.csv', [dict(parameter=p, source=s, identity=i) for p, s, i in provenance])
    print('Fitted basin models:', selected['family'], 'duration P10/P50/P90', d.ppf([.1, .5, .9]),
          'profile correlation km', spatial['profile_correlation_km'], flush=True)
    return spatial
