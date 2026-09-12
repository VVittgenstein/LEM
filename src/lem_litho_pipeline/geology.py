"""Column-relative stratigraphy; no absolute-elevation voxel interpretation."""
from dataclasses import dataclass
import numpy as np
from scipy.ndimage import map_coordinates
from .config import PRESETS


@dataclass
class Inputs:
    labels: np.ndarray
    elevation: np.ndarray
    uplift: np.ndarray
    province: np.ndarray


def generate(config, volume_path=None):
    """Build uint8 (y,x,z) labels using one floating-point depth slab at a time.

    Smooth 3D heterogeneity is interpolated from a small seeded control lattice.
    Depth is measured downward from each initial surface column, co-uplifting
    with it. Provinces are experimental geological environments.
    """
    c = config
    rng = np.random.default_rng(c.seed)
    y, x = np.meshgrid(np.linspace(0, 1, c.ny), np.linspace(0, 1, c.nx), indexing="ij")
    lattice = rng.normal(size=(9, 9, 9)).astype(np.float32)
    phase = rng.uniform(0, 2 * np.pi)
    smooth = map_coordinates(lattice, [y * 8, x * 8, np.zeros(c.shape)], order=1)
    province = np.zeros(c.shape, dtype=np.uint8)
    if c.preset == "mosaic":
        province[:] = (x >= 0.5).astype(np.uint8) + 2 * (y >= 0.5).astype(np.uint8)
    else:
        province[:] = PRESETS.index(c.preset)
    fold = 350 * np.sin(6 * np.pi * x + 2 * np.pi * y + phase)
    fault = 300 * np.floor(5 * x) + 120 * y
    radius = ((x - 0.72) / 0.26)**2 + ((y - 0.72) / 0.30)**2
    warp = np.choose(province, [80 * x, fold, fault, 150 * np.sin(4 * x)])
    uplift = np.choose(province, [np.full(c.shape, 0.0003),
                      0.0004 + 0.0008 * np.sin(np.pi * x)**2,
                      0.0003 + 0.0002 * (np.floor(5 * x) % 3),
                      0.0003 + 0.0008 * np.exp(-radius)])
    envelope = np.sin(np.pi * x) * np.sin(np.pi * y)
    elevation = (20 + 120 * envelope + 2 * smooth).astype(np.float64)
    elevation[[0, -1], :] = 0
    elevation[:, [0, -1]] = 0
    uplift[[0, -1], :] = 0
    uplift[:, [0, -1]] = 0
    shape = (*c.shape, c.nz)
    labels = (np.empty(shape, dtype=np.uint8) if volume_path is None else
              np.lib.format.open_memmap(volume_path, mode="w+", dtype=np.uint8, shape=shape))
    for k in range(c.nz):
        noise = map_coordinates(lattice, [y * 8, x * 8, np.full(c.shape, 8 * k / (c.nz - 1))], order=1)
        strat_depth = k * c.dz + warp + 70 * noise
        slab = (np.floor(strat_depth / 200).astype(np.int32) % 3).astype(np.uint8)
        slab[strat_depth > c.depth * 0.65] = 3
        intrusion = (province == 3) & (radius < 0.3 + 1.2 * k / (c.nz - 1))
        slab[intrusion] = 4
        labels[:, :, k] = slab
    if isinstance(labels, np.memmap):
        labels.flush()
    return Inputs(labels, elevation, uplift, province)


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
