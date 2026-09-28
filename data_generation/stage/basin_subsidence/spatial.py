"""Joint zero/continuous-rate probability model on an irregular planar mesh.

The geometry is a numerical mesh. No circle, rectangle or ellipse is used as
an activity mask. A fixed correlated preference is part of the hierarchical
prior, analogous to the existing platform joint-state generator.
"""
import time
import numpy as np
from scipy import sparse, special, stats
from scipy.sparse.linalg import spsolve
from scipy.spatial import Delaunay, ConvexHull
from scipy.sparse.csgraph import connected_components, dijkstra
from numba import njit
from .common import *

def mesh(seed, side, span=1.):
    r = rng(seed, 201)
    yy, xx = np.meshgrid(np.arange(side), np.arange(side), indexing='ij')
    points = np.column_stack([xx.ravel(), yy.ravel()]).astype(float)
    outer = (xx.ravel() == 0) | (xx.ravel() == side-1) | (yy.ravel() == 0) | (yy.ravel() == side-1)
    points[~outer] += r.uniform(-.38, .38, (int((~outer).sum()), 2))
    points = (points/(side-1)-.5)*span
    tri = Delaunay(points)
    triangles = tri.simplices
    vertices = points[triangles]
    d1, d2 = vertices[:, 1]-vertices[:, 0], vertices[:, 2]-vertices[:, 0]
    area = abs(d1[:, 0]*d2[:, 1]-d1[:, 1]*d2[:, 0])/2
    mass = np.bincount(triangles.ravel(), weights=np.repeat(area/3, 3), minlength=len(points))
    # Area is measured in event-coordinate units, independent of auxiliary span.
    edges = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
    edges = np.unique(edges, axis=0)
    distance = np.linalg.norm(points[edges[:, 0]]-points[edges[:, 1]], axis=1)
    edge_weight = np.sqrt(np.median(distance)/distance)
    degree = np.bincount(edges.ravel(), minlength=len(points))
    neighbors = np.full((len(points), degree.max()), -1, np.int32)
    weights = np.zeros(neighbors.shape)
    used = np.zeros(len(points), int)
    for (a, b), w in zip(edges, edge_weight):
        neighbors[a, used[a]] = b; weights[a, used[a]] = w; used[a] += 1
        neighbors[b, used[b]] = a; weights[b, used[b]] = w; used[b] += 1
    boundary_distance = np.minimum.reduce([xx.ravel(), yy.ravel(), side-1-xx.ravel(), side-1-yy.ravel()])
    return points, triangles, edges, mass, neighbors, weights, boundary_distance

def laplacian(points, edges, angle=0., ratio=1.):
    d = points[edges[:, 1]]-points[edges[:, 0]]
    c, s = np.cos(angle), np.sin(angle)
    longitudinal = d[:, 0]*c+d[:, 1]*s
    transverse = -d[:, 0]*s+d[:, 1]*c
    metric = np.sqrt(longitudinal**2+(transverse/ratio)**2)
    weight = np.median(metric)/np.maximum(metric, 1e-8)
    a, b = edges.T
    W = sparse.coo_matrix((np.r_[weight, weight], (np.r_[a, b], np.r_[b, a])), shape=(len(points), len(points))).tocsr()
    return sparse.diags(np.asarray(W.sum(axis=1)).ravel())-W

def correlated_field(random, graph, length_cells):
    value = spsolve(sparse.eye(graph.shape[0], format='csc') + max(.01, length_cells**2/4)*graph.tocsc(),
                     random.standard_normal(graph.shape[0]))
    return (value-value.mean())/max(float(value.std()), 1e-12)

def preference_field(seed, points, edges, correlation_fraction, side, span=1.):
    random = rng(seed, 202)
    angle = float(random.uniform(0, np.pi))
    ratio = float(random.uniform(.35, 1.))
    graph = laplacian(points, edges, angle, ratio)
    weights = random.dirichlet([1.5, 3., 2.5])
    scales = np.clip(correlation_fraction*np.array([.5, 1.5, 3.]), .035, .5)
    fields = np.array([correlated_field(random, graph, v*(side-1)/span) for v in scales])
    value = weights @ fields
    value = (value-value.mean())/value.std()
    return value, dict(angle_rad=angle, correlation_axis_ratio=ratio, scale_fractions=scales.tolist(),
                       scale_weights=weights.tolist(), identity='numerical planar organization prior; no geological forces or outlines')

@njit(cache=True)
def global_scalar(area, x, y, second, target, pars):
    if area <= 1e-12:
        return 1e100
    center = (x*x+y*y)/(area*area)
    spread = second/area-center
    return pars[0]*.5*((area-target)/pars[1])**2+pars[2]*center+pars[3]*spread

