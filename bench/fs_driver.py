"""Thin runner around fastscapelib-fortran's FastScape API.

Used by ``evolve.py`` (T-006) and ``replicate_examples.py`` (T-007). Every setting is explicit and
written to ``meta.json`` next to the exported arrays.

Boundary code ``bc`` follows the FastScape convention of four digits ordered
bottom, right, top, left (``1111`` = all four fixed at base level; ``1000`` = bottom only;
``1`` = left only). Fixed borders keep their initial elevation when uplift is zero there.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import fastscapelib_fortran as fs

ctx = fs.fastscapecontext


def fixed_border_mask(bc: int, nx: int, ny: int) -> np.ndarray:
    """Boolean (ny, nx) mask of nodes on borders whose bc digit is 1."""
    d = str(int(bc)).zfill(4)
    m = np.zeros((ny, nx), dtype=bool)
    if d[0] == "1":
        m[0, :] = True       # bottom (first row, y = 0)
    if d[1] == "1":
        m[:, -1] = True      # right
    if d[2] == "1":
        m[-1, :] = True      # top
    if d[3] == "1":
        m[:, 0] = True       # left
    return m


def grid_xy(nx: int, ny: int, dx: float) -> tuple[np.ndarray, np.ndarray]:
    """Node coordinates (ny, nx); x along columns, y along rows, origin at node 0."""
    x = np.arange(nx) * dx
    y = np.arange(ny) * dx
    return np.meshgrid(x, y)


class FastScapeRun:
    """One FastScape model instance. Arrays are (ny, nx); FastScape order is x fastest."""

    def __init__(self, *, nx: int, ny: int, dx: float, dt: float, kf, m: float, n: float, kd,
                 kfsed: float = -1.0, kdsed: float = -1.0, g1: float = 0.0, g2: float = 0.0, p: float = 0.0,
                 single_flow: bool = True, bc: int = 1111, uplift=0.0, h0: np.ndarray | None = None,
                 seed: int = 1234, noise_amplitude: float = 1.0, label: str = ""):
        self.nx, self.ny, self.dx, self.dt = int(nx), int(ny), float(dx), float(dt)
        self.nn = self.nx * self.ny
        self.m, self.n, self.kfsed, self.kdsed, self.g1, self.g2, self.p = float(m), float(n), float(kfsed), float(kdsed), float(g1), float(g2), float(p)
        self.single_flow, self.bc, self.seed, self.label = bool(single_flow), int(bc), int(seed), label
        self.kf = np.ascontiguousarray(np.broadcast_to(np.asarray(kf, dtype="d"), (self.ny, self.nx))).copy()
        self.kd = np.ascontiguousarray(np.broadcast_to(np.asarray(kd, dtype="d"), (self.ny, self.nx))).copy()
        self.uplift = np.ascontiguousarray(np.broadcast_to(np.asarray(uplift, dtype="d"), (self.ny, self.nx))).copy()
        if h0 is None:
            h0 = np.random.RandomState(self.seed).rand(self.ny, self.nx) * noise_amplitude
        self.h0 = np.ascontiguousarray(h0, dtype="d")
        self.step = 0
        self.t_setup = None
        self.step_times: list[float] = []
        self._setup()

    # -- lifecycle ---------------------------------------------------------------------------
    def _setup(self) -> None:
        t0 = time.perf_counter()
        fs.fastscape_init()
        fs.fastscape_set_nx_ny(self.nx, self.ny)
        fs.fastscape_setup()
        fs.fastscape_set_xl_yl((self.nx - 1) * self.dx, (self.ny - 1) * self.dx)
        fs.fastscape_set_bc(self.bc)
        h = self.h0.ravel().copy()
        fs.fastscape_init_h(h)
        fs.fastscape_set_dt(self.dt)
        self._push_erosional_parameters()
        ctx.singleflowdirection = 1 if self.single_flow else 0
        fs.fastscape_set_u(self.uplift.ravel().copy())
        self.t_setup = time.perf_counter() - t0

    def _push_erosional_parameters(self) -> None:
        fs.fastscape_set_erosional_parameters(self.kf.ravel(), self.kfsed, self.m, self.n, self.kd.ravel(),
                                              self.kdsed, self.g1, self.g2, self.p)

    def set_kf(self, kf: np.ndarray) -> None:
        """Replace the erodibility field (used for time-varying K such as an exhumed dyke)."""
        self.kf = np.ascontiguousarray(np.broadcast_to(np.asarray(kf, dtype="d"), (self.ny, self.nx))).copy()
        self._push_erosional_parameters()

    def close(self) -> None:
        fs.fastscape_destroy()

    # -- stepping ----------------------------------------------------------------------------
    def advance(self, k: int = 1) -> None:
        for _ in range(k):
            t0 = time.perf_counter()
            fs.fastscape_execute_step()
            self.step_times.append(time.perf_counter() - t0)
            self.step += 1

    # -- state access ------------------------------------------------------------------------
    def _copy(self, fn) -> np.ndarray:
        out = np.empty(self.nn)
        fn(out)
        return out.reshape(self.ny, self.nx)

    def h(self) -> np.ndarray:
        return self._copy(fs.fastscape_copy_h)

    def drainage_area(self) -> np.ndarray:
        return self._copy(fs.fastscape_copy_drainage_area)

    def lake_depth(self) -> np.ndarray:
        return self._copy(fs.fastscape_copy_lake_depth)

    def total_erosion(self) -> np.ndarray:
        return self._copy(fs.fastscape_copy_total_erosion)

    def basement(self) -> np.ndarray:
        return self._copy(fs.fastscape_copy_basement)

    @property
    def time_years(self) -> float:
        return self.step * self.dt

    # -- export ------------------------------------------------------------------------------
    def settings(self) -> dict:
        return {
            "label": self.label, "nx": self.nx, "ny": self.ny, "dx_m": self.dx, "dt_yr": self.dt,
            "kf": _describe(self.kf), "kfsed": self.kfsed, "m": self.m, "n": self.n,
            "kd": _describe(self.kd), "kdsed": self.kdsed, "g1": self.g1, "g2": self.g2, "p": self.p,
            "single_flow_direction": self.single_flow, "bc": self.bc, "uplift_m_per_yr": _describe(self.uplift),
            "seed": self.seed, "initial_topography": "random uniform noise" if self.h0.max() <= 1.0 else "custom (see meta)",
            "library": "fastscapelib-fortran 2.8.4 (FastScape API via Python)",
        }

    def export_final(self, out_dir: Path | str, extra: dict | None = None) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        h = self.h()
        a = self.drainage_area()
        np.save(out / "elevation.npy", h)
        np.save(out / "drainage_area.npy", a)
        st = np.array(self.step_times) if self.step_times else np.array([0.0])
        meta = {
            "written_utc": datetime.now(timezone.utc).isoformat(),
            "settings": self.settings(),
            "steps": self.step, "time_yr": self.time_years,
            "channels": {
                "elevation": {"file": "elevation.npy", "units": "m", "kind": "elevation"},
                "drainage_area": {"file": "drainage_area.npy", "units": "m2", "kind": "drainage_area", "display": "log10"},
            },
            "grid": {"nx": self.nx, "ny": self.ny, "dx_m": self.dx, "dy_m": self.dx},
            "timing": {"setup_s": self.t_setup, "steps_total_s": float(st.sum()), "step_mean_s": float(st.mean()),
                       "step_first_s": float(st[0]), "step_last_s": float(st[-1])},
            "output": {"z_min": float(h.min()), "z_max": float(h.max()), "z_mean": float(h.mean()),
                       "A_max": float(a.max()), "finite": bool(np.isfinite(h).all() and np.isfinite(a).all()),
                       "lake_cells": int((self.lake_depth() > 0).sum())},
        }
        if extra:
            meta.update(extra)
        (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
        return out


def _describe(arr: np.ndarray) -> dict | float:
    if np.all(arr == arr.flat[0]):
        return float(arr.flat[0])
    return {"min": float(arr.min()), "max": float(arr.max()), "mean": float(arr.mean()), "field": True}


# -- stop criteria --------------------------------------------------------------------------------
class SteadyStateStop:
    """Stop when the core-mean elevation change rate is below ``rel_tol`` × uplift for ``consecutive`` checks."""

    def __init__(self, uplift_rate: float, rel_tol: float = 0.01, consecutive: int = 3):
        self.u, self.rel_tol, self.consecutive = float(uplift_rate), rel_tol, consecutive
        self._prev = None
        self._prev_step = None
        self._hits = 0
        self.history: list[dict] = []

    def __call__(self, run: FastScapeRun) -> bool:
        h = run.h()[1:-1, 1:-1].mean()
        if self._prev is not None:
            rate = (h - self._prev) / ((run.step - self._prev_step) * run.dt)
            ratio = abs(rate) / self.u if self.u else abs(rate)
            self.history.append({"step": run.step, "mean_dh_dt": rate, "ratio_to_uplift": ratio})
            self._hits = self._hits + 1 if ratio < self.rel_tol else 0
        self._prev, self._prev_step = h, run.step
        return self._hits >= self.consecutive

    def describe(self) -> dict:
        return {"type": "steady_state", "rel_tol": self.rel_tol, "consecutive": self.consecutive, "history": self.history}


class PlateauFractionStop:
    """Stop when the eroded fraction of a plateau's initial excess volume reaches ``target``."""

    def __init__(self, plateau_mask: np.ndarray, h0: np.ndarray, base_level: float, target: float):
        self.mask = plateau_mask
        self.v0 = float(np.sum(np.clip(h0[plateau_mask] - base_level, 0, None)))
        self.target = float(target)
        self.h0 = h0
        self.history: list[dict] = []
        self.last = 0.0

    def fraction(self, run: FastScapeRun) -> float:
        h = run.h()
        removed = float(np.sum(np.clip(self.h0[self.mask] - h[self.mask], 0, None)))
        return removed / self.v0 if self.v0 else 0.0

    def __call__(self, run: FastScapeRun) -> bool:
        f = self.fraction(run)
        self.last = f
        self.history.append({"step": run.step, "eroded_fraction": f})
        return f >= self.target

    def describe(self) -> dict:
        return {"type": "plateau_fraction", "target": self.target, "final_fraction": self.last, "history": self.history}


