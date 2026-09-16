from dataclasses import dataclass
import numpy as np
from scipy.ndimage import gaussian_filter
from .config import LANDFORMS, PRESETS


@dataclass
class Inputs:
    labels: np.ndarray
    elevation: np.ndarray
    uplift: np.ndarray
    province: np.ndarray
    landform: np.ndarray | None = None
    landform_weights: np.ndarray | None = None
    planned_landforms: tuple[str, ...] = ()
    land_mask: np.ndarray | None = None
    ridge_field: np.ndarray | None = None
    ridge_system_count: int = 0


def _smooth_field(rng, shape, scale=0.12):
    """Return a reproducible, unit-variance field with grid-scale noise removed."""
    field = rng.normal(size=shape)
    sigma = max(1.0, min(shape) * scale)
    field = gaussian_filter(field, sigma=sigma, mode="reflect")
    field -= field.mean()
    standard_deviation = field.std()
    if standard_deviation > 0:
        field /= standard_deviation
    return field


def _island(c, rng, x, y):
    """Construct one star-shaped island with an approximate target occupancy.

    Grids whose one-cell ocean ring cannot enclose the requested occupancy retain
    the ocean ring and fill every available interior cell. The default and other
    adequately sized grids retain the configured target to within one cell.
    """
    center_x, center_y = rng.uniform(-0.10, 0.10, size=2)
    angle = rng.uniform(0, np.pi)
    aspect = rng.uniform(0.72, 1.38)
    xx, yy = x - center_x, y - center_y
    xr = np.cos(angle) * xx + np.sin(angle) * yy
    yr = -np.sin(angle) * xx + np.cos(angle) * yy
    theta = np.arctan2(yr, xr)
    radius = np.hypot(xr / aspect, yr * aspect)
    boundary_shape = np.ones(c.shape)
    for harmonic in range(2, 9):
        amplitude = rng.uniform(0.025, 0.105) / np.sqrt(harmonic)
        boundary_shape += amplitude * np.cos(harmonic * theta + rng.uniform(0, 2 * np.pi))
    radial_coordinate = radius / np.clip(boundary_shape, 0.75, 1.25)

    buffer_cells = c.ocean_buffer_cells
    eligible = np.ones(c.shape, dtype=bool)
    eligible[:buffer_cells, :] = eligible[-buffer_cells:, :] = False
    eligible[:, :buffer_cells] = eligible[:, -buffer_cells:] = False
    requested = int(round(c.target_land_fraction * c.nx * c.ny))
    available = int(eligible.sum())
    land_cells = min(requested, available)
    eligible_values = radial_coordinate[eligible]
    if land_cells == available:
        threshold = float(np.nextafter(eligible_values.max(), np.inf))
    else:
        partition = np.partition(eligible_values, land_cells)
        threshold = 0.5 * (partition[land_cells - 1] + partition[land_cells])
    land = eligible & (radial_coordinate < threshold)

    missing = land_cells - int(land.sum())
    if missing:
        candidates = np.flatnonzero(eligible & ~land)
        order = np.argsort(radial_coordinate.ravel()[candidates], kind="stable")
        land.ravel()[candidates[order[:missing]]] = True
    signed = threshold - radial_coordinate
    signed[~eligible] = np.minimum(signed[~eligible], -0.02)
    return land, signed


def _landform_plan(c, rng, x, y, land):
    count = int(rng.integers(3, 6))
    preset_index = PRESETS.index(c.preset)
    required = np.array([LANDFORMS.index("mountain"), LANDFORMS.index("plain")])
    remaining = np.array([index for index in range(len(LANDFORMS)) if index not in required])
    preference = np.roll(remaining, preset_index % len(remaining))
    jitter = rng.random(len(preference))
    extra = preference[np.argsort(jitter + np.linspace(0.0, 0.25, len(preference)))[:count - 2]]
    selected = np.concatenate((required, extra))
    rng.shuffle(selected)

    phase = rng.uniform(0, 2 * np.pi)
    centers = []
    for index in range(count):
        theta = phase + 2 * np.pi * index / count + rng.uniform(-0.16, 0.16)
        radius = rng.uniform(0.18, 0.43)
        centers.append((radius * np.cos(theta), radius * np.sin(theta)))
    influence = np.empty((*c.shape, count), dtype=np.float64)
    broad_noise = _smooth_field(rng, c.shape, 0.16)
    for index, (cx, cy) in enumerate(centers):
        width = rng.uniform(0.38, 0.54)
        influence[..., index] = -((x - cx) ** 2 + (y - cy) ** 2) / width**2
        influence[..., index] += 0.10 * broad_noise + rng.uniform(-0.08, 0.08)
    influence -= influence.max(axis=2, keepdims=True)
    weights = np.exp(3.2 * influence)
    weights /= weights.sum(axis=2, keepdims=True)
    local_index = np.argmax(weights, axis=2)
    landform = np.full(c.shape, 255, dtype=np.uint8)
    landform[land] = selected[local_index[land]].astype(np.uint8)
    planned = tuple(LANDFORMS[index] for index in selected)
    return landform, weights.astype(np.float32), selected, planned


