"""One sample end to end: draw the configuration, build the Fastscape inputs, run to T, check, export.

Order of the sampling steps (``architecture-dataflow.md`` 4.1.5):
1. T uniform in 5 to 30 Myr (assumption from archive message 150 and rule P-7).
2. Land region: shape-first generator with calibrated spectral parameters; occupancy outside the preference band
   discards the draw (up to ``max_shape_tries`` redraws, all recorded).
3. Periphery bathymetry (segments, profiles, roughness) with the marine solver's depth cap.
4. Case: submerged (land plain above sea level) or emergence (platform below sea level lifted by the regional dome),
   drawn 50/50 (assumption; yZz decided both mappings are tried and compared at run time).
5. Sea level schedule, activities and epochs, K/D/precipitation and marine parameters.
6. Run with the marine module, multiple flow direction and G; export the T-time state in the viewer format together
   with the configuration, the evidence labels and the milestone-1 check result.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import activities as act
from . import worker
from .checks import CheckConfig, evaluate
from .distributions import QuantileTable, sample_range
from .driver import Epoch, FastScapeModel, fixed_border_mask, run_schedule
from .landmask import LandmaskParams, generate_shape_first, mask_metrics, power_law_field
from .parameters import sample_parameters
from .paths import POP34_PACKAGE, ROOT
from .periphery import PeripheryTables, build_bathymetry, trace_outline
from .sealevel import SeaLevelSchedule

ASSUMPTION = "尚待验证的假设"
CALC = "本项目借鉴或合成改造"
MARINE_MAX_DEPTH_M = 1500.0  # 2.8.4 marine solver aborts for deeper floors with the Glerum diffusivities (marine_diag, 2026-09-09)
SINK_BAND_M = 4000.0  # depth of the outer ocean band used as a sediment sink (assumption, sink_test 2026-09-09); None disables
SINK_RAMP_KM = 0.0  # linear ramp inward of the band from the sink depth to the sampled floor (0 = none; assumption under test)
DEFAULT_CALIBRATION = ROOT / "docs" / "work" / "2026-09-09-pipeline" / "landmask-calibration.json"


def _load_calibration(path: Path | None) -> dict:
    p = path or DEFAULT_CALIBRATION
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        return {"beta": d["best"]["beta"], "amp": d["best"]["amp"], "source": str(p), "evidence_state": CALC}
    return {"beta": 3.5, "amp": 0.25, "source": "default (uncalibrated)", "evidence_state": ASSUMPTION}


def _reference_pca(rng: np.random.Generator) -> float:
    import csv
    with open(POP34_PACKAGE / "class4-shape-statistics-pop34.csv", encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["statistic"] == "pca_ratio" and r["subset"] == "all"]
    return float(np.clip(QuantileTable.from_row(rows[0], "pca").sample(rng), 1.05, 4.0))


def _land_plain_height(rng: np.random.Generator) -> float:
    """Low plain height (m) for the submerged case: drawn from the reference landmasses' low quantiles (A15, pop34)."""
    import csv
    with open(POP34_PACKAGE / "class1-depth-roughness-land-pop34.csv", encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["group"] == "land_elevation" and r["statistic"] in ("landmass_p05", "landmass_p25")]
    tab = QuantileTable.from_row(rows[int(rng.integers(len(rows)))], "land low quantile")
    return float(np.clip(tab.sample(rng), 5.0, 300.0))


