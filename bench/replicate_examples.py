"""T-007: replicate the official fastscapelib-fortran examples with the project's driver.

Sources (fetched 2026-09-04 from github.com/fastscape-lem/fastscapelib-fortran, examples/):
Mountain.f90, DippingDyke.f90, Fan.f90, FastScape_test.ipynb. Parameters are copied verbatim; only the
grid is changed for the "scaled" variants (500 x 500 nodes, 1 km spacing). Run length is decided by a
state criterion (see fs_driver.SteadyStateStop / PlateauFractionStop) with a step cap.

  python replicate_examples.py --example notebook_original      # driver verification, original grid
  python replicate_examples.py --example fan_original
  python replicate_examples.py --example mountain
  python replicate_examples.py --example dippingdyke
  python replicate_examples.py --example fan --target-from results/examples/fan_original
  python replicate_examples.py --example notebook --target-from results/examples/notebook_original
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from fs_driver import FastScapeRun, PlateauFractionStop, SteadyStateStop, fixed_border_mask, grid_xy, run_until

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "examples"
SCALED = {"nx": 500, "ny": 500, "dx": 1000.0}


def noise(nx: int, ny: int, seed: int) -> np.ndarray:
    return np.random.RandomState(seed).rand(ny, nx)


def build(example: str, seed: int, target: float | None):
    """Return (run, stop, before_step, info) for one example."""
    if example == "mountain":
        nx, ny, dx = SCALED["nx"], SCALED["ny"], SCALED["dx"]
        u = np.full((ny, nx), 1e-3)
        u[fixed_border_mask(1111, nx, ny)] = 0.0
        run = FastScapeRun(nx=nx, ny=ny, dx=dx, dt=1e5, kf=2e-6, kfsed=-1.0, m=0.6, n=1.5, kd=1e-1, kdsed=-1.0,
                           g1=0.0, g2=0.0, p=-2.0, single_flow=False, bc=1111, uplift=u, seed=seed, label="mountain")
        stop = SteadyStateStop(1e-3, rel_tol=0.01, consecutive=3)
        info = {"source": "examples/Mountain.f90", "original_grid": "401x401, 100 km, dt 1e5 yr, 100 steps",
                "check_every": 10}
        return run, stop, None, info

    if example == "dippingdyke":
        nx, ny, dx = SCALED["nx"], SCALED["ny"], SCALED["dx"]
        xl = (nx - 1) * dx
        X, _Y = grid_xy(nx, ny, dx)
        u = np.full((ny, nx), 1e-3)
        u[fixed_border_mask(1111, nx, ny)] = 0.0
        run = FastScapeRun(nx=nx, ny=ny, dx=dx, dt=1e5, kf=2e-5, kfsed=-1.0, m=0.4, n=1.0, kd=1e-1, kdsed=-1.0,
                           g1=0.0, g2=-1.0, p=1.0, single_flow=False, bc=1111, uplift=u, seed=seed, label="dippingdyke")
        x_dyke, dx_dyke = xl / 10.0, xl / 50.0
        cotana = 1.0 / math.tan(math.radians(30.0))

        def before_step(r: FastScapeRun) -> None:
            e = r.total_erosion()
            kf = np.full((ny, nx), 2e-5)
            s = x_dyke + e * cotana
            kf[(X - s - dx_dyke) * (X - s + dx_dyke) <= 0.0] = 1e-5
            r.set_kf(kf)

        stop = SteadyStateStop(1e-3, rel_tol=0.01, consecutive=3)
        info = {"source": "examples/DippingDyke.f90", "original_grid": "201x201, 100 km, dt 1e5 yr, 500 steps",
                "dyke": {"x_dyke_m": x_dyke, "half_width_m": dx_dyke, "dip_deg": 30.0, "kf_dyke": 1e-5},
                "check_every": 10}
        return run, stop, before_step, info

    if example in ("fan", "fan_original"):
        if example == "fan":
            nx, ny, dx = SCALED["nx"], SCALED["ny"], SCALED["dx"]
        else:
            nx, ny, dx = 101, 201, 100.0
        yl = (ny - 1) * dx
        _X, Y = grid_xy(nx, ny, dx)
        h0 = noise(nx, ny, seed)
        mask = Y > yl / 2.0
        h0 = np.where(mask, h0 + 1000.0, h0)
        run = FastScapeRun(nx=nx, ny=ny, dx=dx, dt=2e3, kf=1e-4, kfsed=1.5e-4, m=0.4, n=1.0, kd=1e-2, kdsed=1.5e-2,
                           g1=1.0, g2=1.0, p=1.0, single_flow=False, bc=1000, uplift=0.0, h0=h0, seed=seed, label=example)
        stop = PlateauFractionStop(mask, h0, 0.0, target if target is not None else 2.0)
        info = {"source": "examples/Fan.f90", "original_grid": "101x201, 10x20 km, dt 2e3 yr, 200 steps",
                "plateau": "1000 m where y > yl/2", "check_every": 100 if example == "fan" else 200}
        return run, stop, None, info

    if example in ("notebook", "notebook_original"):
        if example == "notebook":
            nx, ny, dx = SCALED["nx"], SCALED["ny"], SCALED["dx"]
        else:
            nx, ny, dx = 201, 101, 100.0
        xl = (nx - 1) * dx
        X, _Y = grid_xy(nx, ny, dx)
        h0 = noise(nx, ny, seed)
        mask = X > xl / 2.0
        h0 = np.where(mask, h0 + 1000.0, h0)
        run = FastScapeRun(nx=nx, ny=ny, dx=dx, dt=2e3, kf=1e-4, kfsed=1e-4, m=0.4, n=1.0, kd=1e-2, kdsed=1e-2,
                           g1=1.0, g2=1.0, p=1.0, single_flow=False, bc=1, uplift=0.0, h0=h0, seed=seed, label=example)
        stop = PlateauFractionStop(mask, h0, 0.0, target if target is not None else 2.0)
        info = {"source": "examples/FastScape_test.ipynb", "original_grid": "201x101, 20x10 km, dt 2e3 yr, 200 steps",
                "plateau": "1000 m where x > xl/2", "check_every": 100 if example == "notebook" else 200}
        return run, stop, None, info

    raise ValueError(example)


def save_figure(out: Path, h: np.ndarray, a: np.ndarray, dx: float, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ny, nx = h.shape
    x = np.arange(nx) * dx / 1e3
    y = np.arange(ny) * dx / 1e3
    fig, axes = plt.subplots(1, 2, figsize=(12, 5 * ny / nx + 1.5))
    c0 = axes[0].contourf(x, y, h, 20)
    axes[0].set_title(f"{title}: elevation (m)")
    fig.colorbar(c0, ax=axes[0])
    c1 = axes[1].contourf(x, y, np.log10(a), 20)
    axes[1].set_title(f"{title}: log10 drainage area (m2)")
    fig.colorbar(c1, ax=axes[1])
    for ax in axes:
        ax.set_aspect(1)
        ax.set_xlabel("x (km)")
        ax.set_ylabel("y (km)")
    fig.tight_layout()
    fig.savefig(out / "figure.png", dpi=110)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--example", required=True,
                   choices=["mountain", "dippingdyke", "fan", "notebook", "fan_original", "notebook_original"])
    p.add_argument("--out", default=None)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--max-steps", type=int, default=20000)
    p.add_argument("--check-every", type=int, default=None)
    p.add_argument("--target-fraction", type=float, default=None,
                   help="plateau examples: eroded-fraction target; default read from --target-from")
    p.add_argument("--target-from", default=None, help="directory of an *_original run to take the target from")
    p.add_argument("--figure", action="store_true", help="also write figure.png (elevation and log10 area)")
    a = p.parse_args()

    target = a.target_fraction
    if target is None and a.target_from:
        meta = json.loads((Path(a.target_from) / "meta.json").read_text(encoding="utf-8"))
        target = meta["loop"]["criterion"]["final_fraction"]
    is_original = a.example.endswith("_original")
    run, stop, before_step, info = build(a.example, a.seed, target)
    check_every = a.check_every or info["check_every"]
    max_steps = 200 if is_original else a.max_steps   # originals run exactly their published 200 steps
    out = Path(a.out) if a.out else RESULTS / a.example
    try:
        record = run_until(run, max_steps=max_steps, stop=None if is_original else stop,
                           check_every=check_every, before_step=before_step)
        if is_original:
            stop(run)  # evaluate the criterion once so the final fraction is recorded
            record["criterion"] = stop.describe()
        extra = {"task": "T-007", "example": a.example, "info": info, "loop": record,
                 "target_fraction": target}
        run.export_final(out, extra=extra)
        if a.figure or is_original:
            save_figure(out, run.h(), run.drainage_area(), run.dx, a.example)
        print("written", out, "steps", run.step, "reason", record["stop_reason"], flush=True)
    finally:
        run.close()


if __name__ == "__main__":
    main()
