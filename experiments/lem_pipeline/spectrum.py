"""Surface relief spectrum of the reference landmasses (yZz 2026-09-09: the generator's spectral exponent is to be
measured from the reference surfaces, archive message 150 reading; decision recorded in the ledger).

For each reference landmass with a GEBCO 30 arc-second subset (session A, ``references/data/2026-09-08-q1-data/A/subsets``)
the two-dimensional power spectrum of the elevation field (land and sea floor together, since the coastline is the
zero level set of that field) is radially averaged with physical wavenumbers (longitude spacing scaled by the cosine
of the latitude) and the exponent ``beta`` of ``P(k) ∝ k^-beta`` is fitted by least squares in log-log space over a
wavelength band. ``P`` is the mean squared Fourier amplitude per wavenumber cell, the same convention as
``landmask.power_law_field`` (amplitude ∝ k^(-beta/2)). A Hann taper is applied after removing the mean.
"""
from __future__ import annotations

import numpy as np

KM_PER_DEG = 111.195


def radial_spectrum(z: np.ndarray, dx_km: float, dy_km: float, nbins: int = 40) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (k centres in 1/km, mean power per wavenumber cell, counts) on logarithmic bins."""
    z = np.asarray(z, dtype=float)
    z = z - z.mean()
    ny, nx = z.shape
    wy = np.hanning(ny)[:, None]
    wx = np.hanning(nx)[None, :]
    F = np.fft.fft2(z * wy * wx)
    P = np.abs(F) ** 2 / (nx * ny)
    kx = np.fft.fftfreq(nx, d=dx_km)
    ky = np.fft.fftfreq(ny, d=dy_km)
    K = np.hypot(kx[None, :], ky[:, None])
    kmin = max(1.0 / (nx * dx_km), 1.0 / (ny * dy_km))
    kmax = 0.5 / max(dx_km, dy_km)
    edges = np.logspace(np.log10(kmin), np.log10(kmax), nbins + 1)
    idx = np.digitize(K.ravel(), edges) - 1
    ok = (idx >= 0) & (idx < nbins)
    counts = np.bincount(idx[ok], minlength=nbins)
    sums = np.bincount(idx[ok], weights=P.ravel()[ok], minlength=nbins)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = sums / counts
    centres = np.sqrt(edges[:-1] * edges[1:])
    return centres, mean, counts


def fit_beta(k: np.ndarray, p: np.ndarray, counts: np.ndarray, wl_min_km: float, wl_max_km: float) -> dict:
    """Least-squares slope of log P against log k for wavelengths between ``wl_min_km`` and ``wl_max_km``."""
    sel = (counts > 8) & np.isfinite(p) & (p > 0) & (k >= 1.0 / wl_max_km) & (k <= 1.0 / wl_min_km)
    if sel.sum() < 4:
        return {"beta": float("nan"), "r2": float("nan"), "n_bins": int(sel.sum())}
    x, y = np.log(k[sel]), np.log(p[sel])
    A = np.vstack([x, np.ones_like(x)]).T
    coef, res, *_ = np.linalg.lstsq(A, y, rcond=None)
    yhat = A @ coef
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {"beta": float(-coef[0]), "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"), "n_bins": int(sel.sum())}


def subset_spacing_km(lat: np.ndarray, lon: np.ndarray) -> tuple[float, float]:
    dlat = float(abs(lat[1] - lat[0]))
    dlon = float(abs(lon[1] - lon[0]))
    phi = np.deg2rad(float(lat.mean()))
    return dlon * KM_PER_DEG * np.cos(phi), dlat * KM_PER_DEG


def focal_window(z: np.ndarray, lat: np.ndarray, lon: np.ndarray, span_km: float = 460.0) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Cut a ``span_km`` square around the centroid of the land cells (z > 0); clipped to the subset."""
    dx, dy = subset_spacing_km(lat, lon)
    land = z > 0
    if not land.any():
        return z, (0, z.shape[0], 0, z.shape[1])
    ys, xs = np.nonzero(land)
    cy, cx = int(np.median(ys)), int(np.median(xs))
    hy, hx = int(round(span_km / dy / 2)), int(round(span_km / dx / 2))
    y0, y1 = max(0, cy - hy), min(z.shape[0], cy + hy)
    x0, x1 = max(0, cx - hx), min(z.shape[1], cx + hx)
    return z[y0:y1, x0:x1], (y0, y1, x0, x1)
