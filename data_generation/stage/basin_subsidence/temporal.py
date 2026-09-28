"""Convergent-style event clocks with newly fitted signed basin histories."""
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy import special
from .common import *
from .fit import distribution
from .spatial import correlated_field, laplacian

def hazard_increment(wait, dt, epoch, model):
    if wait < 0 or dt < 0:
        raise ValueError('Negative eligible time')
    k = model['shape']
    eta = model['reference_median_wait_Myr']/np.log(2)**(1/k)
    c = model['epochs'][epoch]['growth_multiplier']/eta**k
    return float(c*((wait+dt)**k-wait**k))

def simulate(seed, dt_Myr=.025, trigger=None, duration=None, design=None):
    if dt_Myr <= 0:
        raise ValueError('Positive scheduling step required')
    trigger = trigger or load(MODELS / 'trigger.json')
    duration = duration or load(MODELS / 'duration.json')
    design = design or load(MODELS / 'design.json')
    spec = duration['selected']; d = distribution(spec['family'], spec['parameters'])
    random, phase = rng(seed, 10), rng(seed, 11)
    t = wait = hazard = 0.
    threshold = float(random.exponential())
    events, embargoes = [], []
    while t < 48-1e-11:
        epoch = epoch_index(t)
        stop = 48-EPOCHS[epoch][3]
        step = min(dt_Myr, stop-t)
        dh = hazard_increment(wait, step, epoch, trigger)
        if hazard+dh < threshold-1e-13:
            hazard += dh; wait += step; t += step
            if abs(t-stop) < 1e-10:
                t = stop
            continue
        k = trigger['shape']; eta = trigger['reference_median_wait_Myr']/np.log(2)**(1/k)
        coefficient = trigger['epochs'][epoch]['growth_multiplier']/eta**k
        offset = (wait**k+(threshold-hazard)/coefficient)**(1/k)-wait
        start = t+float(np.clip(offset, 0, step))
        total = float(d.ppf(phase.uniform(np.finfo(float).eps, 1-np.finfo(float).eps)))
        hold = float(phase.beta(*design['hold_fraction_beta'])) if phase.random() < design['hold_probability'] else 0.
        rise_share = float(phase.beta(*design['rise_beta']))
        rise = total*(1-hold)*rise_share
        steady = total*hold
        end = start+total
        index = len(events)
        event = dict(seed=seed, event_index=index, event_id=f'basin-{seed}-{index+1:02d}',
            event_seed=int(rng(seed, 100+index).integers(1, 2**31)), activity_type='basin_subsidence',
            start_sim_Myr=start, start_age_Ma=48-start, natural_end_sim_Myr=end, duration_Myr=total,
            rise_Myr=rise, hold_Myr=steady, fall_Myr=total-rise-steady,
            rise_end_sim_Myr=start+rise, hold_end_sim_Myr=start+rise+steady,
            executed_until_sim_Myr=min(48., end), ongoing_at_modern=bool(end > 48),
            start_epoch=EPOCHS[epoch][0], eligible_wait_Myr=wait+offset)
        events.append(event)
        if end >= 48:
            break
        end_epoch = epoch_index(end)
        resume = 48-EPOCHS[end_epoch][3]
        embargoes.append(dict(event_index=index, natural_end_Myr=end, resume_Myr=resume, end_epoch=EPOCHS[end_epoch][0]))
        t = resume; wait = hazard = 0.; threshold = float(random.exponential())
    return dict(seed=seed, events=events, embargoes=embargoes, dt_Myr=dt_Myr,
        rule='continuous cumulative hazard; paused while active and through end epoch; retain unexecuted natural history')