@njit(cache=True)
def global_energy(moment, target, pars):
    return global_scalar(moment[0], moment[1], moment[2], moment[3], target, pars)

@njit(cache=True)
def energy(state, edges, edge_weights, moment, target, pars, preference):
    value = global_energy(moment, target, pars)
    for i in range(len(state)):
        if state[i] != 0:
            value -= pars[6]*preference[i, 0]
            value += pars[7]*(state[i]-preference[i, 1])**2
    for k in range(len(edges)):
        a, b = edges[k]
        rough = pars[5]*(state[a]-state[b])**2 if state[a] != 0 and state[b] != 0 else 0.
        value += edge_weights[k]*(pars[4]*((state[a] != 0) != (state[b] != 0)) + rough)
    return value

@njit(cache=True)
def moments(state, weights, points):
    area = mx = my = second = 0.
    for i in range(len(state)):
        if state[i] != 0:
            x, y = points[i]
            w = weights[i]
            area += w; mx += w*x; my += w*y; second += w*(x*x+y*y)
    return np.array([area, mx, my, second])

@njit(cache=True)
def sample_system(seed, start, quantiles, eligible, neighbors, edge_weights, edges, ew,
                  mass, points, preference, target, pars, temperatures, burn, draws, thin):
    """Prior proposals cancel in MH ratios. Temperature affects only interaction energy."""
    np.random.seed(seed)
    replicas = len(temperatures)
    states = np.empty((replicas, len(start)))
    for j in range(replicas):
        states[j] = start
    mom = np.zeros((replicas, 4))
    E = np.empty(replicas)
    for j in range(replicas):
        mom[j] = moments(states[j], mass, points)
        E[j] = energy(states[j], edges, ew, mom[j], target, pars, preference)
    trace = np.zeros((draws//thin, 6))
    accepted = np.zeros(replicas)
    exchanges = np.zeros(replicas-1)
    recorded = 0
    for sweep in range(burn+draws):
        for j in range(replicas):
            for step in range(len(eligible)):
                i = eligible[np.random.randint(len(eligible))]
                old = states[j, i]
                new = 0.
                if np.random.random() < .5:
                    q = np.random.random()*(len(quantiles)-1)
                    k = int(q)
                    new = quantiles[k]+(q-k)*(quantiles[min(k+1, len(quantiles)-1)]-quantiles[k])
                if old == new:
                    continue
                dz = (1. if new != 0 else 0.)-(1. if old != 0 else 0.)
                x, y = points[i]
                dm = mass[i]*dz
                m0 = mom[j, 0]+dm; m1 = mom[j, 1]+dm*x
                m2 = mom[j, 2]+dm*y; m3 = mom[j, 3]+dm*(x*x+y*y)
                delta = global_scalar(m0, m1, m2, m3, target, pars)-global_energy(mom[j], target, pars)
                delta -= pars[6]*preference[i, 0]*dz
                old_unary = pars[7]*(old-preference[i, 1])**2 if old != 0 else 0.
                new_unary = pars[7]*(new-preference[i, 1])**2 if new != 0 else 0.
                delta += new_unary-old_unary
                for n in range(neighbors.shape[1]):
                    other = neighbors[i, n]
                    if other < 0:
                        break
                    v = states[j, other]
                    old_rough = pars[5]*(old-v)**2 if old != 0 and v != 0 else 0.
                    new_rough = pars[5]*(new-v)**2 if new != 0 and v != 0 else 0.
                    delta += edge_weights[i, n]*(pars[4]*((1. if (new != 0) != (v != 0) else 0.)-(1. if (old != 0) != (v != 0) else 0.))
                              + new_rough-old_rough)
                if np.log(max(np.random.random(), 1e-300)) < -delta/temperatures[j]:
                    states[j, i] = new
                    mom[j, 0] = m0; mom[j, 1] = m1; mom[j, 2] = m2; mom[j, 3] = m3
                    E[j] += delta
                    accepted[j] += 1
        if sweep % 8 == 0:
            # A symmetric permutation move relocates a whole numerical pattern.
            # The iid node-prior product cancels exactly; recompute the full E.
            side = int(np.sqrt(len(eligible)))
            for j in range(replicas):
                radius = max(1, side//2) if np.random.random() < .35 else 3
                dx = np.random.randint(-radius, radius+1); dy = np.random.randint(-radius, radius+1)
                candidate_state = states[j].copy()
                for k in range(len(eligible)):
                    source = ((k//side+dy) % side)*side+(k % side+dx) % side
                    candidate_state[eligible[k]] = states[j, eligible[source]]
                candidate_moment = moments(candidate_state, mass, points)
                candidate_energy = energy(candidate_state, edges, ew, candidate_moment, target, pars, preference)
                if np.log(max(np.random.random(), 1e-300)) < -(candidate_energy-E[j])/temperatures[j]:
                    states[j] = candidate_state; mom[j] = candidate_moment; E[j] = candidate_energy
                # Symmetric block activation toggle. New positive values come
                # from their prior, so the density factors cancel in both directions.
                candidate_state = states[j].copy()
                width = 3 if np.random.random() < .5 else 5
                row0 = np.random.randint(0, side); col0 = np.random.randint(0, side)
                for dr in range(width):
                    for dc in range(width):
                        node = eligible[((row0+dr) % side)*side+(col0+dc) % side]
                        if candidate_state[node] != 0:
                            candidate_state[node] = 0.
                        else:
                            q = np.random.random()*(len(quantiles)-1); k = int(q)
                            candidate_state[node] = quantiles[k]+(q-k)*(quantiles[min(k+1, len(quantiles)-1)]-quantiles[k])
                candidate_moment = moments(candidate_state, mass, points)
                candidate_energy = energy(candidate_state, edges, ew, candidate_moment, target, pars, preference)
                if np.log(max(np.random.random(), 1e-300)) < -(candidate_energy-E[j])/temperatures[j]:
                    states[j] = candidate_state; mom[j] = candidate_moment; E[j] = candidate_energy
        if sweep % 4 == 0:
            parity = (sweep//4) % 2
            for j in range(parity, replicas-1, 2):
                logalpha = (1/temperatures[j]-1/temperatures[j+1])*(E[j]-E[j+1])
                if np.log(max(np.random.random(), 1e-300)) < logalpha:
                    temp = states[j].copy(); states[j] = states[j+1]; states[j+1] = temp
                    tempm = mom[j].copy(); mom[j] = mom[j+1]; mom[j+1] = tempm
                    t = E[j]; E[j] = E[j+1]; E[j+1] = t
                    exchanges[j] += 1
        if sweep % 128 == 0:
            for j in range(replicas):
                mom[j] = moments(states[j], mass, points)
                E[j] = energy(states[j], edges, ew, mom[j], target, pars, preference)
        if sweep >= burn and (sweep-burn+1) % thin == 0:
            a = mom[0, 0]
            mean = np.sum(states[0]*mass)/a
            trace[recorded] = np.array([a, mom[0, 1]/a, mom[0, 2]/a, mom[0, 3]/a, mean, E[0]])
            recorded += 1
    return states[0], trace, accepted/((burn+draws)*len(eligible)), exchanges

def convergence(trace):
    # Split-chain classical R-hat plus an autocorrelation-based conservative ESS.
    chains, draws, variables = trace.shape
    n = draws//2
    split = np.concatenate([trace[:, :n], trace[:, -n:]], axis=0)
    within = np.mean(np.var(split, axis=1, ddof=1), axis=0)
    between = n*np.var(split.mean(axis=1), axis=0, ddof=1)
    variance = (n-1)/n*within+between/n
    rhat = np.sqrt(np.divide(variance, within, out=np.ones_like(within), where=within > 1e-16))
    ess = []
    for j in range(variables):
        a = split[:, :, j]-split[:, :, j].mean(axis=1, keepdims=True)
        den = np.mean(a*a)
        sums = 0.
        if den > 1e-16:
            for lag in range(1, n//2):
                rho = np.mean(a[:, lag:]*a[:, :-lag])/den
                if rho <= 0:
                    break
                sums += rho
        ess.append(float(min(chains*draws, chains*draws/max(1., 1+2*sums))))
    return dict(variables=['active_area', 'center_x', 'center_y', 'second_moment', 'mean_rate', 'interaction_energy'],
                split_rhat=rhat.tolist(), effective_sample_size=ess,
                maximum_rhat=float(rhat.max()), minimum_ess=float(min(ess)),
                passed=bool(rhat.max() <= 1.10 and min(ess) >= 50),
                identity='finite-chain engineering diagnostics; not proof of stationary sampling or geological adequacy')

def graph_prior(seed, model, design, target_length_km=None):
    random = rng(seed, 203)
    L = float(random.lognormal(np.log(model['full_extent']['median_km']), model['full_extent']['log_sd']))
    if target_length_km is not None:
        L = float(target_length_km)
    side = design['mesh_side']
    span = design['auxiliary_span']
    points, triangles, edges, mass, neighbors, weights, layers = mesh(seed, side, span)
    eligible = np.flatnonzero(layers >= design['boundary_layers']).astype(np.int32)
    region_preference, pref_record = preference_field(seed, points, edges, model['profile_correlation_km']/L, side, span)
    target = float(random.uniform(*design['active_fraction_range']))
    quantiles = np.array(model['magnitude_quantiles_m_per_Myr'])/model['reference_mean_m_per_Myr']
    rate_graph = laplacian(points, edges, pref_record['angle_rad'], pref_record['correlation_axis_ratio'])
    rate_normal = correlated_field(rng(seed, 204), rate_graph, np.clip(model['profile_correlation_km']/L, .03, .5)*(side-1)/span)
    rate_target = np.interp(special.ndtr(rate_normal), model['quantile_probabilities'], quantiles)
    preference = np.column_stack([region_preference, rate_target])
    pref_record['magnitude_preference'] = 'separate correlated normal field, mapped through the measured magnitude quantiles; finite unary weight in the joint probability'
    pars = np.array([design['area_weight'], design['area_sd'], design['centroid_weight'], design['spread_weight'],
                     design['interface_weight'], design['rate_smooth_weight'], design['preference_strength'], design['magnitude_weight']])
    ew = np.sqrt(np.median(np.linalg.norm(points[edges[:, 0]]-points[edges[:, 1]], axis=1))/
                 np.linalg.norm(points[edges[:, 0]]-points[edges[:, 1]], axis=1))
    draws, burn = design['draw_sweeps'], design['burn_sweeps']
    records, final_states, traces = [], [], []
    for chain in range(design['chains']):
        start = np.zeros(len(points))
        if chain == 0:
            selected = eligible[np.argsort(preference[eligible, 0])[-max(10, int(target*len(points))):]]
        elif chain == 1:
            selected = eligible
        else:
            selected = random.choice(eligible, max(5, int(len(eligible)*random.uniform(.15, .7))), replace=False)
        start[selected] = np.median(quantiles)
        state, trace, accepted, exchanges = sample_system(int(rng(seed, 210+chain).integers(1, 2**31)), start, quantiles,
            eligible, neighbors, weights, edges, ew, mass, points, preference, target, pars,
            np.array(design['temperatures']), burn, draws, design['thin'])
        final_states.append(state); traces.append(trace)
        records.append(dict(chain=chain, acceptance=accepted.tolist(), exchanges=exchanges.tolist()))
    trace = np.array(traces)
    return dict(points=points, triangles=triangles, edges=edges, mass=mass, preference=preference,
                values=np.array(final_states), trace=trace, layers=layers), dict(seed=seed, sampled_complete_long_km=L,
        design=design, target_active_fraction=target, preference=pref_record, chains=records, diagnostics=convergence(trace),
        representative='last cold state of chain 0, fixed before generation; no appearance-based selection',
        state_prior='each eligible node: probability .5 exact zero, otherwise continuous source-quantile rate; joint interaction reweights this prior',
        target_law='p(state | preference) proportional to product(node_prior) * exp(-E); E includes graph differences and whole-state statistics')

def long_side(points):
    hull = points[ConvexHull(points).vertices]
    directions = np.diff(np.vstack([hull, hull[0]]), axis=0)
    angles = np.arctan2(directions[:, 1], directions[:, 0])
    best = None
    for angle in angles:
        c, s = np.cos(angle), np.sin(angle)
        rotated = hull @ np.array([[c, -s], [s, c]])
        widths = np.ptp(rotated, axis=0)
        area = float(np.prod(widths))
        if best is None or area < best[0]:
            best = area, float(widths.max())
    return best[1]

def generate_reference(seed, directory, design=None):
    start = time.perf_counter()
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    model = load(MODELS / 'spatial.json'); design = design or load(MODELS / 'design.json')
    initial_length = float(rng(seed, 203).lognormal(np.log(model['full_extent']['median_km']), model['full_extent']['log_sd']))
    attempts = []
    for attempt in range(8):
        geometry_seed = seed if attempt == 0 else int(rng(seed, 900+attempt).integers(1, 2**31))
        arrays, record = graph_prior(geometry_seed, model, design, target_length_km=initial_length)
        minimum_layer = int(arrays['layers'][arrays['values'][0] != 0].min())
        attempts.append(dict(attempt=attempt, geometry_seed=geometry_seed, minimum_active_layer=minimum_layer,
                             diagnostic=record['diagnostics'], boundary_contact=minimum_layer <= design['boundary_layers']))
        save(directory/'spatial_attempts.json', attempts)
        print(f"spatial {seed} candidate {attempt}: margin={minimum_layer}, Rhat={record['diagnostics']['maximum_rhat']:.3f}", flush=True)
        if minimum_layer > design['boundary_layers']:
            break
    else:
        save(directory/'failed_attempts.json', attempts)
        raise ValueError('Complete support remains constrained by the artificial frame')
    record.update(event_spatial_seed=seed, accepted_geometry_seed=geometry_seed, geometry_attempts=attempts,
                  retry_rule='only computational-boundary contact; target physical length and all event times fixed')
    z = arrays['values'][0]
    active = z != 0
    if active.sum() < 3:
        raise ValueError('Empty/degenerate event generated')
    # A triangle belongs to support when at least one of its vertices is active.
    support_triangles = np.any(active[arrays['triangles']], axis=1)
    support_vertices = np.unique(arrays['triangles'][support_triangles])
    measured = long_side(arrays['points'][support_vertices])
    scale = record['sampled_complete_long_km']/measured
    center = np.average(arrays['points'][active], axis=0, weights=arrays['mass'][active])
    physical = (arrays['points']-center)*scale
    rate = -z*model['reference_mean_m_per_Myr']/1e6
    raw = arrays['points']
    lower = physical[support_vertices].min(axis=0)-5
    upper = physical[support_vertices].max(axis=0)+5
    x = np.arange(np.floor(lower[0])+.5, np.ceil(upper[0]), 1.)
    y = np.arange(np.floor(lower[1])+.5, np.ceil(upper[1]), 1.)
    np.savez_compressed(directory / 'mesh.npz', points_km=physical, triangles=arrays['triangles'], edges=arrays['edges'],
                        reference_u_m_per_yr=rate, preference=arrays['preference'], mass=arrays['mass'],
                        active=active, x_km=x, y_km=y, raw_points=raw, boundary_layers=arrays['layers'])
    np.savez_compressed(directory / 'sampling.npz', traces=arrays['trace'], final_states=arrays['values'])
    mapper = FieldMap(physical, active)
    X, Y = np.meshgrid(x, y)
    query = mapper.weights(np.column_stack([X.ravel(), Y.ravel()]))
    full = mapper.evaluate(rate, query).reshape(len(y), len(x))
    if np.any(full[[0, -1]]) or np.any(full[:, [0, -1]]):
        raise ValueError('Complete support touches exported computational boundary')
    np.savez_compressed(directory / 'reference.npz', x_km=x, y_km=y, u_m_per_yr=full, support=full != 0)
    record.update(elapsed_seconds=time.perf_counter()-start, node_count=len(rate), active_nodes=int(active.sum()),
                  complete_long_km=long_side(physical[support_vertices]), source_to_physical_scale_km=scale,
                  field_bounds_km=[float(x[0]-.5), float(x[-1]+.5), float(y[0]-.5), float(y[-1]+.5)],
                  reference_min_mm_yr=float(full.min()*1000), support_area_km2=int(np.count_nonzero(full)),
                  geometric_mapping='one isotropic scale of the generated field; physical long-side target; no preset activity outline')
    record['minimum_active_mesh_layer'] = int(arrays['layers'][active].min())
    record['artificial_boundary_contact'] = bool(record['minimum_active_mesh_layer'] <= design['boundary_layers'])
    save(directory / 'spatial.json', record)
    return record

class FieldMap:
    """Continuous shared-node interpolation, with a zero-slope outer taper.

    Query weights are fixed in time, so spatial evaluation commutes with time
    integration. Inactive node values are always zero.
    """
    def __init__(self, points, active):
        self.points = np.asarray(points)
        self.active = np.asarray(active)
        self.tri = Delaunay(self.points)

    def weights(self, points):
        points = np.asarray(points, float)
        if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
            raise ValueError('Finite N x 2 coordinates required')
        simplex = self.tri.find_simplex(points)
        safe = np.maximum(simplex, 0)
        transform = self.tri.transform[safe]
        b = np.einsum('nij,nj->ni', transform[:, :2], points-transform[:, 2])
        barycentric = np.column_stack([b, 1-b.sum(axis=1)])
        vertices = self.tri.simplices[safe]
        active_fraction = np.sum(barycentric*self.active[vertices], axis=1)
        active_fraction = np.clip(active_fraction, 0, 1)
        factor = 3*active_fraction-2*active_fraction**2
        weights = barycentric*factor[:, None]
        weights[simplex < 0] = 0.
        return vertices.astype(np.int32), weights

    @staticmethod
    def evaluate(values, query):
        vertices, weights = query
        return np.einsum('ni,ni->n', np.asarray(values)[vertices], weights)
