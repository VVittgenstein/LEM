"""Workstream D: timestep convergence test with process isolation.

Question (validation file section 9.12): GPT's runs showed about 20 m RMS elevation difference between 50 kyr and
10 kyr steps after 4 Myr; the cause is unknown. This module runs one fixed representative input (submerged-case
land region with a shelf periphery and one deep segment, one convergent belt plus regional uplift) through the
process sets below at a ladder of time steps and compares the states at the same physical time.

Process sets (each adds one process to the previous one):
  A ``uplift_spl``: uplift + stream power (multiple flow direction, G active)
  B ``plus_diffusion``: + hillslope diffusion
  C ``plus_marine``: + marine module (constant sea level)
  D ``plus_sealevel``: + a 100 kyr sinusoidal sea-level forcing of ±60 m (stand-in for the real curve)

The convergence rule used to pick the working step is an assumption recorded in the report: the largest step whose
state differs from the next finer step by at most RMS_TOL m (RMS over all cells), MAXABS_TOL m (largest cell) and
LAND_TOL (land fraction, percentage points). Nothing here is a project experimental verification of the method.
"""
from __future__ import annotations

from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('.', 'experiments'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)


import json
from datetime import datetime, timezone
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lem_pipeline.driver import Epoch, FastScapeModel, MarineParams, ProcessParams, fixed_border_mask, run_schedule

RMS_TOL_M = 5.0
MAXABS_TOL_M = 50.0
LAND_TOL_PP = 0.3

PROCESS_SETS = {
    "uplift_spl": dict(diffusion=False, marine=False, sealevel=False),
    "plus_diffusion": dict(diffusion=True, marine=False, sealevel=False),
    "plus_marine": dict(diffusion=True, marine=True, sealevel=False),
    "plus_sealevel": dict(diffusion=True, marine=True, sealevel=True),
}


def _smooth_noise(rng: np.random.Generator, shape: tuple[int, int], sigma_cells: float, std: float) -> np.ndarray:
    from scipy.ndimage import gaussian_filter
    n = rng.normal(0.0, 1.0, shape)
    s = gaussian_filter(n, sigma_cells, mode="reflect")
    s *= std / max(s.std(), 1e-12)
    return s