def frame_times(event):
    raw = []
    for name, start, duration in [('增强', event['start_sim_Myr'], event['rise_Myr']),
                                  ('维持', event['rise_end_sim_Myr'], event['hold_Myr']),
                                  ('减弱', event['hold_end_sim_Myr'], event['fall_Myr'])]:
        if duration <= 0:
            continue
        for q in (0., .33, .66, 1.):
            t = start+duration*q
            if name == '减弱' and q == 1:
                t = event['natural_end_sim_Myr']
            if t <= 48+1e-10:
                raw.append(dict(sim_Myr=min(t, 48.), stage=name, elapsed_fraction=q))
    if event['ongoing_at_modern']:
        if 48 < event['rise_end_sim_Myr']:
            name, start, duration = '增强', event['start_sim_Myr'], event['rise_Myr']
        elif 48 < event['hold_end_sim_Myr']:
            name, start, duration = '维持', event['rise_end_sim_Myr'], event['hold_Myr']
        else:
            name, start, duration = '减弱', event['hold_end_sim_Myr'], event['fall_Myr']
        raw.append(dict(sim_Myr=48., stage=name, elapsed_fraction=(48-start)/duration))
    raw.sort(key=lambda r: r['sim_Myr'])
    frames = []
    for row in raw:
        label = dict(stage=row['stage'], elapsed_fraction=row['elapsed_fraction'])
        if frames and abs(frames[-1]['sim_Myr']-row['sim_Myr']) < 1e-9:
            if label not in frames[-1]['labels']:
                frames[-1]['labels'].append(label)
        else:
            frames.append(dict(sim_Myr=row['sim_Myr'], labels=[label]))
    for number, frame in enumerate(frames, 1):
        frame.update(number=number, age_Ma=max(0., 48-frame['sim_Myr']), modern=abs(frame['sim_Myr']-48) < 1e-9)
    return frames

def normalize(values):
    return (values-values.min())/max(float(np.ptp(values)), 1e-12)

def make_history(event, directory):
    directory = Path(directory)
    data = np.load(directory / 'mesh.npz')
    points, edges, active = data['points_km'], data['edges'], data['active']
    design, model, spatial = load(MODELS / 'design.json'), load(MODELS / 'temporal.json'), load(MODELS / 'spatial.json')
    random = rng(event['event_seed'], 301)
    normalized = data['raw_points']
    graph = laplacian(normalized, edges)
    # Connected numerical support gets its own origins. These are numerical clocks,
    # not new geological events, sub-basin counts or hidden force sources.
    a, b = edges.T
    kept = active[a] & active[b]
    speed = np.exp(.25*correlated_field(random, graph, 4.))
    distance = np.linalg.norm(points[a]-points[b], axis=1)/np.sqrt(speed[a]*speed[b])
    G = coo_matrix((np.r_[distance[kept], distance[kept]],
                   (np.r_[a[kept], b[kept]], np.r_[b[kept], a[kept]])), shape=(len(points), len(points))).tocsr()
    ids = np.flatnonzero(active)
    sub = G[ids][:, ids]
    count, labels = connected_components(sub)
    origins = [int(random.choice(np.flatnonzero(labels == c))) for c in range(count)]
    arrival = dijkstra(sub, indices=origins, min_only=True)
    if not np.isfinite(arrival).all():
        raise ValueError('A support component has no clock origin')
    onset = np.zeros(len(points)); retreat = np.zeros(len(points))
    onset[ids] = normalize(arrival)*design['onset_last_fraction']
    retreat_random = correlated_field(random, graph, 5.)
    retreat[ids] = normalize(.45*normalize(arrival)+.55*normalize(retreat_random[ids]))
    reference = -data['reference_u_m_per_yr']*1e6
    q = np.array(spatial['quantile_probabilities'])
    z0 = special.ndtri(np.clip(np.interp(reference, spatial['magnitude_quantiles_m_per_Myr'], q), .001, .999))
    corr = np.array(model['joint_normal_correlation'])
    conditional = corr[1:, 1:]-np.outer(corr[1:, 0], corr[0, 1:])
    chol = np.linalg.cholesky(conditional)
    residual = np.column_stack([correlated_field(random, graph, design['temporal_space_fraction']*design['mesh_side']/design['auxiliary_span']) for _ in range(7)])
    latent = z0[:, None]*corr[None, 1:, 0]+residual@chol.T
    ratios = np.column_stack([np.interp(special.ndtr(latent[:, j]), model['quantile_probabilities'], model['ratio_quantiles'][j]) for j in range(7)])
    phase_nodes = np.r_[0., model['phase_nodes'], 1.]
    values = np.column_stack([ratios[:, 0], ratios, ratios[:, -1]])
    curve = PchipInterpolator(phase_nodes, values, axis=1)
    coefficients = np.moveaxis(curve.c, -1, 0)  # nodes x polynomial coefficient x intervals
    up = event['rise_Myr']/event['duration_Myr']
    hold = event['hold_Myr']/event['duration_Myr']
    down = event['fall_Myr']/event['duration_Myr']
    begin = onset*up
    grown = (.45+.55*np.clip(onset/.7, 0, 1))*up
    retreat_begin = up+hold+.65*retreat*down
    retreat_end = retreat_begin+.35*down
    np.savez_compressed(directory / 'time_model.npz', phase_nodes=phase_nodes, coefficients=coefficients,
        ratio_nodes=values, onset=onset, retreat=retreat, growth_begin=begin, growth_end=grown,
        fall_begin=retreat_begin, fall_end=retreat_end)
    save(directory / 'time_model.json', dict(clock_origins=ids[origins].tolist(), support_components=int(count),
        reference_definition=spatial['marginal_identity'], temporal_curve_identity=model['time_migration'],
        phase_ratios_min=float(ratios[active].min()), phase_ratios_max=float(ratios[active].max()),
        local_reverse_motion=bool(np.any(ratios[active] < 0)),
        interpolation='shape-preserving piecewise cubic in normalized natural lifetime',
        event_gate='local cubic onset and retreat; global enhanced/hold/weaken phases',
        query_random_draws=False))