def run_until(run: FastScapeRun, *, max_steps: int, stop=None, check_every: int = 100, on_check=None,
              before_step=None, log=print) -> dict:
    """Advance ``run`` until ``stop(run)`` is True (checked every ``check_every`` steps) or ``max_steps``.

    ``before_step(run)`` is called before every step (e.g. to update K). Returns a record of the loop.
    """
    t0 = time.perf_counter()
    reason = "max_steps"
    while run.step < max_steps:
        k = min(check_every, max_steps - run.step)
        if before_step is None:
            run.advance(k)
        else:
            for _ in range(k):
                before_step(run)
                run.advance(1)
        stopped = bool(stop(run)) if stop is not None else False
        if on_check is not None:
            on_check(run)
        if log is not None:
            st = run.step_times
            log(f"[{run.label}] step {run.step} t={run.time_years/1e6:.3f} Myr  step {np.mean(st[-k:])*1e3:.0f} ms  "
                f"elapsed {time.perf_counter()-t0:.0f} s", flush=True)
        if stopped:
            reason = "criterion"
            break
    return {"stop_reason": reason, "steps": run.step, "wall_s": time.perf_counter() - t0,
            "check_every": check_every, "max_steps": max_steps,
            "criterion": stop.describe() if stop is not None and hasattr(stop, "describe") else None}
