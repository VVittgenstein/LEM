"""Boundary traversals, area eligibility and probabilistic size/depth preference."""
import time
from scipy.special import logsumexp
from .common import *
from .sampling_geometry import (FullSupport, platform, rotation, to_source,
                                window_polygon, shapely, WORLD, LOCAL_CORNERS)

SAMPLING_VERSION = 'basin-window-traversal-20260928'
DESIGN = dict(window_side_km=500., paths_per_block=160, positions_per_path=24, maximum_blocks=4,
    entry_angle_half_range_deg=65., minimum_coverage=.10, maximum_coverage=.70,
    coverage_decay_start=.50, area_retention_weight=4., natural_boundary_weight=1.5,
    position_baseline=6., position_size_weight=6., coverage_decay_weight=1.5,
    depth_quadrature_km=1.,
    parameter_identity='coverage thresholds and preference directions follow the discussion; numerical weight coefficients are implementation design values')


def gate(overlap, full_area, platform_area, design=DESIGN):
    if not np.isfinite([overlap, full_area, platform_area]).all() or min(full_area, platform_area) <= 0:
        raise ValueError('Areas must be finite and full/platform areas positive')
    coverage = overlap/platform_area
    small = full_area/platform_area < design['minimum_coverage']
    if overlap <= 1e-8:
        return 'no_overlap'
    if coverage > design['maximum_coverage']+1e-12:
        return 'above_maximum'
    if not small and coverage < design['minimum_coverage']-1e-12:
        return 'below_minimum'
    return 'eligible'


def weight_terms(overlap, full_area, platform_area, boundary_fraction, depth, design=DESIGN):
    coverage = overlap/platform_area
    retention = float(np.clip(overlap/min(full_area, platform_area), 0., 1.))
    depth = float(np.clip(depth, 0., 1.))
    size = float(np.sqrt(full_area/platform_area))
    boundary = float(np.clip(boundary_fraction, 0., 1.))
    excess = max(0., (coverage-design['coverage_decay_start']) /
                 (design['maximum_coverage']-design['coverage_decay_start']))
    area_log = design['area_retention_weight']*retention
    boundary_log = design['natural_boundary_weight']*boundary
    position_log = -(design['position_baseline']+design['position_size_weight']*size)*depth**2
    coverage_log = -design['coverage_decay_weight']*excess**2
    return dict(coverage=coverage, retained_fraction=retention, natural_boundary_fraction=boundary,
        relative_size=size, normalized_depth=depth, area_log_weight=area_log,
        boundary_log_weight=boundary_log, position_log_weight=position_log,
        coverage_log_weight=coverage_log, position_factor=float(np.exp(position_log)),
        coverage_factor=float(np.exp(coverage_log)),
        log_weight=float(area_log+boundary_log+position_log+coverage_log))


