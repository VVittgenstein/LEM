"""Shared seeds, local means, envelope scaling and exact-count thresholds."""
import numpy as np
from scipy import ndimage as ndi

from .config import BAND, COEFFICIENTS, SIZE, WINDOWS, SharedSample

# Role numbers are a stable part of the replay contract.
ROLES = {"fraction": 11, "pose": 12, "ellipse_residual": 13,
         "noise_1": 101, "noise_5": 105, "noise_25": 125}


def rng_for(seed: int, role: str) -> np.random.Generator:
    if seed < 0:
        raise ValueError("seed must be non-negative")
    seq = np.random.SeedSequence([int(seed), ROLES[role]])
    return np.random.Generator(np.random.PCG64(seq))


def random_fields(seed: int, size: int = SIZE) -> dict[int, np.ndarray]:
    fields = {}
    pad = max(WINDOWS) // 2
    for window in WINDOWS:
        base = rng_for(seed, f"noise_{window}").standard_normal((size + 2 * pad, size + 2 * pad))
        averaged = ndi.uniform_filter(base, size=window, mode="constant", cval=0.0)
        result = averaged[pad:pad + size, pad:pad + size].copy()
        result -= result.mean()
        std = result.std(ddof=0)
        if not np.isfinite(std) or std <= 0:
            raise ValueError("degenerate random field")
        result /= std
        fields[window] = result
    return fields


def shared_sample(seed: int, target_fraction: float | None = None) -> SharedSample:
    fraction = float(rng_for(seed, "fraction").uniform(0.50, 0.60)) if target_fraction is None else float(target_fraction)
    if not np.isfinite(fraction) or not 0.50 <= fraction <= 0.60:
        raise ValueError("target_fraction must be between 0.50 and 0.60")
    pose = rng_for(seed, "pose")
    angle = float(pose.uniform(0.0, 360.0))
    cx, cy = 250.0 + pose.uniform(-25.0, 25.0, size=2)
    return SharedSample(int(seed), fraction, angle, float(cx), float(cy), random_fields(seed),
                        {"bit_generator": "PCG64", "seed_sequence": "[seed, role_id]", "roles": ROLES})


def normalize_envelope(values: np.ndarray) -> tuple[np.ndarray, dict]:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError("envelope must be a finite 2D array")
    lo, hi = float(values.min()), float(values.max())
    if hi <= lo:
        raise ValueError("constant envelope cannot be normalized")
    return (values - lo) / (hi - lo), {"raw_min": lo, "raw_max": hi, "transform": "(raw-min)/(max-min)"}


def allowed_region(shape=(SIZE, SIZE), band: int = BAND) -> np.ndarray:
    if band < 0 or 2 * band >= min(shape):
        raise ValueError("invalid ocean band")
    allowed = np.ones(shape, dtype=bool)
    if band:
        allowed[:band] = allowed[-band:] = False
        allowed[:, :band] = allowed[:, -band:] = False
    return allowed


def exact_mask(values: np.ndarray, count: int, band: int = BAND) -> tuple[np.ndarray, dict]:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError("combined field must be finite and two-dimensional")
    allowed = allowed_region(values.shape, band)
    ids = np.flatnonzero(allowed)
    if count <= 0 or count > len(ids):
        raise ValueError("requested cell count exceeds the allowed region")
    scores = values.ravel()[ids]
    threshold = float(np.partition(scores, len(scores) - count)[len(scores) - count])
    above = scores > threshold
    chosen = ids[above]
    ties = ids[scores == threshold]
    tie_needed = count - len(chosen)
    mask = np.zeros(values.shape, dtype=bool)
    mask.ravel()[chosen] = True
    mask.ravel()[ties[:tie_needed]] = True
    return mask, {"value": threshold, "target_cells": int(count), "actual_cells": int(mask.sum()),
                  "equal_value_candidates": int(len(ties)), "equal_value_selected": int(tie_needed),
                  "tie_rule": "ascending row-major flat index", "ocean_band_cells": band}


def combine(envelope: np.ndarray, shared: SharedSample, gain: float = 1.0) -> tuple[np.ndarray, np.ndarray, dict]:
    if not np.isfinite(gain) or gain < 0:
        raise ValueError("noise gain must be finite and non-negative")
    result = np.array(envelope, dtype=np.float64, copy=True)
    for window, coefficient in zip(WINDOWS, COEFFICIENTS):
        result += gain * coefficient * shared.fields[window]
    mask, threshold = exact_mask(result, round(shared.target_fraction * SIZE * SIZE))
    return result, mask, threshold


def local_coordinates(shared: SharedSample) -> tuple[np.ndarray, np.ndarray]:
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float64) + 0.5
    x -= shared.center_x_km
    y -= shared.center_y_km
    theta = np.deg2rad(shared.angle_deg)
    return x * np.cos(theta) + y * np.sin(theta), -x * np.sin(theta) + y * np.cos(theta)

