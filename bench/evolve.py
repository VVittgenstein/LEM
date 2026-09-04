"""T-006: long fastscape runs with the benchmark parameters, exporting only the final state.

Example:
  python evolve.py --dt 500 --steps 20000 --out results/evolve/dt500
  python evolve.py --dt 10000 --steps 1000 --out results/evolve/dt10000
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from fs_driver import FastScapeRun, fixed_border_mask, run_until

HERE = Path(__file__).resolve().parent


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dt", type=float, required=True)
    p.add_argument("--steps", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--nx", type=int, default=500)
    p.add_argument("--ny", type=int, default=500)
    p.add_argument("--dx", type=float, default=1000.0)
    p.add_argument("--K", type=float, default=1e-5)
    p.add_argument("--D", type=float, default=0.01)
    p.add_argument("--U", type=float, default=1e-3)
    p.add_argument("--m", type=float, default=0.4)
    p.add_argument("--n", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--bc", type=int, default=1111)
    p.add_argument("--log-every", type=int, default=500)
    a = p.parse_args()

    uplift = np.full((a.ny, a.nx), a.U)
    uplift[fixed_border_mask(a.bc, a.nx, a.ny)] = 0.0
    run = FastScapeRun(nx=a.nx, ny=a.ny, dx=a.dx, dt=a.dt, kf=a.K, m=a.m, n=a.n, kd=a.D,
                       single_flow=True, bc=a.bc, uplift=uplift, seed=a.seed,
                       label=f"evolve dt={a.dt:g}")
    try:
        record = run_until(run, max_steps=a.steps, stop=None, check_every=a.log_every)
        out = run.export_final(HERE / a.out if not Path(a.out).is_absolute() else a.out,
                               extra={"task": "T-006", "loop": record, "note": "benchmark parameters, final state only"})
        print("written", out, flush=True)
    finally:
        run.close()


if __name__ == "__main__":
    main()