def _ridge_network(c, rng, x, y):
    """Return multiple smoothly curved, longitudinally modulated mountain systems."""
    core_total = np.zeros(c.shape, dtype=np.float64)
    flank_total = np.zeros(c.shape, dtype=np.float64)
    count = int(rng.integers(2, 5))
    previous_end = None
    for index in range(count):
        length = rng.uniform(1.55, 2.20) if index == 0 else rng.uniform(1.00, 1.75)
        angle = rng.uniform(0, np.pi)
        direction = np.array([np.cos(angle), np.sin(angle)])
        normal = np.array([-direction[1], direction[0]])
        if index > 0 and previous_end is not None and rng.random() < 0.32:
            start = previous_end + rng.uniform(-0.18, 0.18, size=2)
        else:
            start = rng.uniform(-0.72, 0.28, size=2)

        samples = int(rng.integers(72, 112))
        t = np.linspace(0.0, 1.0, samples)
        increments = gaussian_filter(rng.normal(size=samples), sigma=rng.uniform(4.0, 8.0),
                                     mode="reflect")
        walk = np.cumsum(increments)
        walk -= np.linspace(walk[0], walk[-1], samples)
        walk /= max(float(np.max(np.abs(walk))), np.finfo(float).eps)
        phase1, phase2, phase3 = rng.uniform(0, 2 * np.pi, size=3)
        curve = (rng.uniform(0.15, 0.31) * np.sin(np.pi * t) * walk
                 + rng.uniform(0.08, 0.19) * np.sin(2 * np.pi * t + phase1)
                 + rng.uniform(0.035, 0.085) * np.sin(5 * np.pi * t + phase2))
        along = start[None, :] + length * t[:, None] * direction[None, :]
        points = along + curve[:, None] * normal[None, :]
        previous_end = points[-1]

        longitudinal = (1.0 + rng.uniform(0.10, 0.30) * np.sin(2 * np.pi * t + phase2)
                        + rng.uniform(0.06, 0.16) * np.sin(5 * np.pi * t + phase3))
        longitudinal *= 0.10 + 0.90 * np.sin(np.pi * t)**0.55
        core_width = rng.uniform(0.045, 0.082) * (
            1.0 + rng.uniform(0.15, 0.34) * np.sin(2 * np.pi * t + phase1))
        flank_width = rng.uniform(0.135, 0.245) * (
            1.0 + rng.uniform(0.12, 0.28) * np.sin(2 * np.pi * t + phase3))
        base_amplitude = rng.uniform(0.76, 1.04)

        distance_squared = np.full(c.shape, np.inf)
        nearest_index = np.zeros(c.shape, dtype=np.int16)
        for sample_index, point in enumerate(points):
            candidate = (x - point[0])**2 + (y - point[1])**2
            closer = candidate < distance_squared
            distance_squared[closer] = candidate[closer]
            nearest_index[closer] = sample_index
        local_amplitude = base_amplitude * longitudinal[nearest_index]
        local_core_width = np.maximum(core_width[nearest_index], 0.020)
        local_flank_width = np.maximum(flank_width[nearest_index], 0.070)
        distance = np.sqrt(distance_squared)
        core_profile = np.exp(-distance_squared / local_core_width**2)
        flank_profile = np.exp(-distance_squared / local_flank_width**2)
        parallel_structure = 0.78 + 0.22 * np.cos(
            np.pi * distance / np.maximum(1.8 * local_core_width, 0.025))**2
        core_total += local_amplitude * core_profile
        flank_total += local_amplitude * flank_profile * parallel_structure

    sigma = max(1.0, min(c.shape) * 0.0025)
    core_total = gaussian_filter(core_total, sigma=sigma, mode="nearest")
    flank_total = gaussian_filter(flank_total, sigma=sigma, mode="nearest")
    return np.clip(core_total, 0.0, 2.8), np.clip(flank_total, 0.0, 3.2), count