def draw_config(seed: int, *, T: float | None = None, dt: float = 10e3, nx: int = 500, ny: int = 500, dx_km: float = 1.0,
                occupancy_band=(0.50, 0.60), ocean_band_km: float = 10.0, max_shape_tries: int = 30,
                calibration: Path | None = None, case: str | None = None) -> dict:
    rng = np.random.default_rng(seed)
    T = float(T) if T is not None else float(sample_range(rng, 5e6, 30e6, force="uniform"))
    cal = _load_calibration(calibration)
    tries = []
    land = None
    for k in range(max_shape_tries):
        p = LandmaskParams(nx=nx, ny=ny, dx_km=dx_km, axis_ratio=_reference_pca(rng), orientation_deg=float(rng.uniform(0, 180)),
                           beta=cal["beta"], noise_amplitude=cal["amp"], ocean_band_km=ocean_band_km, seed=int(rng.integers(1 << 30)))
        cand, info = generate_shape_first(p)
        occ = info["occupancy_achieved"]
        tries.append({"try": k, "occupancy": occ, "fill": info["fill_achieved"], "axis_ratio": p.axis_ratio})
        if occupancy_band[0] <= occ <= occupancy_band[1]:
            land, land_info = cand, info
            break
    if land is None:
        return {"seed": seed, "discarded": True, "reason": f"no shape reached the occupancy band in {max_shape_tries} tries", "shape_tries": tries, "T_yr": T}
    case = case or ("submerged" if rng.random() < 0.5 else "emergence")
    cfg = {"seed": seed, "T_yr": T, "dt_yr": dt, "nx": nx, "ny": ny, "dx_km": dx_km, "case": case, "occupancy_band": list(occupancy_band),
           "ocean_band_km": ocean_band_km, "landmask": land_info, "landmask_calibration": cal, "shape_tries": tries,
           "land_metrics": mask_metrics(land, dx_km), "marine_max_depth_m": MARINE_MAX_DEPTH_M,
           "evidence": {"T": ("5 to 30 Myr uniform; archive message 150 + rule P-7", ASSUMPTION), "case": ("submerged/emergence 50/50", ASSUMPTION),
                        "marine_max_depth": ("2.8.4 marine solver limit found 2026-09-09", "工具限制，本项目假设")}}
    return cfg, land, rng


