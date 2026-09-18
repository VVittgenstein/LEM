"""Diagnostics for the marine module's convergence failure ("Multi-lithology diffusion not converging").

Each variant changes one aspect of the workstream-D reference input and runs a few steps; the runner records which
variants abort. Results feed the workstream-D report (cause analysis, not a verification).
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

from lem_pipeline.driver import Epoch, FastScapeModel, MarineParams, ProcessParams, run_schedule
from tests.experiments.lem_pipeline.experiments.timestep_test import build_reference_input

VARIANTS = {
    "baseline": {},
    "no_deep_segment": {"deep": False},
    "kds_120_40": {"kds": (120.0, 40.0)},
    "kds_30_10": {"kds": (30.0, 10.0)},
    "no_roughness": {"rough": False},
    "deep_1500": {"deep_depth": 1500.0},
    "deep_600": {"deep_depth": 600.0},
    "G_zero": {"G": 0.0},
    "single_flow": {"p": -2.0},
    "ratio_1": {"ratio": 1.0},
    "layer_100": {"layer": 100.0},
    "grid_250": {"nx": 250, "ny": 250},
    "no_uplift": {"uplift": False},
    "flat_shelf_200": {"deep": False, "flat": -200.0},
}


def run_variant(*, label: str, variant: str = "baseline", dt: float = 10e3, steps: int = 5, nx: int = 500, ny: int = 500,
                out_dir: str = "", overrides: dict | None = None) -> dict:
    v = dict(VARIANTS[variant])
    v.update(overrides or {})
    nx, ny = v.get("nx", nx), v.get("ny", ny)
    inp = build_reference_input(nx, ny, 1000.0, deep_depth=v.get("deep_depth", 3000.0))
    h0 = inp["h0"].copy()
    if v.get("deep") is False:
        h0 = np.where(inp["land"], h0, np.minimum(h0, -20.0))
        h0 = np.where(~inp["land"], -100.0 - 0.3 * 0 + (h0 - h0) - 100.0, h0)  # uniform -100 m (roughness dropped)
        if "flat" in v:
            h0 = np.where(~inp["land"], v["flat"], h0)
    if v.get("rough") is False:
        rng = np.random.default_rng(1)
        inp2 = build_reference_input(nx, ny, 1000.0, seed=inp["seed"])
        h0 = np.where(inp["land"], 50.0, np.minimum(np.round(h0 / 50.0) * 50.0, -20.0))
    kds1, kds2 = v.get("kds", (300.0, 100.0))
    marine = MarineParams(kds1=kds1, kds2=kds2, ratio=v.get("ratio", 0.5), layer=v.get("layer", 1000.0))
    uplift = inp["uplift"] if v.get("uplift", True) else np.zeros_like(inp["uplift"])
    model = FastScapeModel(nx=nx, ny=ny, dx=1000.0, dt=dt, h0=h0, kf=3e-6, kd=0.01,
                           process=ProcessParams(m=0.45, n=1.0, g1=v.get("G", 1.0), g2=v.get("G", 1.0), p=v.get("p", 1.0)),
                           marine=marine, sea_level=0.0, precip=1.0, uplift=uplift, bc=1111, label=label)
    try:
        done = []
        for k in range(steps):
            model.advance(1)
            h = model.h()
            done.append({"step": k + 1, "z_min": float(h.min()), "z_max": float(h.max()), "land": model.land_fraction(h)})
            print(f"[{label}] step {k+1} ok z {h.min():.0f}..{h.max():.0f}", flush=True)
        return {"variant": variant, "steps_done": len(done), "last": done[-1], "step_mean_s": float(np.mean(model.step_times))}
    finally:
        model.close()