def selection_probabilities(log_weights):
    values = np.asarray(log_weights, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError('Expected a nonempty finite vector of log weights')
    return np.exp(values-logsumexp(values))


def candidate_metrics(field, land, center, matrix, design=DESIGN):
    local = field.local_geometry(center, matrix)
    overlap = local.intersection(land.geometry)
    area = float(overlap.area)
    status = gate(area, field.area, land.area, design)
    result = dict(status=status, continuous_overlap_km2=area, coverage=area/land.area)
    if status != 'eligible':
        return result
    cells, mean_distance = land.interior_measure(local, overlap.bounds)
    raster_status = gate(cells, field.area, land.area, design)
    result.update(raster_overlap_km2=cells, raster_coverage=cells/land.area)
    if raster_status != 'eligible':
        result['status'] = 'raster_'+raster_status
        return result
    natural = field.local_boundary(center, matrix).intersection(WORLD)
    natural_inside = natural.intersection(land.geometry)
    length, inside_length = float(natural.length), float(natural_inside.length)
    result.update(weight_terms(area, field.area, land.area, inside_length/length if length else 0.,
                               mean_distance/land.maximum_distance, design))
    centroid = local.centroid
    result.update(continuous_crop_area_km2=float(local.intersection(WORLD).area),
        mean_platform_boundary_distance_km=mean_distance,
        maximum_platform_boundary_distance_km=land.maximum_distance,
        natural_boundary_in_window_km=length, natural_boundary_in_platform_km=inside_length,
        field_centroid_x_km=float(centroid.x), field_centroid_y_km=float(centroid.y),
        full_inside_platform=bool(land.geometry.covers(local)),
        outside_platform_area_km2=max(0., field.area-area),
        outside_outer_platform_area_km2=max(0., field.area-float(local.intersection(land.outer_geometry).area)))
    return result


def propose_paths(field, random, design=DESIGN):
    for _ in range(design['paths_per_block']):
        boundary, outward, details = field.boundary_draw(random)
        angle = float(random.uniform(0., 2*np.pi))
        matrix = rotation(angle)
        deviation = float(random.uniform(-design['entry_angle_half_range_deg'], design['entry_angle_half_range_deg']))
        direction = rotation(np.radians(deviation))@(-outward)
        radius = 250.*(abs(direction@matrix[:, 0])+abs(direction@matrix[:, 1]))
        projected = (field.vertices-boundary)@direction
        low, high = float(projected.min()-radius-2.), float(projected.max()+radius+2.)
        start, end = boundary+low*direction, boundary+high*direction
        if field.geometry.intersects(window_polygon(start, matrix)) or field.geometry.intersects(window_polygon(end, matrix)):
            raise ValueError('Traversal endpoints must lie fully outside the event')
        strata = (np.arange(design['positions_per_path'])+random.random(design['positions_per_path']))/design['positions_per_path']
        centers = boundary+(low+(high-low)*strata)[:, None]*direction
        yield dict(**details, boundary_source_km=boundary.tolist(), inward_direction=direction.tolist(),
            direction_deviation_deg=deviation, rotation_deg=float(np.degrees(angle)),
            interval_km=[low, high], start_center_source_km=start.tolist(), end_center_source_km=end.tolist(),
            endpoints_outside=True), centers, strata, matrix


def choose_window(event, directory, output_directory=None, design=None):
    started = time.perf_counter()
    directory = Path(directory)
    destination = Path(output_directory) if output_directory is not None else directory
    destination.mkdir(parents=True, exist_ok=True)
    design = dict(DESIGN if design is None else design)
    field, land = FullSupport(directory), platform(event['seed'])
    proposal_random, selection_random = rng(event['event_seed'], 501), rng(event['event_seed'], 502)
    candidates, paths, eligible = [], [], []
    for block in range(design['maximum_blocks']):
        for path, centers, strata, matrix in propose_paths(field, proposal_random, design):
            path['path_id'] = len(paths); path['block'] = block
            paths.append(path)
            for j, (center, fraction) in enumerate(zip(centers, strata)):
                row = dict(candidate_id=len(candidates), path_id=path['path_id'], stratum=j,
                    center_source_x_km=float(center[0]), center_source_y_km=float(center[1]),
                    rotation_deg=path['rotation_deg'], traversal_fraction=float(fraction),
                    selection_probability=0., selected=False,
                    **candidate_metrics(field, land, center, matrix, design))
                if row['status'] == 'eligible':
                    eligible.append(row['candidate_id'])
                candidates.append(row)
        if eligible:
            break
    save(destination/'entry_paths.json', dict(version=SAMPLING_VERSION, paths=paths))
    if not eligible:
        csvsave(destination/'window_candidates.csv', candidates)
        save(destination/'selection_failure.json', dict(reason='No eligible window; event was retained', design=design))
        raise RuntimeError(f"No eligible window for {event['event_id']}; event generation was not repeated")
    probabilities = selection_probabilities([candidates[i]['log_weight'] for i in eligible])
    for i, probability in zip(eligible, probabilities):
        candidates[i]['selection_probability'] = float(probability)
    selected_id = int(selection_random.choice(eligible, p=probabilities))
    selected = candidates[selected_id]
    selected['selected'] = True
    center = np.array([selected['center_source_x_km'], selected['center_source_y_km']])
    matrix = rotation(np.radians(selected['rotation_deg']))
    x, y = np.meshgrid(np.arange(500)+.5, np.arange(500)+.5)
    points = to_source(np.column_stack([x.ravel(), y.ravel()]), center, matrix)
    query = field.mapper.weights(points)
    values = field.mapper.evaluate(field.rate, query).reshape(500, 500)
    pink = (values != 0) & land.mask
    if pink.sum() != selected['raster_overlap_km2']:
        raise ValueError('Continuous support/cell-center prediction differs from the field evaluator')
    if gate(float(pink.sum()), field.area, land.area, design) != 'eligible':
        raise ValueError('Selected window violates the array coverage contract')
    np.savez_compressed(destination/'window.npz', u_m_per_yr=values, support=values != 0,
                        pink_overlap=pink, query_vertices=query[0], query_weights=query[1])
    corners = to_source(LOCAL_CORNERS, center, matrix)
    with np.load(directory/'reference.npz') as full:
        lower = np.minimum([full['x_km'][0]-.5, full['y_km'][0]-.5], corners.min(axis=0))
        upper = np.maximum([full['x_km'][-1]+.5, full['y_km'][-1]+.5], corners.max(axis=0))
    middle = (lower+upper)/2; span = float(max(upper-lower)*1.04)
    statuses = {s: sum(r['status'] == s for r in candidates) for s in sorted({r['status'] for r in candidates})}
    record = dict(**selected, seed=event['seed'], event_id=event['event_id'], version=SAMPLING_VERSION,
        design=design, rotation_matrix=matrix.tolist(), center_source_km=center.tolist(),
        corners_source_km=corners.tolist(), window_side_km=500.,
        common_extent_km=[middle[0]-span/2, middle[0]+span/2, middle[1]-span/2, middle[1]+span/2],
        common_extent_identity='adaptive plotting extent enclosing complete field and fixed 500 km window',
        complete_support_area_km2=field.area, platform_area_km2=land.area,
        small_event_exemption=bool(field.area/land.area < design['minimum_coverage']),
        crop_support_area_km2=int(np.count_nonzero(values)), platform_overlap_km2=int(pink.sum()),
        candidate_count=len(candidates), eligible_count=len(eligible), path_count=len(paths), status_counts=statuses,
        rule='complete-boundary traversals; area gates; weighted random selection using retention, natural zero boundary, size/depth attenuation and coverage attenuation',
        probability_identity='normalized across eligible proposals, without spatial-density correction or quotas',
        no_post_crop_rescale=True, base_source=str(land.path), base_sha256=sha(land.path),
        field_input_hashes={name: sha(directory/name) for name in ('mesh.npz', 'reference.npz', 'event.json', 'time_model.npz')},
        natural_boundary_max_abs_rate_m_per_yr=field.boundary_max_rate,
        geometry_library=dict(version=shapely.__version__, path=shapely.__file__),
        elapsed_window_sampling_seconds=time.perf_counter()-started,
        convergent_axis_requirements_inherited=False)
    csvsave(destination/'window_candidates.csv', candidates)
    save(destination/'selection.json', record)
    return record