def build_reference_input(nx: int = 500, ny: int = 500, dx: float = 1000.0, seed: int = 20260909, deep_depth: float = 3000.0) -> dict:
    """Deterministic representative input (submerged case). Distances in km are computed from cell indices.

    ``deep_depth`` caps the floor of the deep periphery segment; the 2.8.4 marine solver aborts for floors of about
    3000 m with the Glerum diffusivities (see ``marine_diag``), so the matrix is run with a converging cap."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:ny, 0:nx].astype(float)
    cx, cy = nx / 2, ny / 2
    a, b = 130.0, 90.0  # semi-axes in km (260 × 180 km land region)
    theta = np.deg2rad(25.0)
    xr = (x - cx) * np.cos(theta) + (y - cy) * np.sin(theta)
    yr = -(x - cx) * np.sin(theta) + (y - cy) * np.cos(theta)
    ellipse = (xr / a) ** 2 + (yr / b) ** 2
    outline = _smooth_noise(rng, (ny, nx), 12.0, 0.12)
    land = ellipse + outline < 1.0
    # distance from land (km) and a deep periphery segment on the west
    from scipy.ndimage import distance_transform_edt
    dist = distance_transform_edt(~land) * (dx / 1000.0)
    ang = np.arctan2(y - cy, x - cx)
    deep = (np.cos(ang - np.pi) > 0.55) & ~land  # western sector
    W, zb, slope = 40.0, 190.0, 0.03
    shelf = -100.0 - 0.3 * dist  # gentle deepening on the shallow periphery
    prof = np.where(dist <= W, -20.0 - (zb - 20.0) * dist / W, -zb - slope * 1000.0 * (dist - W))
    prof = np.maximum(prof, -deep_depth)
    seabed = np.where(deep, prof, shelf)
    seabed += _smooth_noise(rng, (ny, nx), 3.0, 4.0)
    landsurf = 50.0 + _smooth_noise(rng, (ny, nx), 4.0, 5.0)
    h0 = np.where(land, landsurf, seabed)
    # uplift: one convergent belt (70 km wide Gaussian cross-profile) along the long axis, offset 30 km, + regional
    belt_axis = yr - 30.0
    belt = 5e-4 * np.exp(-0.5 * (belt_axis / (35.0 / 2.355)) ** 2)  # FWHM 35 km core inside a 70 km band
    belt = np.where(np.abs(belt_axis) <= 35.0, belt, 0.0)
    regional = 5e-5
    uplift = np.where(land, regional + belt, 0.0)
    ring = fixed_border_mask(1111, nx, ny)
    uplift[ring] = 0.0
    return {"h0": h0, "uplift": uplift, "land": land, "deep": deep, "ring": ring, "nx": nx, "ny": ny, "dx": dx, "seed": seed, "deep_depth": deep_depth}


def sea_level_sine(t: float, amplitude: float = 60.0, period: float = 100e3) -> float:
    return -amplitude * np.sin(2 * np.pi * t / period)


def run_case(*, label: str, process_set: str, dt: float, t_end: float, out_dir: str, nx: int = 500, ny: int = 500,
             dx: float = 1000.0, seed: int = 20260909, log_every_steps: int = 0, deep_depth: float = 3000.0,
             perturb_std: float = 0.0, perturb_seed: int = 0) -> dict:
    """One model run (job function for ``runner.run_jobs``). ``perturb_std`` adds white noise (m) to the initial
    surface (intrinsic-variability reference for the statistical convergence criterion)."""
    cfg = PROCESS_SETS[process_set]
    inp = build_reference_input(nx, ny, dx, seed, deep_depth=deep_depth)
    if perturb_std > 0:
        inp["h0"] = inp["h0"] + np.random.default_rng(perturb_seed).normal(0.0, perturb_std, inp["h0"].shape)
    marine = MarineParams() if cfg["marine"] else None
    kd = 0.01 if cfg["diffusion"] else 0.0
    model = FastScapeModel(nx=nx, ny=ny, dx=dx, dt=dt, h0=inp["h0"], kf=3e-6, kd=kd,
                           process=ProcessParams(m=0.45, n=1.0, g1=1.0, g2=1.0, p=1.0), marine=marine,
                           sea_level=0.0, precip=1.0, uplift=inp["uplift"], bc=1111, label=label)
    try:
        model.enable(diffusion=cfg["diffusion"], marine=cfg["marine"])
        sl = sea_level_sine if cfg["sealevel"] else None
        prog = Path(out_dir)
        prog.mkdir(parents=True, exist_ok=True)
        prog_file = prog / "progress.txt"  # last completed step; survives a Fortran STOP in the marine solver

        def on_step(m):
            prog_file.write_text(f"{m.step} {m.time_years:.0f}\n", encoding="utf-8")

        rec = run_schedule(model, t_end=t_end, epochs=[Epoch(0.0, t_end * 2, inp["uplift"])], sea_level_at=sl, on_step=on_step,
                           log_every_steps=log_every_steps, on_log=lambda m, w: print(f"[{label}] step {m.step} t={m.time_years/1e6:.2f} Myr {w:.0f} s", flush=True))
        h = model.h()
        out = model.export(out_dir, extra={"workstream": "D", "process_set": process_set, "loop": rec,
                                            "input": {"seed": seed, "land_cells": int(inp["land"].sum()), "deep_depth_m": deep_depth,
                                                      "perturb_std_m": perturb_std, "perturb_seed": perturb_seed}},
                           channels=("elevation", "drainage_area", "total_erosion"))
        return {"out": str(out), "steps": rec["steps"], "wall_s": rec["wall_s"], "step_mean_s": float(np.mean(model.step_times)),
                "land_fraction": model.land_fraction(h), "z_min": float(h.min()), "z_max": float(h.max()),
                "finite": bool(np.isfinite(h).all())}
    finally:
        model.close()


def run_case_worker(*, label: str, process_set: str, dt: float, t_end: float, out_dir: str, nx: int = 500, ny: int = 500,
                    dx: float = 1000.0, seed: int = 20260909, deep_depth: float = 3000.0, perturb_std: float = 0.0, perturb_seed: int = 0) -> dict:
    """Same reference case as ``run_case`` but run through the checkpointed worker with step-level recovery from the
    marine solver's abort (``worker.py``); the export mirrors ``run_case`` (elevation, drainage_area, total_erosion)."""
    from lem_pipeline import worker

    cfg = PROCESS_SETS[process_set]
    inp = build_reference_input(nx, ny, dx, seed, deep_depth=deep_depth)
    if perturb_std > 0:
        inp["h0"] = inp["h0"] + np.random.default_rng(perturb_seed).normal(0.0, perturb_std, inp["h0"].shape)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    marine = MarineParams() if cfg["marine"] else None
    kd = 0.01 if cfg["diffusion"] else 0.0
    sea_t = np.arange(0.0, t_end + worker.MIN_DT, worker.MIN_DT)
    sea_z = np.array([sea_level_sine(float(t)) if cfg["sealevel"] else 0.0 for t in sea_t])
    worker.save_inputs(out, h0=inp["h0"], kf=np.full((ny, nx), 3e-6), kd=np.full((ny, nx), kd), precip=np.ones((ny, nx)),
                       epochs=[Epoch(0.0, t_end * 2, inp["uplift"])], sea_series_t=sea_t, sea_series_z=sea_z,
                       process=ProcessParams(m=0.45, n=1.0, g1=1.0, g2=1.0, p=1.0), marine=marine, dt=dt, T=t_end, nx=nx, ny=ny, dx_m=dx)
    rec = worker.orchestrate(out, log=lambda m: print(m, flush=True))
    if not rec.get("done"):
        (out / "run-failed.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        return {"out": str(out), "done": False, "error": rec.get("error"), "restarts": rec.get("restarts"), "t": rec.get("t")}
    h = np.load(out / "final_h.npy")
    sea_final = float(sea_z[-1] if t_end >= sea_t[-1] else np.interp(t_end, sea_t, sea_z))
    np.save(out / "elevation.npy", h)
    np.save(out / "drainage_area.npy", np.load(out / "final_area.npy").astype(np.float32))
    np.save(out / "total_erosion.npy", np.load(out / "final_etot.npy").astype(np.float32))
    meta = {"written_utc": datetime.now(timezone.utc).isoformat(),
            "settings": {"label": label, "nx": nx, "ny": ny, "dx_m": dx, "dt_yr": dt, "bc": 1111, "sea_level_final_m": sea_final,
                         "library": "fastscapelib-fortran 2.8.4; checkpointed worker with step-level recovery"},
            "steps": rec.get("steps"), "time_yr": rec.get("t"), "grid": {"nx": nx, "ny": ny, "dx_m": dx, "dy_m": dx},
            "timing": {"steps_total_s": rec.get("wall_s"), "step_mean_s": rec.get("step_mean_s")},
            "output": {"z_min": float(h.min()), "z_max": float(h.max()), "land_fraction": float((h > sea_final).mean()), "finite": bool(np.isfinite(h).all())},
            "workstream": "D", "process_set": process_set, "loop": rec,
            "input": {"seed": seed, "land_cells": int(inp["land"].sum()), "deep_depth_m": deep_depth, "perturb_std_m": perturb_std, "perturb_seed": perturb_seed}}
    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    for name in ("final_h", "final_area", "final_b", "final_etot", "final_f", "ckpt_h", "ckpt_f", "ckpt_b", "ckpt_etot"):
        if (out / f"{name}.npy").exists():
            (out / f"{name}.npy").unlink()
    return {"out": str(out), "done": True, "steps": rec["steps"], "wall_s": rec["wall_s"], "step_mean_s": rec.get("step_mean_s"),
            "restarts": rec.get("restarts", 0), "sub_steps_total": rec.get("sub_steps_total", 0), "land_fraction": float((h > sea_final).mean())}


def make_jobs(root: Path, *, t_end: float, dts: dict[str, list[float]], nx: int = 500, ny: int = 500, deep_depth: float = 3000.0) -> list[dict]:
    jobs = []
    for pset, ladder in dts.items():
        for dt in ladder:
            label = f"{pset}_dt{int(dt)}"
            jobs.append(dict(label=label, process_set=pset, dt=float(dt), t_end=float(t_end),
                             out_dir=str(root / pset / f"dt{int(dt)}"), nx=nx, ny=ny, deep_depth=deep_depth))
    return jobs


def analyze(root: Path) -> dict:
    """Compare each step against the next finer step and against the finest step of its process set."""
    summary = {"rms_tol_m": RMS_TOL_M, "maxabs_tol_m": MAXABS_TOL_M, "land_tol_pp": LAND_TOL_PP, "sets": {}}
    for pset_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        runs = {}
        for d in sorted(pset_dir.iterdir()):
            meta_p = d / "meta.json"
            if not meta_p.exists():
                continue
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            runs[float(meta["settings"]["dt_yr"])] = {"dir": d, "meta": meta, "h": np.load(d / "elevation.npy")}
        if len(runs) < 2:
            continue
        dts = sorted(runs, reverse=True)  # coarse → fine
        finest = dts[-1]
        rows = []
        for i, dt in enumerate(dts):
            h = runs[dt]["h"]
            row = {"dt_yr": dt, "steps": runs[dt]["meta"]["steps"], "wall_s": runs[dt]["meta"]["timing"]["steps_total_s"],
                   "step_mean_s": runs[dt]["meta"]["timing"]["step_mean_s"], "land_fraction": runs[dt]["meta"]["output"]["land_fraction"],
                   "z_max": runs[dt]["meta"]["output"]["z_max"]}
            for tag, ref_dt in (("vs_next_finer", dts[i + 1] if i + 1 < len(dts) else None), ("vs_finest", finest if dt != finest else None)):
                if ref_dt is None:
                    continue
                hr = runs[ref_dt]["h"]
                diff = h - hr
                land_h, land_r = h > 0, hr > 0
                row[f"{tag}_dt"] = ref_dt
                row[f"{tag}_rms_m"] = float(np.sqrt(np.mean(diff ** 2)))
                row[f"{tag}_maxabs_m"] = float(np.abs(diff).max())
                row[f"{tag}_land_diff_pp"] = float(100 * (land_h.mean() - land_r.mean()))
                row[f"{tag}_class_changed_cells"] = int((land_h != land_r).sum())
                row[f"{tag}_rms_land_m"] = float(np.sqrt(np.mean(diff[land_r] ** 2))) if land_r.any() else None
                row[f"{tag}_rms_sea_m"] = float(np.sqrt(np.mean(diff[~land_r] ** 2))) if (~land_r).any() else None
                row[f"{tag}_cells_over_10m"] = int((np.abs(diff) > 10).sum())
                # statistical comparison: land hypsometry and slope distributions (cell-wise chaos vs statistical convergence)
                qs = [0.05, 0.25, 0.5, 0.75, 0.95]
                hl, hrl = h[land_h], hr[land_r]
                if hl.size and hrl.size:
                    row[f"{tag}_hypsometry_quantile_diff_m"] = [float(a - b) for a, b in zip(np.quantile(hl, qs), np.quantile(hrl, qs))]
                    gy, gx = np.gradient(h, 1000.0)
                    gyr, gxr = np.gradient(hr, 1000.0)
                    sl, slr = np.hypot(gx, gy)[land_h], np.hypot(gxr, gyr)[land_r]
                    row[f"{tag}_slope_quantile_ratio"] = [float(a / b) if b > 0 else None for a, b in zip(np.quantile(sl, qs), np.quantile(slr, qs))]
                    row[f"{tag}_land_relief_p95_m"] = [float(np.quantile(hl, 0.95) - np.quantile(hl, 0.05)), float(np.quantile(hrl, 0.95) - np.quantile(hrl, 0.05))]
            rows.append(row)
        passing = [r["dt_yr"] for r in rows if "vs_next_finer_rms_m" in r and r["vs_next_finer_rms_m"] <= RMS_TOL_M
                   and r["vs_next_finer_maxabs_m"] <= MAXABS_TOL_M and abs(r["vs_next_finer_land_diff_pp"]) <= LAND_TOL_PP]
        summary["sets"][pset_dir.name] = {"rows": rows, "largest_passing_dt_yr": max(passing) if passing else None}
    (root / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    return summary


def summary_markdown(summary: dict) -> str:
    lines = ["| 过程集 | dt (kyr) | 步数 | 单步 s | 陆地比例 | 与下一细步长 RMS (m) | 最大差 (m) | 陆地比例差 (pp) | 与最细步长 RMS (m) |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for pset, s in summary["sets"].items():
        for r in s["rows"]:
            g = lambda k: (f"{r[k]:.2f}" if isinstance(r.get(k), (int, float)) else "")
            lines.append(f"| {pset} | {r['dt_yr']/1e3:g} | {r['steps']} | {r['step_mean_s']:.3f} | {r['land_fraction']:.4f} | {g('vs_next_finer_rms_m')} | {g('vs_next_finer_maxabs_m')} | {g('vs_next_finer_land_diff_pp')} | {g('vs_finest_rms_m')} |")
        lines.append(f"| {pset} | 通过判据的最大步长 | {s['largest_passing_dt_yr']} | | | | | | |")
    return "\n".join(lines)
