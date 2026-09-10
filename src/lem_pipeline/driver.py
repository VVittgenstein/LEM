"""FastScape 2.8.4 driver with marine module, precipitation, time-varying uplift and sea level.

Facts about the library that this module relies on (checked against the fixed-commit sources kept under
``references/`` on 2026-09-09):

* ``FastScape_Set_Erosional_Parameters(kf, kfsed, m, n, kd, kdsed, g1, g2, p)``: ``p`` is the multiple-flow-direction
  exponent; ``p < -1.5`` switches to single flow direction. ``kfsed``/``kdsed`` below zero mean "same as bedrock".
* ``FastScape_Set_Marine_Parameters(sl, p1, p2, z1, z2, r, l, kds1, kds2)`` switches the marine module on and stores the
  sea level; ``p1``/``p2`` (surface porosities) enter the decompaction of incoming solid volume (``Marine.f90`` lines
  46 to 47 and 116 to 117); ``z1``/``z2`` (porosity decay depths) only enter the compaction call, which is commented out
  in 2.8.4, so they are inert. Re-calling the routine each step is the only way to move the sea level.
* ``FastScape_Set_Precip(array)`` sets a per-node precipitation multiplier (default 1); ``FastScape_Set_U(array)`` sets
  the per-node uplift rate in m/yr and can be re-called at any step.
* One model instance per process: the Fortran module holds global state.
* Fixed borders (``bc`` digit 1) keep their initial elevation when their uplift is zero; the sea level must stay above
  the border elevation for the border to remain ocean.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:  # the library is only present in lem-env; importing the module elsewhere must still work for tests of pure code
    import fastscapelib_fortran as fs
    ctx = fs.fastscapecontext
except Exception:  # pragma: no cover
    fs = None
    ctx = None

SINGLE_FLOW_P = -2.0


@dataclass
class ProcessParams:
    """Global scalars of the erosion model (class-3 data)."""
    m: float = 0.45
    n: float = 1.0
    kfsed: float = -1.0
    kdsed: float = -1.0
    g1: float = 1.0
    g2: float = 1.0
    p: float = 1.0  # multiple flow direction exponent; SINGLE_FLOW_P selects single flow direction
    evidence_state: str = "尚待验证的假设"


@dataclass
class MarineParams:
    """Marine module parameter set. Default = Glerum 2024 pair (300, 100) with r = 0.5, p1 = p2 = 0, L = 1000 m
    (yZz 2026-09-09: take the source's parameter set as a whole and record p1/p2 explicitly)."""
    kds1: float = 300.0
    kds2: float = 100.0
    ratio: float = 0.5
    poro1: float = 0.0
    poro2: float = 0.0
    zporo1: float = 1.0e4  # inert in 2.8.4; recorded for completeness
    zporo2: float = 1.0e4
    layer: float = 1000.0
    evidence_state: str = "来源直接给出的模型设定，作为假设配置"


def fixed_border_mask(bc: int, nx: int, ny: int) -> np.ndarray:
    """Boolean (ny, nx) mask of nodes on borders whose bc digit is 1 (digits: bottom, right, top, left)."""
    d = str(int(bc)).zfill(4)
    m = np.zeros((ny, nx), dtype=bool)
    if d[0] == "1":
        m[0, :] = True
    if d[1] == "1":
        m[:, -1] = True
    if d[2] == "1":
        m[-1, :] = True
    if d[3] == "1":
        m[:, 0] = True
    return m


def _field(value, ny: int, nx: int) -> np.ndarray:
    return np.ascontiguousarray(np.broadcast_to(np.asarray(value, dtype="d"), (ny, nx))).copy()


class FastScapeModel:
    """One FastScape model instance. Arrays are (ny, nx) with x varying fastest in FastScape order."""

    def __init__(self, *, nx: int, ny: int, dx: float, dt: float, h0: np.ndarray, kf, kd,
                 process: ProcessParams | None = None, marine: MarineParams | None = None,
                 sea_level: float = 0.0, precip=1.0, uplift=0.0, bc: int = 1111, label: str = ""):
        if fs is None:
            raise RuntimeError("fastscapelib_fortran is not importable in this interpreter (use lem-env)")
        self.nx, self.ny, self.dx, self.dt = int(nx), int(ny), float(dx), float(dt)
        self.nn = self.nx * self.ny
        self.process = process or ProcessParams()
        self.marine = marine
        self.sea_level = float(sea_level)
        self.bc, self.label = int(bc), label
        self.h0 = np.ascontiguousarray(h0, dtype="d")
        assert self.h0.shape == (self.ny, self.nx), "h0 must be (ny, nx)"
        self.kf = _field(kf, self.ny, self.nx)
        self.kd = _field(kd, self.ny, self.nx)
        self.precip = _field(precip, self.ny, self.nx)
        self.uplift = _field(uplift, self.ny, self.nx)
        self.step = 0
        self.step_times: list[float] = []
        self.sea_level_history: list[tuple[int, float]] = []
        self.t_setup = None
        self._setup()

    # -- lifecycle ---------------------------------------------------------------------------
    def _setup(self) -> None:
        t0 = time.perf_counter()
        fs.fastscape_init()
        fs.fastscape_set_nx_ny(self.nx, self.ny)
        fs.fastscape_setup()
        fs.fastscape_set_xl_yl((self.nx - 1) * self.dx, (self.ny - 1) * self.dx)
        fs.fastscape_set_bc(self.bc)
        fs.fastscape_init_h(self.h0.ravel().copy())
        fs.fastscape_set_dt(self.dt)
        self._push_erosional_parameters()
        fs.fastscape_set_precip(self.precip.ravel().copy())
        fs.fastscape_set_u(self.uplift.ravel().copy())
        if self.marine is not None:
            self._push_marine()
        self.t_setup = time.perf_counter() - t0

    def _push_erosional_parameters(self) -> None:
        pr = self.process
        fs.fastscape_set_erosional_parameters(self.kf.ravel().copy(), pr.kfsed, pr.m, pr.n, self.kd.ravel().copy(),
                                              pr.kdsed, pr.g1, pr.g2, pr.p)

    def _push_marine(self) -> None:
        mp = self.marine
        fs.fastscape_set_marine_parameters(self.sea_level, mp.poro1, mp.poro2, mp.zporo1, mp.zporo2,
                                           mp.ratio, mp.layer, mp.kds1, mp.kds2)

    def enable(self, *, uplift: bool | None = None, spl: bool | None = None, diffusion: bool | None = None,
               marine: bool | None = None) -> None:
        """Switch individual processes (used by the timestep isolation experiments)."""
        if uplift is not None:
            ctx.runuplift = bool(uplift)
        if spl is not None:
            ctx.runspl = bool(spl)
        if diffusion is not None:
            ctx.rundiffusion = bool(diffusion)
        if marine is not None:
            if marine and self.marine is None:
                raise ValueError("marine parameters are required to enable the marine module")
            ctx.runmarine = bool(marine)

    def close(self) -> None:
        fs.fastscape_destroy()

    # -- time-varying inputs -----------------------------------------------------------------
    def set_uplift(self, uplift) -> None:
        self.uplift = _field(uplift, self.ny, self.nx)
        fs.fastscape_set_u(self.uplift.ravel().copy())

    def set_sea_level(self, sea_level: float) -> None:
        self.sea_level = float(sea_level)
        if self.marine is not None:
            self._push_marine()
        self.sea_level_history.append((self.step, self.sea_level))

    def set_precip(self, precip) -> None:
        self.precip = _field(precip, self.ny, self.nx)
        fs.fastscape_set_precip(self.precip.ravel().copy())

    def set_kf_kd(self, kf=None, kd=None) -> None:
        if kf is not None:
            self.kf = _field(kf, self.ny, self.nx)
        if kd is not None:
            self.kd = _field(kd, self.ny, self.nx)
        self._push_erosional_parameters()

    # -- stepping ----------------------------------------------------------------------------
    def advance(self, k: int = 1) -> None:
        for _ in range(k):
            t0 = time.perf_counter()
            fs.fastscape_execute_step()
            self.step_times.append(time.perf_counter() - t0)
            self.step += 1

    @property
    def time_years(self) -> float:
        return self.step * self.dt

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

    def erosion_rate(self) -> np.ndarray:
        return self._copy(fs.fastscape_copy_erosion_rate)

    def silt_fraction(self) -> np.ndarray:
        return self._copy(fs.fastscape_copy_f)

    def slope(self) -> np.ndarray:
        return self._copy(fs.fastscape_copy_slope)

    def gauss_seidel_iterations(self) -> int:
        try:
            return int(fs.fastscape_get_gssiterations())
        except Exception:
            return -1

    def land_fraction(self, h: np.ndarray | None = None) -> float:
        h = self.h() if h is None else h
        return float(np.mean(h > self.sea_level))

    # -- export ------------------------------------------------------------------------------
    def settings(self) -> dict:
        return {
            "label": self.label, "nx": self.nx, "ny": self.ny, "dx_m": self.dx, "dt_yr": self.dt, "bc": self.bc,
            "process": asdict(self.process), "marine": asdict(self.marine) if self.marine else None,
            "sea_level_final_m": self.sea_level, "kf": _describe(self.kf), "kd": _describe(self.kd),
            "precip": _describe(self.precip), "uplift_final_m_per_yr": _describe(self.uplift),
            "flow_direction": "single" if self.process.p < -1.5 else f"multiple (p={self.process.p:g})",
            "library": "fastscapelib-fortran 2.8.4 (FastScape API via Python, lem-env)",
        }

    def export(self, out_dir: Path | str, *, extra: dict | None = None, channels: tuple[str, ...] = ("elevation", "drainage_area")) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        h = self.h()
        arrays = {"elevation": h}
        meta_channels = {"elevation": {"file": "elevation.npy", "units": "m", "kind": "elevation"}}
        if "drainage_area" in channels:
            arrays["drainage_area"] = self.drainage_area()
            meta_channels["drainage_area"] = {"file": "drainage_area.npy", "units": "m2", "kind": "drainage_area", "display": "log10"}
        if "basement" in channels:
            arrays["basement"] = self.basement()
            meta_channels["basement"] = {"file": "basement.npy", "units": "m", "kind": "elevation"}
        if "total_erosion" in channels:
            arrays["total_erosion"] = self.total_erosion()
            meta_channels["total_erosion"] = {"file": "total_erosion.npy", "units": "m", "kind": "scalar"}
        if "silt_fraction" in channels and self.marine is not None:
            arrays["silt_fraction"] = self.silt_fraction()
            meta_channels["silt_fraction"] = {"file": "silt_fraction.npy", "units": "1", "kind": "scalar"}
        for name, arr in arrays.items():
            np.save(out / f"{name}.npy", arr.astype(np.float32) if name != "elevation" else arr)
        st = np.array(self.step_times) if self.step_times else np.array([0.0])
        meta = {
            "written_utc": datetime.now(timezone.utc).isoformat(),
            "settings": self.settings(),
            "steps": self.step, "time_yr": self.time_years,
            "channels": meta_channels,
            "grid": {"nx": self.nx, "ny": self.ny, "dx_m": self.dx, "dy_m": self.dx},
            "timing": {"setup_s": self.t_setup, "steps_total_s": float(st.sum()), "step_mean_s": float(st.mean()),
                       "step_first_s": float(st[0]), "step_last_s": float(st[-1])},
            "output": {"z_min": float(h.min()), "z_max": float(h.max()), "z_mean": float(h.mean()),
                       "land_fraction": self.land_fraction(h), "finite": bool(np.isfinite(h).all()),
                       "lake_cells": int((self.lake_depth() > 0).sum())},
            "sea_level_history": self.sea_level_history[-2000:],
        }
        if extra:
            meta.update(extra)
        (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
        return out


def _describe(arr: np.ndarray) -> dict | float:
    if np.all(arr == arr.flat[0]):
        return float(arr.flat[0])
    return {"min": float(arr.min()), "max": float(arr.max()), "mean": float(arr.mean()), "field": True}


@dataclass
class Epoch:
    """Piecewise-constant uplift epoch: ``uplift`` applies from ``t_start`` (inclusive) to ``t_end`` (exclusive)."""
    t_start: float
    t_end: float
    uplift: np.ndarray


def run_schedule(model: FastScapeModel, *, t_end: float, epochs: list[Epoch], sea_level_at=None,
                 log_every_steps: int = 0, on_log=None, on_step=None) -> dict:
    """Advance the model to ``t_end`` (years), switching uplift at epoch boundaries and, when ``sea_level_at(t)`` is
    given, updating the sea level every step. Epoch boundaries are rounded to whole steps."""
    t0 = time.perf_counter()
    n_steps = int(round(t_end / model.dt))
    epochs = sorted(epochs, key=lambda e: e.t_start)
    current = None
    while model.step < n_steps:
        t = model.time_years
        ep = next((e for e in epochs if e.t_start <= t < e.t_end), None)
        if ep is not current:
            model.set_uplift(ep.uplift if ep is not None else 0.0)
            current = ep
        if sea_level_at is not None:
            model.set_sea_level(float(sea_level_at(t)))
        model.advance(1)
        if on_step is not None:
            on_step(model)
        if log_every_steps and model.step % log_every_steps == 0 and on_log is not None:
            on_log(model, time.perf_counter() - t0)
    return {"steps": model.step, "time_yr": model.time_years, "wall_s": time.perf_counter() - t0}
