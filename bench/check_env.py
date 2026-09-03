"""T-001 E0 check: imports, minimal runs for Landlab (3 routing configurations) and fastscape.

Writes bench/results/env_check.json. Creates files only under bench/results.
"""
import importlib
import json
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "env_check.json"
OUT.parent.mkdir(exist_ok=True)

report = {
    "python": sys.version,
    "executable": sys.executable,
    "platform": platform.platform(),
    "imports": {},
    "landlab_min_run": {},
    "fastscape_min_run": {},
}

PKGS = ["numpy", "scipy", "numba", "xarray", "zarr", "xsimlab", "landlab", "fastscape",
        "fastscapelib_fortran", "richdem", "psutil", "dask", "matplotlib"]
for name in PKGS:
    try:
        m = importlib.import_module(name)
        report["imports"][name] = {"ok": True, "version": getattr(m, "__version__", "n/a")}
    except Exception as e:  # noqa: BLE001
        report["imports"][name] = {"ok": False, "error": repr(e), "traceback": traceback.format_exc()}

# minimal unified physical setup
NY = NX = 30
DX = 1000.0
DT = 1000.0
NSTEPS = 5
K, M, N = 1e-5, 0.4, 1.0
D = 0.01
U = 1e-3
SEED = 1234


def init_surface(ny, nx, seed):
    return np.random.RandomState(seed).rand(ny, nx)


def landlab_run(config):
    from landlab import RasterModelGrid
    from landlab.components import (FastscapeEroder, FlowAccumulator, LakeMapperBarnes,
                                    LinearDiffuser, PriorityFloodFlowRouter)

    grid = RasterModelGrid((NY, NX), xy_spacing=DX)
    z = grid.add_field("topographic__elevation", init_surface(NY, NX, SEED).ravel(),
                       at="node", clobber=True)
    if config == "DepressionFinderAndRouter":
        fa = FlowAccumulator(grid, flow_director="D8", depression_finder="DepressionFinderAndRouter")

        def route():
            fa.run_one_step()
    elif config == "LakeMapperBarnes":
        fa = FlowAccumulator(grid, flow_director="D8")
        fill = grid.zeros(at="node")
        lmb = LakeMapperBarnes(grid, method="D8", fill_flat=False, surface="topographic__elevation",
                               fill_surface=fill, redirect_flow_steepest_descent=True,
                               reaccumulate_flow=True, ignore_overfill=True, track_lakes=True)

        def route():
            fa.run_one_step()
            lmb.run_one_step()
    elif config == "PriorityFloodFlowRouter":
        pf = PriorityFloodFlowRouter(grid, flow_metric="D8", depression_handler="fill",
                                     accumulate_flow=True)

        def route():
            pf.run_one_step()
    else:
        raise ValueError(config)
    if "flood_status_code" not in grid.at_node:
        grid.add_zeros("flood_status_code", at="node", dtype=int)
    sp = FastscapeEroder(grid, K_sp=K, m_sp=M, n_sp=N, erode_flooded_nodes=False)
    ld = LinearDiffuser(grid, linear_diffusivity=D)
    core = grid.core_nodes
    t0 = time.perf_counter()
    for _ in range(NSTEPS):
        z[core] += U * DT
        route()
        sp.run_one_step(DT)
        ld.run_one_step(DT)
    el = time.perf_counter() - t0
    A = grid.at_node["drainage_area"]
    return {"ok": True, "seconds_total": el, "steps": NSTEPS,
            "z_min": float(z.min()), "z_max": float(z.max()), "z_finite": bool(np.isfinite(z).all()),
            "A_min_core": float(A[core].min()), "A_max": float(A.max()),
            "A_finite": bool(np.isfinite(A).all()), "cell_area": DX * DX,
            "node_fields": sorted(grid.at_node.keys())}


for cfg in ["DepressionFinderAndRouter", "LakeMapperBarnes", "PriorityFloodFlowRouter"]:
    try:
        report["landlab_min_run"][cfg] = landlab_run(cfg)
    except Exception as e:  # noqa: BLE001
        report["landlab_min_run"][cfg] = {"ok": False, "error": repr(e), "traceback": traceback.format_exc()}


def fastscape_run(store=None):
    import xsimlab as xs
    from fastscape.models import basic_model

    clocks = {"time": np.arange(0, (NSTEPS + 1) * DT, DT), "out": np.array([NSTEPS * DT])}
    in_ds = xs.create_setup(
        model=basic_model, clocks=clocks, master_clock="time",
        input_vars={"grid__shape": [NY, NX], "grid__length": [(NY - 1) * DX, (NX - 1) * DX],
                    "boundary__status": "fixed_value", "uplift__rate": U,
                    "spl__k_coef": K, "spl__area_exp": M, "spl__slope_exp": N,
                    "diffusion__diffusivity": D, "init_topography__seed": SEED},
        output_vars={"topography__elevation": "out", "drainage__area": "out", "grid__dx": None},
    )
    t0 = time.perf_counter()
    out = in_ds.xsimlab.run(model=basic_model, store=store)
    el = time.perf_counter() - t0
    z = out["topography__elevation"].isel(out=-1).values
    A = out["drainage__area"].isel(out=-1).values
    return {"ok": True, "seconds_total": el, "steps": NSTEPS,
            "z_min": float(z.min()), "z_max": float(z.max()), "z_finite": bool(np.isfinite(z).all()),
            "A_min": float(A.min()), "A_max": float(A.max()), "A_finite": bool(np.isfinite(A).all()),
            "store": repr(store), "grid_dx": float(out["grid__dx"].values)}


try:
    report["fastscape_min_run"]["memory_store"] = fastscape_run(None)
except Exception as e:  # noqa: BLE001
    report["fastscape_min_run"]["memory_store"] = {"ok": False, "error": repr(e), "traceback": traceback.format_exc()}
try:
    p = HERE / "results" / "_zarr_check.zarr"
    if p.exists():
        shutil.rmtree(p)
    report["fastscape_min_run"]["directory_store"] = fastscape_run(str(p))
except Exception as e:  # noqa: BLE001
    report["fastscape_min_run"]["directory_store"] = {"ok": False, "error": repr(e), "traceback": traceback.format_exc()}

OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

for k, v in report["imports"].items():
    print(f"import    {k:26s} " + (f"OK   {v['version']}" if v["ok"] else f"FAIL {v['error']}"))
for k, v in report["landlab_min_run"].items():
    print(f"landlab   {k:26s} " + (f"OK   {v['seconds_total']:.2f}s z[{v['z_min']:.2f},{v['z_max']:.2f}] A[{v['A_min_core']:.3g},{v['A_max']:.3g}]" if v["ok"] else f"FAIL {v['error']}"))
for k, v in report["fastscape_min_run"].items():
    print(f"fastscape {k:26s} " + (f"OK   {v['seconds_total']:.2f}s z[{v['z_min']:.2f},{v['z_max']:.2f}] A[{v['A_min']:.3g},{v['A_max']:.3g}] dx={v['grid_dx']}" if v["ok"] else f"FAIL {v['error']}"))
print("written:", OUT)