def smooth(z):
    z = np.clip(z, 0., 1.)
    return z*z*(3-2*z)

class NodeHistory:
    def __init__(self, directory):
        directory = Path(directory)
        self.event = load(directory / 'event.json')
        with np.load(directory / 'mesh.npz') as data:
            self.reference = data['reference_u_m_per_yr']
        with np.load(directory / 'time_model.npz') as data:
            self.time = dict(data)
        self.n = len(self.reference)

    def _rate_phase(self, phase):
        phase = np.asarray(phase)
        # First axis always addresses nodes; trailing axes may be quadrature points.
        if phase.ndim == 0:
            phase = np.full((self.n,), float(phase))
        index = np.clip(np.searchsorted(self.time['phase_nodes'], phase, side='right')-1, 0, len(self.time['phase_nodes'])-2)
        node = np.arange(self.n).reshape((self.n,)+(1,)*(phase.ndim-1))
        c = self.time['coefficients']
        delta = phase-self.time['phase_nodes'][index]
        ratio = ((c[node, 0, index]*delta+c[node, 1, index])*delta+c[node, 2, index])*delta+c[node, 3, index]
        def expanded(name):
            return self.time[name].reshape((self.n,)+(1,)*(phase.ndim-1))
        gate = smooth((phase-expanded('growth_begin'))/np.maximum(expanded('growth_end')-expanded('growth_begin'), 1e-15))
        gate *= 1-smooth((phase-expanded('fall_begin'))/np.maximum(expanded('fall_end')-expanded('fall_begin'), 1e-15))
        gate *= (phase > 0) & (phase < 1)
        return self.reference.reshape((self.n,)+(1,)*(phase.ndim-1))*gate*ratio

    def rate(self, t_myr):
        phase = (t_myr-self.event['start_sim_Myr'])/self.event['duration_Myr']
        if phase <= 0 or phase >= 1:
            return np.zeros(self.n)
        return self._rate_phase(phase)

    def displacement(self, a_myr, b_myr):
        if not np.isfinite([a_myr, b_myr]).all() or b_myr < a_myr:
            raise ValueError('Finite ordered integration interval required')
        start, life = self.event['start_sim_Myr'], self.event['duration_Myr']
        a = max(0., (a_myr-start)/life); b = min(1., (b_myr-start)/life)
        if b <= a:
            return np.zeros(self.n)
        fixed = np.broadcast_to(self.time['phase_nodes'], (self.n, len(self.time['phase_nodes'])))
        clocks = np.column_stack([self.time[k] for k in ('growth_begin', 'growth_end', 'fall_begin', 'fall_end')])
        boundaries = np.sort(np.clip(np.column_stack([np.full(self.n, a), fixed, clocks, np.full(self.n, b)]), a, b), axis=1)
        low, high = boundaries[:, :-1], boundaries[:, 1:]
        nodes, weights = np.polynomial.legendre.leggauss(5)
        times = (low+high)[:, :, None]/2+(high-low)[:, :, None]*nodes/2
        # Polynomial degree at most 9 on each partition; five-point Gauss is exact
        # up to floating-point roundoff. No LEM timestep enters this integral.
        rates = self._rate_phase(times)
        return np.sum(rates*weights[None, None, :]*(high-low)[:, :, None]/2, axis=(1, 2))*life*1e6
