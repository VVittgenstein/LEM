"""Land statistics of the reference landmasses at about 1 km (workstream A of the pipeline task).

For each reference landmass with a GEBCO 30 arc-second subset the elevation window is resampled to square cells
(the longitude axis is scaled by the cosine of the mean latitude, so the cell is ``dy × dy`` with ``dy ≈ 0.925 km``),
depressions are filled (richdem, epsilon fill, D8), the D8 drainage area and the steepest-descent slope are computed,
and quantiles over land cells (elevation above 0 m) are returned for the elevation, the slope, the drainage area and
the stream-power kernel ``A^m · S^n`` (m = 0.45, n = 1, the process parameters used by the pipeline).

The kernel quantiles combine with an erosion-rate compilation to bound the erodibility ``K = E / (A^m S^n)``
(the "K reversal" of the task plan); everything here is computed from first-tier data and labelled accordingly.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

KM_PER_DEG = 111.195
QUANTS = (0.05, 0.25, 0.5, 0.75, 0.95)


def to_square_cells(z: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, float]:
    """Resample the longitude axis so that cells are square; returns (z_square, cell_km)."""
    dlat = float(abs(lat[1] - lat[0]))
    dlon = float(abs(lon[1] - lon[0]))
    phi = np.deg2rad(float(np.mean(lat)))
    dy_km = dlat * KM_PER_DEG
    dx_km = dlon * KM_PER_DEG * np.cos(phi)
    factor = dx_km / dy_km
    zs = ndimage.zoom(np.asarray(z, dtype=np.float32), (1.0, factor), order=1, mode="nearest")
    return zs, dy_km


def d8_area_and_slope(z: np.ndarray, cell_km: float, sea_level: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Depression-filled D8 drainage area (m²), steepest-descent slope (m/m) and land mask on the square grid."""
    import richdem as rd

    zz = np.asarray(z, dtype=np.float64)
    arr = rd.rdarray(zz, no_data=-32768.0)
    arr.geotransform = [0.0, cell_km * 1000.0, 0.0, 0.0, 0.0, -cell_km * 1000.0]
    filled = rd.FillDepressions(arr, epsilon=True, in_place=False, topology="D8")
    acc = rd.FlowAccumulation(filled, method="D8")
    area = np.asarray(acc, dtype=np.float64) * (cell_km * 1000.0) ** 2
    f = np.asarray(filled, dtype=np.float64)
    # steepest descent slope over the 8 neighbours of the filled surface
    dxm = cell_km * 1000.0
    slope = np.zeros_like(f)
    pad = np.pad(f, 1, mode="edge")
    for di, dj, dist in ((-1, 0, dxm), (1, 0, dxm), (0, -1, dxm), (0, 1, dxm),
                         (-1, -1, dxm * np.sqrt(2)), (-1, 1, dxm * np.sqrt(2)), (1, -1, dxm * np.sqrt(2)), (1, 1, dxm * np.sqrt(2))):
        nb = pad[1 + di:1 + di + f.shape[0], 1 + dj:1 + dj + f.shape[1]]
        slope = np.maximum(slope, (f - nb) / dist)
    land = zz > sea_level
    return area, slope, land


def land_quantiles(z: np.ndarray, area: np.ndarray, slope: np.ndarray, land: np.ndarray, m: float = 0.45, n: float = 1.0,
                   min_area_cells: int = 1, cell_km: float = 1.0) -> dict:
    sel = land & (area >= min_area_cells * (cell_km * 1000.0) ** 2)
    out = {"land_cells": int(land.sum()), "cells_used": int(sel.sum())}
    if sel.sum() == 0:
        return out
    kern = np.power(area[sel], m) * np.power(np.maximum(slope[sel], 1e-6), n)
    for name, vals in (("elevation_m", z[sel]), ("slope", slope[sel]), ("area_m2", area[sel]), ("kernel_AmSn", kern)):
        q = np.quantile(vals, QUANTS)
        out[name] = {f"p{int(p * 100):02d}": float(v) for p, v in zip(QUANTS, q)}
        out[name]["mean"] = float(np.mean(vals))
    # kernel restricted to cells with A ≥ 1 km² and ≥ 10 km² (channel cells)
    for thr_km2 in (1.0, 10.0, 100.0):
        s2 = sel & (area >= thr_km2 * 1e6)
        if s2.sum() > 10:
            k2 = np.power(area[s2], m) * np.power(np.maximum(slope[s2], 1e-6), n)
            out[f"kernel_AmSn_A_ge_{int(thr_km2)}km2"] = {f"p{int(p * 100):02d}": float(v) for p, v in zip(QUANTS, np.quantile(k2, QUANTS))}
            out[f"kernel_AmSn_A_ge_{int(thr_km2)}km2"]["cells"] = int(s2.sum())
    return out
