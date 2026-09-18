"""Land-region generator: random field + threshold with an elliptical envelope (yZz 2026-09-09, archive message 150).

The field is ``F = E(x, y) + A · N(x, y)`` where ``E`` is a smooth elliptical envelope (1 at the centre, 0 on the
ellipse boundary, negative outside) and ``N`` is a Gaussian random field with an isotropic power-law spectrum
``P(k) ∝ k^(-beta)``. The threshold ``tau`` is found by bisection so that the land fraction of the domain equals the
sampled occupancy target. Cells within the outer ocean band are never land. The spectrum exponent, the noise
amplitude and the envelope axis ratio are the calibration parameters; their distributions are fitted to the 34
reference landmasses by ``scripts/pipeline_calibrate_landmask.py`` and stored in the sample configuration with the
evidence state ``本项目借鉴或合成改造``. Until calibration has been run the defaults below are assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
from scipy import ndimage


@dataclass
class LandmaskParams:
    nx: int = 500
    ny: int = 500
    dx_km: float = 1.0
    occupancy: float = 0.55          # target land fraction of the whole domain (design input)
    axis_ratio: float = 1.8          # envelope major/minor
    orientation_deg: float = 30.0
    beta: float = 3.0                # power-law spectral exponent of the random field
    noise_amplitude: float = 0.35    # noise std relative to the envelope range (0..1)
    min_wavelength_km: float = 2.0   # spectral cut-off (grid scale)
    ocean_band_km: float = 10.0      # outer ring that is always ocean
    center_x_km: float | None = None
    center_y_km: float | None = None
    seed: int = 0
    evidence_state: str = "尚待验证的假设"


def power_law_field(rng: np.random.Generator, ny: int, nx: int, beta: float, dx_km: float = 1.0,
                    min_wavelength_km: float = 2.0, max_wavelength_km: float | None = None) -> np.ndarray:
    """Zero-mean, unit-std Gaussian random field with P(k) ∝ k^-beta between the two wavelengths."""
    kx = np.fft.fftfreq(nx, d=dx_km)
    ky = np.fft.fftfreq(ny, d=dx_km)
    KX, KY = np.meshgrid(kx, ky)
    k = np.hypot(KX, KY)
    amp = np.zeros_like(k)
    nz = k > 0
    amp[nz] = k[nz] ** (-beta / 2.0)
    if min_wavelength_km:
        amp[k > 1.0 / min_wavelength_km] = 0.0
    if max_wavelength_km:
        amp[(k < 1.0 / max_wavelength_km) & nz] = 0.0
    phase = np.exp(2j * np.pi * rng.random((ny, nx)))
    field = np.real(np.fft.ifft2(amp * phase))
    field -= field.mean()
    s = field.std()
    return field / s if s > 0 else field


def ellipse_envelope(p: LandmaskParams, span_km: float | None = None) -> np.ndarray:
    """1 at the centre, 0 on the ellipse, decreasing outside. Without ``span_km`` the ellipse holds the occupancy
    target; with ``span_km`` its major axis equals ``span_km`` (shape-first mode)."""
    y, x = np.mgrid[0:p.ny, 0:p.nx].astype(float) * p.dx_km
    cx = p.center_x_km if p.center_x_km is not None else p.nx * p.dx_km / 2
    cy = p.center_y_km if p.center_y_km is not None else p.ny * p.dx_km / 2
    th = np.deg2rad(p.orientation_deg)
    xr = (x - cx) * np.cos(th) + (y - cy) * np.sin(th)
    yr = -(x - cx) * np.sin(th) + (y - cy) * np.cos(th)
    if span_km is None:
        area = p.occupancy * p.nx * p.ny * p.dx_km ** 2
        b = np.sqrt(area / (np.pi * p.axis_ratio))
        a = b * p.axis_ratio
    else:
        a = span_km / 2.0
        b = a / p.axis_ratio
    r = np.sqrt((xr / a) ** 2 + (yr / b) ** 2)
    return 1.0 - r


def _allowed_mask(p: LandmaskParams) -> np.ndarray:
    band = int(round(p.ocean_band_km / p.dx_km))
    allowed = np.ones((p.ny, p.nx), dtype=bool)
    if band > 0:
        allowed[:band, :] = allowed[-band:, :] = False
        allowed[:, :band] = allowed[:, -band:] = False
    return allowed


def _field(p: LandmaskParams, span_km: float | None = None) -> np.ndarray:
    rng = np.random.default_rng(p.seed)
    env = ellipse_envelope(p, span_km)
    noise = power_law_field(rng, p.ny, p.nx, p.beta, p.dx_km, p.min_wavelength_km)
    return env + p.noise_amplitude * noise


def generate(p: LandmaskParams) -> tuple[np.ndarray, dict]:
    """Occupancy-first mode: threshold so that the land fraction of the domain equals ``p.occupancy``."""
    field = _field(p)
    allowed = _allowed_mask(p)
    target = p.occupancy * p.nx * p.ny
    lo, hi = field[allowed].min(), field[allowed].max()
    tau = None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        n_land = int(((field > mid) & allowed).sum())
        if n_land > target:
            lo = mid
        else:
            hi = mid
        tau = mid
    land = (field > tau) & allowed
    return land, {"mode": "occupancy_first", "threshold": float(tau), "occupancy_target": p.occupancy,
                  "occupancy_achieved": float(land.mean()), "params": asdict(p)}


def generate_shape_first(p: LandmaskParams, span_km: float | None = None, tol_km: float = 4.0) -> tuple[np.ndarray, dict]:
    """Shape-first mode (yZz 2026-09-09, archive message 109 reading accepted): the shape is scaled to the window.

    The envelope's major axis equals ``span_km`` (default: domain minus the ocean band minus a 20 km margin) and the
    threshold is set by bisection so that the main component's minimum enclosing square equals ``span_km``. The
    occupancy is then a result (fill ratio × window share); the caller discards samples whose occupancy falls short
    of the preference band. Shape statistics of the outcome are calibrated through ``beta``, ``noise_amplitude`` and
    ``axis_ratio`` (``scripts/pipeline_calibrate_landmask.py``)."""
    span = span_km if span_km is not None else (p.nx * p.dx_km - 2 * p.ocean_band_km - 20.0)
    field = _field(p, span)
    allowed = _allowed_mask(p)
    lo, hi = field[allowed].min(), field[allowed].max()
    best = None
    for _ in range(40):
        tau = 0.5 * (lo + hi)
        land = (field > tau) & allowed
        m = mask_metrics(land, p.dx_km, quick=True)
        sq = m.get("min_square_km", 0.0)
        if best is None or abs(sq - span) < abs(best[0] - span):
            best = (sq, tau, land, m)
        if sq < span:
            hi = tau  # lower threshold → more land → larger extent
        else:
            lo = tau
        if abs(sq - span) < tol_km:
            break
    sq, tau, land, m = best
    return land, {"mode": "shape_first", "threshold": float(tau), "span_target_km": span, "min_square_achieved_km": float(sq),
                  "fill_achieved": float(m.get("fill_ratio_main", 0.0)), "occupancy_achieved": float(land.mean()), "params": asdict(p)}


def mask_metrics(land: np.ndarray, dx_km: float = 1.0, quick: bool = False) -> dict:
    """Shape statistics comparable with D's landmass metrics (4-connected components like D)."""
    n_land = int(land.sum())
    if n_land == 0:
        return {"land_fraction": 0.0, "fill_ratio_main": 0.0}
    lab, ncomp = ndimage.label(land, structure=ndimage.generate_binary_structure(2, 1))
    sizes = np.bincount(lab.ravel())[1:]
    largest = int(sizes.max())
    main = lab == (int(sizes.argmax()) + 1)
    ys, xs = np.nonzero(main)
    if quick:
        pts = np.vstack([xs, ys]).T.astype(float) * dx_km
        best = np.inf
        for deg in range(0, 90, 5):
            th = np.deg2rad(deg)
            rot = pts @ np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
            ext = rot.max(0) - rot.min(0) + dx_km
            best = min(best, float(ext.max()))
        return {"land_fraction": float(land.mean()), "components": int(ncomp), "largest_component_share": largest / n_land,
                "min_square_km": best, "fill_ratio_main": (largest * dx_km ** 2) / best ** 2 if best > 0 else 0.0}
    cov = np.cov(np.vstack([xs, ys]) * dx_km)
    ev = np.sort(np.linalg.eigvalsh(cov))[::-1]
    pca_ratio = float(np.sqrt(ev[0] / ev[1])) if ev[1] > 0 else float("inf")
    # perimeter (grid edges) of all land
    per = 0
    per += int((land[:, 1:] != land[:, :-1]).sum()) + int((land[1:, :] != land[:-1, :]).sum())
    per += int(land[0, :].sum() + land[-1, :].sum() + land[:, 0].sum() + land[:, -1].sum())
    perimeter_km = per * dx_km
    area_km2 = n_land * dx_km ** 2
    shoreline_dev = perimeter_km / (2 * np.sqrt(np.pi * area_km2))
    # minimum enclosing square by rotation search (0..90 deg) for the main component
    best = np.inf
    pts = np.vstack([xs, ys]).T.astype(float) * dx_km
    for deg in range(0, 90, 3):
        th = np.deg2rad(deg)
        rot = pts @ np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
        ext = rot.max(0) - rot.min(0) + dx_km
        best = min(best, float(ext.max()))
    fill = (largest * dx_km ** 2) / best ** 2 if best > 0 else 0.0
    # closed water (holes): water not connected to the boundary
    water = ~land
    wl, nw = ndimage.label(water, structure=np.ones((3, 3)))
    border_labels = set(np.unique(np.concatenate([wl[0, :], wl[-1, :], wl[:, 0], wl[:, -1]])))
    closed = np.isin(wl, [l for l in range(1, nw + 1) if l not in border_labels])
    return {"land_fraction": float(land.mean()), "land_area_km2": area_km2, "components": int(ncomp),
            "largest_component_share": largest / n_land, "pca_ratio_main": pca_ratio, "shoreline_development_grid": float(shoreline_dev),
            "perimeter_grid_km": perimeter_km, "min_square_km": best, "fill_ratio_main": float(fill),
            "closed_water_cells": int(closed.sum()), "touches_boundary": bool(land[0, :].any() or land[-1, :].any() or land[:, 0].any() or land[:, -1].any())}