def _geology_fields(c, rng, x, y):
    phase = rng.uniform(0, 2 * np.pi)
    centers = np.array([
        [-0.48, -0.16], [0.34, -0.43], [0.46, 0.30], [-0.28, 0.46]
    ])
    centers += rng.uniform(-0.16, 0.16, size=centers.shape)
    scores = []
    texture = _smooth_field(rng, c.shape, 0.18)
    for cx, cy in centers:
        width = rng.uniform(0.48, 0.72)
        scores.append(-((x - cx) ** 2 + (y - cy) ** 2) / width**2
                      + 0.12 * texture + rng.uniform(-0.12, 0.12))
    scores = np.stack(scores, axis=2)
    scores -= scores.max(axis=2, keepdims=True)
    weights = np.exp(2.2 * scores)
    weights /= weights.sum(axis=2, keepdims=True)
    province = np.argmax(weights, axis=2).astype(np.uint8)

    folds = 320 * np.sin(4.5 * np.pi * x + 1.8 * np.pi * y + phase)
    blocks = 260 * np.tanh(3.2 * np.sin(4 * np.pi * x + phase)) + 90 * y
    massif = 520 * np.exp(-((x - centers[3, 0]) ** 2 + (y - centers[3, 1]) ** 2) / 0.16)
    styles = np.stack((90 * x + 45 * texture, folds, blocks, massif,
                       0.35 * folds + 0.25 * blocks + 0.40 * massif), axis=2)
    preset_index = PRESETS.index(c.preset)
    if c.preset == "mosaic":
        style_weights = np.concatenate((weights, np.zeros((*c.shape, 1))), axis=2)
        warp = np.sum(style_weights * styles, axis=2)
    else:
        warp = 0.82 * styles[..., preset_index] + 0.18 * np.sum(weights * styles[..., :4], axis=2)
    return province, weights, warp, texture


