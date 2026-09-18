"""Statistical time-step criterion for the timestep test (workflow D).

Cell-wise differences between runs with different time steps do not decrease with refinement for the stream-power
sets (drainage reorganisation is sensitively dependent on the step), so the step is judged on landscape statistics:
land fraction, land elevation quantiles (p05 to p95), land slope quantiles, land relief (p95 minus p05), maximum
elevation and the ocean-cell elevation quantiles. The noise floor of every statistic is the largest difference between
the finest-step run and the finest-step runs whose initial surface was perturbed by 1 cm white noise (intrinsic
variability). A coarser step passes when each statistic differs from the finest run by at most
``max(NOISE_FACTOR × noise floor, absolute floor)``. The factor and the absolute floors are assumptions of this project.
"""
from __future__ import annotations

from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('.', 'experiments'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)


import numpy as np

QS = (0.05, 0.25, 0.5, 0.75, 0.95)
NOISE_FACTOR = 2.0
# absolute floors (assumptions): differences below these are treated as immaterial for the pipeline's purpose
ABS_FLOOR = {"land_fraction_pp": 0.5, "land_elev_q_m": 5.0, "land_slope_q_rel": 0.10, "land_relief_m": 10.0, "z_max_m": 20.0, "ocean_elev_q_m": 5.0}


def landscape_stats(h: np.ndarray, sea_level: float = 0.0, dx_m: float = 1000.0) -> dict:
    h = np.asarray(h, dtype=float)
    land = h > sea_level
    gy, gx = np.gradient(h, dx_m)
    slope = np.hypot(gx, gy)
    out = {"land_fraction": float(land.mean()), "z_max": float(h.max())}
    if land.any():
        hl = h[land]
        out["land_elev_q"] = [float(v) for v in np.quantile(hl, QS)]
        out["land_slope_q"] = [float(v) for v in np.quantile(slope[land], QS)]
        out["land_relief"] = float(np.quantile(hl, 0.95) - np.quantile(hl, 0.05))
    if (~land).any():
        out["ocean_elev_q"] = [float(v) for v in np.quantile(h[~land], QS)]
    return out


def stat_differences(a: dict, b: dict) -> dict:
    """Absolute differences (a minus b) per statistic family; slopes as relative differences."""
    d = {"land_fraction_pp": abs(100.0 * (a["land_fraction"] - b["land_fraction"])), "z_max_m": abs(a["z_max"] - b["z_max"])}
    if "land_elev_q" in a and "land_elev_q" in b:
        d["land_elev_q_m"] = max(abs(x - y) for x, y in zip(a["land_elev_q"], b["land_elev_q"]))
        d["land_slope_q_rel"] = max(abs(x - y) / y if y > 0 else 0.0 for x, y in zip(a["land_slope_q"], b["land_slope_q"]))
        d["land_relief_m"] = abs(a["land_relief"] - b["land_relief"])
    if "ocean_elev_q" in a and "ocean_elev_q" in b:
        d["ocean_elev_q_m"] = max(abs(x - y) for x, y in zip(a["ocean_elev_q"], b["ocean_elev_q"]))
    return d


def noise_floor(finest: dict, perturbed: list[dict]) -> dict:
    floors: dict[str, float] = {}
    for p in perturbed:
        for k, v in stat_differences(p, finest).items():
            floors[k] = max(floors.get(k, 0.0), v)
    return floors


def judge(diff: dict, floors: dict, factor: float = NOISE_FACTOR, abs_floor: dict = ABS_FLOOR) -> tuple[bool, dict]:
    detail = {}
    ok = True
    for k, v in diff.items():
        tol = max(factor * floors.get(k, 0.0), abs_floor.get(k, 0.0))
        detail[k] = {"diff": v, "tolerance": tol, "pass": bool(v <= tol)}
        ok = ok and v <= tol
    return ok, detail
