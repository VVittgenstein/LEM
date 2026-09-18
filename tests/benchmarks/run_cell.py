"""One benchmark run (one cell, one repeat). Writes one JSON result file.

Configs
  DFR          Landlab FlowAccumulator(D8) + DepressionFinderAndRouter
  LMB          Landlab FlowAccumulator(D8) + LakeMapperBarnes(D8)
  PFFR         Landlab PriorityFloodFlowRouter(D8, fill)
  FS           fastscapelib-fortran, FastScape_Execute_Step per step (single flow direction)
  FS_PIECEWISE fastscapelib-fortran, routines called one by one for component timing
Groups
  elev         export elevation only
  elev_da      export elevation and drainage area
"""
import argparse
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

T0 = time.perf_counter()


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--tool", required=True, choices=["landlab", "fastscape"])
    p.add_argument("--config", required=True, choices=["DFR", "LMB", "PFFR", "FS", "FS_PIECEWISE"])
    p.add_argument("--group", required=True, choices=["elev", "elev_da"])
    p.add_argument("--K", type=float, required=True)
    p.add_argument("--steps", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--export-dir", default=None)
    p.add_argument("--nx", type=int, default=500)
    p.add_argument("--ny", type=int, default=500)
    p.add_argument("--dx", type=float, default=1000.0)
    p.add_argument("--dt", type=float, default=1000.0)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--D", type=float, default=0.01)
    p.add_argument("--U", type=float, default=1e-3)
    p.add_argument("--m", type=float, default=0.4)
    p.add_argument("--n", type=float, default=1.0)
    p.add_argument("--warm-steps", type=int, default=5, help="steps excluded from steady statistics")
    return p.parse_args()


def apply_affinity():
    import psutil
    aff = os.environ.get("BENCH_AFFINITY")
    proc = psutil.Process()
    if aff:
        proc.cpu_affinity([int(x) for x in aff.split(",")])
    return proc.cpu_affinity()


def init_surface(ny, nx, seed):
    import numpy as np
    return np.random.RandomState(seed).rand(ny, nx)


def run_landlab(a, z0):
    import numpy as np
    from landlab import NodeStatus, RasterModelGrid
    from landlab.components import (FastscapeEroder, FlowAccumulator, LakeMapperBarnes,
                                    LinearDiffuser, PriorityFloodFlowRouter)
    from landlab.components.depression_finder.floodstatus import FloodStatus

    t_setup0 = time.perf_counter()
    grid = RasterModelGrid((a.ny, a.nx), xy_spacing=a.dx)
    z = grid.add_field("topographic__elevation", z0.ravel().copy(), at="node", clobber=True)
    assert np.all(grid.status_at_node[grid.boundary_nodes] == NodeStatus.FIXED_VALUE)
    extra = {}
    if a.config == "DFR":
        fa = FlowAccumulator(grid, flow_director="D8", depression_finder="DepressionFinderAndRouter")

        def route():
            fa.run_one_step()
            return 0.0
    elif a.config == "LMB":
        fa = FlowAccumulator(grid, flow_director="D8")
        fill = grid.zeros(at="node")
        lmb = LakeMapperBarnes(grid, method="D8", fill_flat=False, surface="topographic__elevation",
                               fill_surface=fill, redirect_flow_steepest_descent=True,
                               reaccumulate_flow=True, ignore_overfill=True, track_lakes=True)
        if "flood_status_code" not in grid.at_node:
            grid.add_zeros("flood_status_code", at="node", dtype=int)

        def route():
            fa.run_one_step()
            t = time.perf_counter()
            lmb.run_one_step()
            return time.perf_counter() - t
    elif a.config == "PFFR":
        pf = PriorityFloodFlowRouter(grid, flow_metric="D8", depression_handler="fill", accumulate_flow=True)

        def route():
            pf.run_one_step()
            return 0.0
    else:
        raise ValueError(a.config)
    sp = FastscapeEroder(grid, K_sp=a.K, m_sp=a.m, n_sp=a.n, erode_flooded_nodes=False)
    ld = LinearDiffuser(grid, linear_diffusivity=a.D)
    core = grid.core_nodes
    udt = a.U * a.dt
    t_setup = time.perf_counter() - t_setup0

    comp = {"uplift": [], "route": [], "route_fill": [], "spl": [], "diff": [], "total": []}
    for _ in range(a.steps):
        t0 = time.perf_counter()
        z[core] += udt
        t1 = time.perf_counter()
        fill_t = route()
        t2 = time.perf_counter()
        sp.run_one_step(a.dt)
        t3 = time.perf_counter()
        ld.run_one_step(a.dt)
        t4 = time.perf_counter()
        comp["uplift"].append(t1 - t0)
        comp["route"].append(t2 - t1)
        comp["route_fill"].append(fill_t)
        comp["spl"].append(t3 - t2)
        comp["diff"].append(t4 - t3)
        comp["total"].append(t4 - t0)
    A = grid.at_node["drainage_area"]
    fsc = grid.at_node["flood_status_code"]
    extra["flooded_nodes_final"] = int(np.sum(fsc == FloodStatus._FLOODED))
    extra["A_min_core"] = float(A[core].min())
    return t_setup, comp, z.reshape(a.ny, a.nx).copy(), A.reshape(a.ny, a.nx).copy(), extra


def run_fastscape(a, z0):
    import numpy as np
    import fastscapelib_fortran as fs
    ctx = fs.fastscapecontext
    nn = a.nx * a.ny
    t_setup0 = time.perf_counter()
    fs.fastscape_init()
    fs.fastscape_set_nx_ny(a.nx, a.ny)
    fs.fastscape_setup()
    fs.fastscape_set_xl_yl((a.nx - 1) * a.dx, (a.ny - 1) * a.dx)
    fs.fastscape_set_bc(1111)
    h = np.ascontiguousarray(z0.ravel(), dtype="d")
    fs.fastscape_init_h(h)
    fs.fastscape_set_dt(a.dt)
    fs.fastscape_set_erosional_parameters(np.full(nn, a.K), -1.0, a.m, a.n, np.full(nn, a.D), -1.0, 0.0, 0.0, 0.0)
    ctx.singleflowdirection = 1
    u = np.full((a.ny, a.nx), a.U)
    u[0, :] = 0.0
    u[-1, :] = 0.0
    u[:, 0] = 0.0
    u[:, -1] = 0.0
    fs.fastscape_set_u(u.ravel())
    t_setup = time.perf_counter() - t_setup0

    comp = {"uplift": [], "route": [], "accum": [], "spl": [], "diff": [], "total": []}
    if a.config == "FS":
        for _ in range(a.steps):
            t0 = time.perf_counter()
            fs.fastscape_execute_step()
            comp["total"].append(time.perf_counter() - t0)
    else:
        for _ in range(a.steps):
            t0 = time.perf_counter()
            fs.uplift()
            t1 = time.perf_counter()
            fs.flowroutingsingleflowdirection()
            t2 = time.perf_counter()
            fs.flowaccumulationsingleflowdirection()
            t3 = time.perf_counter()
            fs.streampowerlawsingleflowdirection()
            t4 = time.perf_counter()
            fs.diffusion()
            t5 = time.perf_counter()
            comp["uplift"].append(t1 - t0)
            comp["route"].append(t2 - t1)
            comp["accum"].append(t3 - t2)
            comp["spl"].append(t4 - t3)
            comp["diff"].append(t5 - t4)
            comp["total"].append(t5 - t0)
    hout = np.empty(nn)
    aout = np.empty(nn)
    lake = np.empty(nn)
    fs.fastscape_copy_h(hout)
    fs.fastscape_copy_drainage_area(aout)
    fs.fastscape_copy_lake_depth(lake)
    fs.fastscape_destroy()
    extra = {"flooded_nodes_final": int(np.sum(lake > 0.0)),
             "A_min_core": float(aout.reshape(a.ny, a.nx)[1:-1, 1:-1].min())}
    return t_setup, comp, hout.reshape(a.ny, a.nx), aout.reshape(a.ny, a.nx), extra


def export(arrays, export_dir, run_id):
    import numpy as np
    times = {}
    d = Path(export_dir)
    d.mkdir(parents=True, exist_ok=True)
    for name, arr in arrays.items():
        p = d / f"{run_id}_{name}.npy"
        t0 = time.perf_counter()
        with open(p, "wb") as f:
            np.save(f, arr)
            f.flush()
            os.fsync(f.fileno())
        times[name] = time.perf_counter() - t0
    return times


def main():
    a = parse()
    started = datetime.now(timezone.utc).isoformat()
    t_imp0 = time.perf_counter()
    import numpy as np
    import psutil
    if a.tool == "landlab":
        import landlab
        tool_version = landlab.__version__
    else:
        import fastscapelib_fortran  # noqa: F401
        from importlib.metadata import PackageNotFoundError, version
        tool_version = "unknown"
        for dist in ("fastscapelib_fortran", "fastscapelib-fortran", "fastscapelib-f2py"):
            try:
                tool_version = version(dist)
                break
            except PackageNotFoundError:
                continue
    t_import = time.perf_counter() - t_imp0
    affinity = apply_affinity()

    z0 = init_surface(a.ny, a.nx, a.seed)
    if a.tool == "landlab":
        t_setup, comp, z, A, extra = run_landlab(a, z0)
    else:
        t_setup, comp, z, A, extra = run_fastscape(a, z0)

    run_id = Path(a.out).stem
    arrays = {"elev": z}
    if a.group == "elev_da":
        arrays["da"] = A
    export_times = export(arrays, a.export_dir, run_id) if a.export_dir else {}

    tot = np.array(comp["total"])
    ws = a.warm_steps
    steady = tot[ws:] if len(tot) > ws else tot
    stats = {
        "steps": a.steps,
        "first_step_s": float(tot[0]),
        "steady_mean_s": float(steady.mean()),
        "steady_median_s": float(np.median(steady)),
        "steady_min_s": float(steady.min()),
        "steady_max_s": float(steady.max()),
        "sum_steps_s": float(tot.sum()),
        "components_steady_mean_s": {k: float(np.mean(v[ws:])) for k, v in comp.items() if len(v) > ws},
    }
    proc = psutil.Process()
    mem = proc.memory_info()
    result = {
        "run_id": run_id,
        "status": "ok",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "args": vars(a),
        "tool_version": tool_version,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "affinity": affinity,
        "thread_env": {k: os.environ.get(k) for k in
                       ["OMP_NUM_THREADS", "NUMBA_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]},
        "t_import_s": t_import,
        "t_setup_s": t_setup,
        "stats": stats,
        "per_step": comp,
        "export_s": export_times,
        "peak_wset_MB": getattr(mem, "peak_wset", 0) / 2**20,
        "rss_MB": mem.rss / 2**20,
        "output": {
            "z_min": float(z.min()), "z_max": float(z.max()), "z_finite": bool(np.isfinite(z).all()),
            "A_max": float(A.max()), "A_finite": bool(np.isfinite(A).all()), **extra,
        },
        "wall_s": time.perf_counter() - T0,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"{run_id}: steady {stats['steady_mean_s'] * 1e3:.1f} ms/step, first {stats['first_step_s'] * 1e3:.1f} ms, "
          f"peak {result['peak_wset_MB']:.0f} MB, wall {result['wall_s']:.1f} s, flooded {extra['flooded_nodes_final']}")


if __name__ == "__main__":
    main()