def generate(config, volume_path=None):
    """Generate seeded island geometry, continuous forcing and 3D lithology.

    The uint8 volume uses ``(y, x, z)`` order. Depth is measured downward from
    each initial surface column and co-uplifts with that column in the backend.
    Categorical maps are diagnostics of the dominant member of continuous
    spatial weights used to construct uplift and stratigraphic geometry.
    """
    c = config
    seed_sequence = np.random.SeedSequence([c.seed, PRESETS.index(c.preset)])
    rng = np.random.default_rng(seed_sequence)
    lithology_rng = np.random.default_rng(np.random.SeedSequence(
        [c.seed, PRESETS.index(c.preset), c.lithology_seed_offset, 911]))
    y, x = np.meshgrid(np.linspace(-1, 1, c.ny), np.linspace(-1, 1, c.nx), indexing="ij")
    land, shore_score = _island(c, rng, x, y)
    landform, landform_weights, selected, planned = _landform_plan(c, rng, x, y, land)
    province, geology_weights, warp, texture = _geology_fields(c, lithology_rng, x, y)

    uplift_rates = np.array([7.0e-4, 4.0e-4, 7.0e-5, 3.2e-4, 4.0e-5])
    selected_rates = uplift_rates[selected]
    uplift = np.sum(landform_weights * selected_rates, axis=2)
    uplift *= 1.0 + 0.12 * np.tanh(texture)
    positive_scale = max(float(np.percentile(shore_score[land], 80)), np.finfo(float).eps)
    coastal_taper = np.clip(shore_score / (0.32 * positive_scale), 0.0, 1.0)

    relief_factors = np.array([1.28, 0.82, 0.26, 0.96, 0.20])[selected]
    relief = np.sum(landform_weights * relief_factors, axis=2)
    ridge_core, ridge_flank, ridge_count = _ridge_network(c, rng, x, y)
    mountain_weight = np.zeros(c.shape, dtype=np.float64)
    if 0 in selected:
        mountain_weight = landform_weights[..., int(np.flatnonzero(selected == 0)[0])]
    hills_weight = np.zeros(c.shape, dtype=np.float64)
    if 1 in selected:
        hills_weight = landform_weights[..., int(np.flatnonzero(selected == 1)[0])]
    ridge_support = np.clip(0.18 + 1.25 * mountain_weight + 0.45 * hills_weight, 0.18, 1.6)
    ridge = np.clip(0.55 * ridge_core + 0.58 * ridge_flank, 0.0, 3.0)
    mountain_belt = np.clip(ridge * (0.82 + 0.38 * mountain_weight)
                             + 0.04 * mountain_weight, 0.0, 2.5)
    ridge_texture = (1.0 + 0.20 * np.tanh(_smooth_field(rng, c.shape, 0.035))
                     + 0.10 * np.tanh(_smooth_field(rng, c.shape, 0.012)))
    uplift *= 0.14 + 1.10 * ridge_core * ridge_support + 0.62 * ridge_flank * ridge_support
    uplift *= np.clip(ridge_texture, 0.62, 1.42)
    uplift += 8.0e-5 * hills_weight * ridge_flank
    uplift = np.maximum(uplift * coastal_taper, 0.0)
    uplift *= c.uplift_scale
    uplift[~land] = 0.0
    inland = np.clip(shore_score / positive_scale, 0.0, 1.8)
    coastal_platform = 38 * np.clip(shore_score / (0.12 * positive_scale), 0.0, 1.0)
    lowland_base = 75 * inland * (0.55 + 0.45 * relief)
    relief_texture = (1.0 + 0.24 * np.tanh(_smooth_field(rng, c.shape, 0.030))
                      + 0.10 * np.tanh(_smooth_field(rng, c.shape, 0.010)))
    ridge_height = c.initial_relief_scale * (175 * ridge_core + 245 * ridge_flank)
    ridge_height *= (0.72 + 0.28 * mountain_weight) * np.clip(inland / 0.22, 0.0, 1.0)
    ridge_height *= np.clip(relief_texture, 0.58, 1.48)
    hill_height = 95 * c.initial_relief_scale * hills_weight * inland * (1.0 + 0.12 * np.tanh(texture))
    positive_height = coastal_platform + lowland_base + ridge_height + hill_height
    negative_scale = max(float(np.percentile(-shore_score[~land], 80)), np.finfo(float).eps)
    ocean_depth = 20 + 260 * np.clip(-shore_score / negative_scale, 0, 1.5)
    elevation = np.where(land, np.maximum(positive_height, 0.05), -ocean_depth).astype(np.float64)

    shape = (*c.shape, c.nz)
    labels = (np.empty(shape, dtype=np.uint8) if volume_path is None else
              np.lib.format.open_memmap(volume_path, mode="w+", dtype=np.uint8, shape=shape))
    intrusive_center = np.unravel_index(np.argmax(geology_weights[..., 3]), c.shape)
    iy, ix = intrusive_center
    intrusion_radius = ((x - x[iy, ix]) / 0.38) ** 2 + ((y - y[iy, ix]) / 0.34) ** 2
    for k in range(c.nz):
        depth_fraction = k / (c.nz - 1)
        depth = k * c.dz
        depth_texture = 55 * np.sin(2.5 * texture + 5.0 * depth_fraction)
        stratigraphic_depth = depth + warp + depth_texture
        slab = (np.floor(stratigraphic_depth / 230).astype(np.int32) % 3).astype(np.uint8)
        slab[stratigraphic_depth > c.depth * (0.60 + 0.05 * geology_weights[..., 0])] = 3
        intrusion = intrusion_radius < 0.16 + 0.82 * depth_fraction
        if c.preset == "intrusive_massif":
            intrusion |= intrusion_radius < 0.08 + 1.05 * depth_fraction
        slab[intrusion] = 4
        labels[:, :, k] = slab
    if isinstance(labels, np.memmap):
        labels.flush()
    return Inputs(labels, elevation, uplift, province, landform, landform_weights,
                  planned, land, ridge.astype(np.float32), ridge_count)


def exposed_labels(labels, cumulative_erosion, dz):
    """Return the bedrock voxel intercept for signed net cumulative erosion.

    Positive values use ``ceil(cumulative_erosion / dz)``. Finite negative
    values select depth index zero: the original top bedrock material. This is
    a conservative bedrock lookup and does not identify deposited sediment.
    """
    if labels.ndim != 3 or labels.dtype != np.uint8 or labels.shape[2] < 2:
        raise ValueError("labels must be a uint8 (y,x,z) volume")
    if not np.isfinite(dz) or dz <= 0:
        raise ValueError("dz must be positive and finite")
    erosion = np.broadcast_to(np.asarray(cumulative_erosion, dtype=float), labels.shape[:2])
    if not np.all(np.isfinite(erosion)):
        raise ValueError("net cumulative erosion must be finite for bedrock voxel lookup")
    index = np.ceil(np.maximum(erosion, 0.0) / dz)
    if np.any(index >= labels.shape[2]):
        raise ValueError("bedrock voxel column exhausted: increase depth or shorten simulation")
    return np.take_along_axis(labels, index.astype(np.intp)[..., None], axis=2)[..., 0].astype(np.int32)