def build_inputs(cfg: dict, land: np.ndarray, rng: np.random.Generator, tables: PeripheryTables | None = None,
                 overrides: dict | None = None) -> dict:
    """``overrides`` (diagnostics only): depth_cap, k_uniform, k_mult_cap, kds (pair), precip (scalar), no_roughness, slope_cap."""
    ov = overrides or {}
    ny, nx, dx_km, T = cfg["ny"], cfg["nx"], cfg["dx_km"], cfg["T_yr"]
    tables = tables or PeripheryTables()
    depth, pinfo = build_bathymetry(land, rng, tables, dx_km, roughness=not ov.get("no_roughness", False))
    cap = float(ov.get("depth_cap", MARINE_MAX_DEPTH_M))
    depth = np.where(np.isnan(depth), np.nan, np.maximum(depth, -cap))
    # land surface
    land_rough = power_law_field(rng, ny, nx, 3.5, dx_km, 2.0) * 5.0  # 5 m std on the plain (assumption)
    if cfg["case"] == "submerged":
        plain = _land_plain_height(rng)
        landsurf = plain + land_rough
        platform_depth = 0.0
    else:
        platform_depth = float(sample_range(rng, 20.0, 100.0, force="uniform"))
        landsurf = -platform_depth + land_rough
        depth = depth - platform_depth  # periphery profile starts at the platform depth so the surface is continuous at the outline (assumption)
    h0 = np.where(land, landsurf, depth)
    h0 = np.where(np.isnan(h0), -100.0, h0)
    ring = fixed_border_mask(1111, nx, ny)
    h0[ring] = np.minimum(h0[ring], -MARINE_MAX_DEPTH_M * 0 - 150.0)  # borders at least 150 m below the initial sea level (assumption)
    sink = ov.get("sink_band_m", SINK_BAND_M)
    if sink is not None:
        # The outer ocean band (the yZz "always ocean" band of the milestone-1 rule) is made a sediment sink of depth
        # SINK_BAND_M: the 2.8.4 marine module fills every reachable ocean cell up to the shelf surface and the
        # boundaries are closed, so without a sink the sediment produced over T fills the narrow ocean rim and the
        # band becomes land at sea-level lowstands (2026-09-09 scan: 12 of 16 samples at 2 Myr). The band stands for
        # the open ocean beyond the sampled periphery; its depth is an assumption tested on 5 seeds (sink_test).
        band = int(round(cfg["ocean_band_km"] / dx_km))
        yy, xx = np.mgrid[0:ny, 0:nx]
        d_border = np.minimum(np.minimum(yy, ny - 1 - yy), np.minimum(xx, nx - 1 - xx)) + 1  # cells from the border (1 at the border)
        bm = d_border <= band
        h0[bm] = np.minimum(h0[bm], -float(sink))
        ramp_km = float(ov.get("sink_ramp_km", SINK_RAMP_KM) or 0.0)
        if ramp_km > 0:
            # linear ramp from the sink depth at the band edge to the sampled sea floor ``ramp_km`` further inward (only deepening)
            ramp = int(round(ramp_km / dx_km))
            rm = (d_border > band) & (d_border <= band + ramp) & ~land
            frac = (d_border[rm] - band) / float(ramp)
            target = -float(sink) + (h0[rm] + float(sink)) * frac
            h0[rm] = np.minimum(h0[rm], target)
        cfg["sink_band"] = {"depth_m": float(sink), "width_km": cfg["ocean_band_km"], "ramp_km": ramp_km,
                            "evidence": ("closed-domain sediment budget of the tool; depth and ramp tested on 5 seeds", ASSUMPTION)}
    contour = trace_outline(land)
    margins = act.OutlineMargins.sample(rng, contour, dx_km)
    activities = act.sample_activities(rng, land, contour, margins, T=T, dx_km=dx_km, ocean_band_km=cfg["ocean_band_km"],
                                       emergence=(cfg["case"] == "emergence"), platform_depth_m=platform_depth)
    epochs = act.build_epochs(activities, T)
    sea = SeaLevelSchedule.sample(rng, T)
    kf, kd, precip, process, marine, prec = sample_parameters(rng, land, dx_km)
    if ov.get("k_uniform"):
        kf = np.full_like(kf, prec.k_hard)
    if ov.get("k_mult_cap") is not None:
        kf = np.minimum(kf, prec.k_hard * float(ov["k_mult_cap"]))
    if ov.get("kds") is not None:
        marine.kds1, marine.kds2 = float(ov["kds"][0]), float(ov["kds"][1])
    if ov.get("kds_equal"):
        marine.kds2 = marine.kds1  # mechanism test: equal silt and sand diffusivities (the sampled silt value for both)
    if ov.get("precip") is not None:
        precip = np.full_like(precip, float(ov["precip"]))
    if ov.get("sea_level_fixed") is not None:
        class _FixedSeaLevel:  # diagnostics only: constant sea level, the schedule draw above keeps the rng sequence unchanged
            def __init__(self, v: float) -> None:
                self.v = float(v)

            def __call__(self, t: float) -> float:
                return self.v

            def describe(self) -> dict:
                return {"fixed_m": self.v, "evidence_state": "诊断用固定海平面"}
        sea = _FixedSeaLevel(ov["sea_level_fixed"])
    cfg["overrides"] = ov
    cfg["periphery"] = {"regime": pinfo.regime, "deep_share": pinfo.deep_share, "perimeter_km": pinfo.perimeter_km, "n_segments": len(pinfo.segments),
                        "evidence": pinfo.evidence}
    cfg["land_surface"] = {"plain_height_m": None if cfg["case"] == "emergence" else float(landsurf[land].mean()), "platform_depth_m": platform_depth,
                           "roughness_std_m": 5.0, "evidence": ("A15 low quantiles (pop34); roughness 5 m", ASSUMPTION)}
    cfg["margins"] = {"active_share": float(np.mean(margins.label == "active")), "evidence": ("F 100 km labels, unclassified by classified share", ASSUMPTION)}
    cfg["activities"] = act.describe(activities)
    cfg["epochs"] = [{"t_start": e.t_start, "t_end": e.t_end, "u_max": float(e.uplift.max()), "u_min": float(e.uplift.min())} for e in epochs]
    cfg["sea_level"] = sea.describe()
    cfg["parameters"] = asdict(prec)
    cfg["process"] = asdict(process)
    cfg["marine"] = asdict(marine)
    cfg["initial"] = {"h0_min": float(h0.min()), "h0_max": float(h0.max()), "land_fraction_t0": float((h0 > 0).mean())}
    return {"h0": h0, "kf": kf, "kd": kd, "precip": precip, "process": process, "marine": marine, "epochs": epochs, "sea": sea, "land": land}


def run_sample(*, seed: int, out_dir: str, T: float | None = None, dt: float = 10e3, nx: int = 500, ny: int = 500,
               occupancy_band=(0.50, 0.60), calibration: str | None = None, case: str | None = None, label: str = "",
               log_every_steps: int = 200, overrides: dict | None = None, max_steps: int | None = None) -> dict:
    """Job function: build, run to T, check and export one sample. ``max_steps`` truncates the run (diagnostics)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    drawn = draw_config(seed, T=T, dt=dt, nx=nx, ny=ny, occupancy_band=tuple(occupancy_band),
                        calibration=Path(calibration) if calibration else None, case=case)
    if isinstance(drawn, dict) and drawn.get("discarded"):
        (out / "config.json").write_text(json.dumps(drawn, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        return {"seed": seed, "accepted": False, "stage": "shape", "reason": drawn["reason"], "wall_s": time.perf_counter() - t0}
    cfg, land, rng = drawn
    inputs = build_inputs(cfg, land, rng, overrides=overrides)
    if max_steps is not None:
        cfg["T_yr"] = float(max_steps) * dt
    cfg["timing"] = {"inputs_s": time.perf_counter() - t0}
    (out / "config.json").write_text(json.dumps(cfg, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    np.save(out / "initial_elevation.npy", inputs["h0"].astype(np.float32))
    # time loop in a checkpointed child process with step-level recovery from the marine solver's abort (worker.py)
    T = float(cfg["T_yr"])
    sea_t = np.arange(0.0, T + worker.MIN_DT, worker.MIN_DT)
    sea_z = np.array([float(inputs["sea"](float(tt))) for tt in sea_t])
    worker.save_inputs(out, h0=inputs["h0"], kf=inputs["kf"], kd=inputs["kd"], precip=inputs["precip"], epochs=inputs["epochs"], sea_series_t=sea_t,
                       sea_series_z=sea_z, process=inputs["process"], marine=inputs["marine"], dt=dt, T=T, nx=nx, ny=ny, dx_m=cfg["dx_km"] * 1000.0)
    rec = worker.orchestrate(out, log=lambda m: print(m, flush=True))
    if not rec.get("done"):
        (out / "run-failed.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        return {"seed": seed, "accepted": False, "stage": "run", "reason": rec.get("error"), "restarts": rec.get("restarts"), "restart_log": rec.get("restart_log"),
                "t_reached": rec.get("t"), "wall_s": time.perf_counter() - t0, "T_yr": T, "case": cfg["case"], "dt_yr": dt}
    h = np.load(out / "final_h.npy")
    area = np.load(out / "final_area.npy")
    sea_final = float(sea_z[-1] if T >= sea_t[-1] else np.interp(T, sea_t, sea_z))
    check = evaluate(h, CheckConfig(sea_level_m=sea_final, dx_km=cfg["dx_km"], ocean_band_km=cfg["ocean_band_km"], occupancy_band=tuple(occupancy_band)))
    # implicit stream-power step number K A^m dt / dx on the final drainage network (diagnostic fact of the run)
    spl_number = float(np.nanmax(inputs["kf"] * np.power(np.maximum(area, 0.0), inputs["process"].m)) * dt / (cfg["dx_km"] * 1000.0))
    check["spl_number_max"] = spl_number
    _export_arrays(out, cfg, h=h, area=area, basement=np.load(out / "final_b.npy"), etot=np.load(out / "final_etot.npy"),
                   silt=np.load(out / "final_f.npy") if inputs["marine"] is not None else None, sea_final=sea_final, rec=rec,
                   extra={"sample": {"seed": seed, "T_yr": T, "case": cfg["case"], "dt_yr": dt}, "loop": rec, "check": check})
    (out / "check.json").write_text(json.dumps(check, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    for name in ("final_h", "final_area", "final_b", "final_etot", "final_f", "ckpt_h", "ckpt_f", "ckpt_b", "ckpt_etot"):
        p = out / f"{name}.npy"
        if p.exists():
            p.unlink()
    return {"seed": seed, "accepted": bool(check["accepted"]), "reasons": check["reasons"], "stage": "T", "land_fraction": check["land_fraction"],
            "steps": rec["steps"], "wall_s": time.perf_counter() - t0, "step_mean_s": rec.get("step_mean_s"), "T_yr": T, "case": cfg["case"],
            "dt_yr": dt, "spl_number_max": spl_number, "restarts": rec.get("restarts", 0), "sub_steps_total": rec.get("sub_steps_total", 0),
            "restart_log": rec.get("restart_log", [])}


def _export_arrays(out: Path, cfg: dict, *, h, area, basement, etot, silt, sea_final: float, rec: dict, extra: dict) -> None:
    """Viewer-format export (same files and meta.json layout as ``driver.FastScapeModel.export``) from the worker's arrays."""
    arrays = {"elevation": h, "drainage_area": area, "basement": basement, "total_erosion": etot}
    channels = {"elevation": {"file": "elevation.npy", "units": "m", "kind": "elevation"},
                "drainage_area": {"file": "drainage_area.npy", "units": "m2", "kind": "drainage_area", "display": "log10"},
                "basement": {"file": "basement.npy", "units": "m", "kind": "elevation", "note": "tracked outside FastScape across restarts (worker.py)"},
                "total_erosion": {"file": "total_erosion.npy", "units": "m", "kind": "scalar", "note": "tracked outside FastScape across restarts (worker.py)"}}
    if silt is not None:
        arrays["silt_fraction"] = silt
        channels["silt_fraction"] = {"file": "silt_fraction.npy", "units": "1", "kind": "scalar"}
    for name, arr in arrays.items():
        np.save(out / f"{name}.npy", np.asarray(arr, dtype=np.float32) if name != "elevation" else np.asarray(arr, dtype=np.float64))
    meta = {"written_utc": datetime.now(timezone.utc).isoformat(),
            "settings": {"label": f"sample{cfg['seed']}", "nx": cfg["nx"], "ny": cfg["ny"], "dx_m": cfg["dx_km"] * 1000.0, "dt_yr": cfg["dt_yr"], "bc": 1111,
                         "process": cfg["process"], "marine": cfg["marine"], "sea_level_final_m": sea_final,
                         "library": "fastscapelib-fortran 2.8.4 (FastScape API via Python, lem-env); checkpointed worker with step-level recovery"},
            "steps": rec.get("steps"), "time_yr": rec.get("t"), "channels": channels,
            "grid": {"nx": cfg["nx"], "ny": cfg["ny"], "dx_m": cfg["dx_km"] * 1000.0, "dy_m": cfg["dx_km"] * 1000.0},
            "timing": {"steps_total_s": rec.get("wall_s"), "step_mean_s": rec.get("step_mean_s")},
            "output": {"z_min": float(np.min(h)), "z_max": float(np.max(h)), "z_mean": float(np.mean(h)), "land_fraction": float(np.mean(h > sea_final)),
                       "finite": bool(np.isfinite(h).all())}}
    meta.update(extra)
    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
