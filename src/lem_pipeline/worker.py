"""Checkpointed FastScape worker with step-level recovery from the marine solver's abort.

The 2.8.4 marine solver stops the whole process (Fortran ``STOP``) when its silt-sand iteration does not converge
(``Marine.f90`` lines 485 to 488). The orchestrator (``sample.run_sample``) therefore runs the time loop in a child
process that writes a checkpoint after every step; when the child dies before reaching T, the orchestrator restarts
it from the checkpoint with the step halved for the remainder of the failed base step (recovery block), then the base
step is resumed. This applies runtime default 1 (yZz 2026-09-09 11:06) at the level of single steps instead of whole
runs, and keeps the approved marine configuration unchanged.

State that FastScape does not expose for a restart is tracked here: the basement ``b`` (``b + u dt`` each step, then
``min(b, h)``) and the total erosion ``etot`` (``sum(h_before_process - h_after)``); the silt fraction is restored
through ``fastscape_init_f``. ``basement`` and ``total_erosion`` in the export therefore come from this tracking.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from lem_pipeline import driver
from lem_pipeline.driver import FastScapeModel, MarineParams, ProcessParams

MIN_DT = 312.5  # yr; the recovery ladder stops here (assumption)
STALL_RESTARTS = 12  # give up when this many restarts fall within STALL_WINDOW_STEPS base steps (assumption, sink_test seed 22)
STALL_WINDOW_STEPS = 5
CHRONIC_MIN_STEPS = 40  # chronic trip: after this many base steps, more than CHRONIC_RATIO restarts per base step gives up (assumption, scan_f05)
CHRONIC_RATIO = 0.5


def save_inputs(out: Path, *, h0, kf, kd, precip, epochs, sea_series_t, sea_series_z, process: ProcessParams,
                marine: MarineParams | None, dt: float, T: float, nx: int, ny: int, dx_m: float, bc: int = 1111) -> None:
    np.savez(out / "worker_inputs.npz", h0=h0, kf=kf, kd=kd, precip=precip, sea_t=sea_series_t, sea_z=sea_series_z,
             ep_t0=np.array([e.t_start for e in epochs]), ep_t1=np.array([e.t_end for e in epochs]), ep_u=np.stack([e.uplift for e in epochs]))
    meta = {"dt": dt, "T": T, "nx": nx, "ny": ny, "dx_m": dx_m, "bc": bc, "process": process.__dict__,
            "marine": marine.__dict__ if marine is not None else None}
    (out / "worker_inputs.json").write_text(json.dumps(meta, ensure_ascii=False, default=str), encoding="utf-8")


def _ckpt_paths(out: Path) -> dict[str, Path]:
    return {k: out / f"ckpt_{k}.npy" for k in ("h", "f", "b", "etot")} | {"meta": out / "ckpt_meta.json"}


def load_checkpoint(out: Path) -> dict | None:
    p = _ckpt_paths(out)
    if not p["meta"].exists():
        return None
    meta = json.loads(p["meta"].read_text(encoding="utf-8"))
    if not all(p[k].exists() for k in ("h", "f", "b", "etot")):
        return None
    return {"meta": meta, **{k: np.load(p[k]) for k in ("h", "f", "b", "etot")}}


def write_checkpoint(out: Path, meta: dict, h, f, b, etot) -> None:
    p = _ckpt_paths(out)
    for k, arr in (("h", h), ("f", f), ("b", b), ("etot", etot)):
        tmp = p[k].with_suffix(".tmp.npy")
        np.save(tmp, np.asarray(arr, dtype=np.float64))
        tmp.replace(p[k])
    tmp = p["meta"].with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p["meta"])


NUDGES = ("f_smooth3", "h_smooth3", "f_uniform")


def apply_nudge(name: str, h: np.ndarray, f: np.ndarray, b: np.ndarray, sea_level: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Minimal state modification used only when the marine solver aborts repeatedly at the same time regardless of
    the step (state-dependent non-convergence, see marine-solver.md 2.1). Applied to ocean cells only; recorded per sample."""
    from scipy import ndimage

    ocean = h < sea_level
    info = {"nudge": name, "ocean_cells": int(ocean.sum())}
    if name == "f_smooth3":
        fs = ndimage.uniform_filter(f, 3, mode="nearest")
        f2 = np.where(ocean, fs, f)
        info["max_f_change"] = float(np.abs(f2 - f).max())
        return h, f2, b, info
    if name == "h_smooth3":
        hs = ndimage.uniform_filter(h, 3, mode="nearest")
        h2 = np.where(ocean, hs, h)
        info["max_h_change_m"] = float(np.abs(h2 - h).max())
        return h2, f, np.minimum(b, h2), info
    if name == "f_uniform":
        f2 = np.where(ocean, 0.5, 0.0)
        info["max_f_change"] = float(np.abs(f2 - f).max())
        return h, f2, b, info
    raise ValueError(name)


def run_worker(out: Path, *, recovery_dt: float | None = None, recovery_until: float | None = None, log_every: int = 200,
               restarts_count: int = 0, nudge: str | None = None) -> dict:
    """Run from the checkpoint (or from t = 0) to T. ``recovery_dt``/``recovery_until``: use the smaller step until
    the simulated time reaches ``recovery_until``, then return to the base step."""
    inp = np.load(out / "worker_inputs.npz")
    meta_in = json.loads((out / "worker_inputs.json").read_text(encoding="utf-8"))
    dt_base, T, nx, ny, dx = float(meta_in["dt"]), float(meta_in["T"]), int(meta_in["nx"]), int(meta_in["ny"]), float(meta_in["dx_m"])
    process = ProcessParams(**{k: v for k, v in meta_in["process"].items() if k in ProcessParams.__dataclass_fields__})
    marine = MarineParams(**{k: v for k, v in meta_in["marine"].items() if k in MarineParams.__dataclass_fields__}) if meta_in["marine"] else None
    ep_t0, ep_t1, ep_u = inp["ep_t0"], inp["ep_t1"], inp["ep_u"]
    sea_t, sea_z = inp["sea_t"], inp["sea_z"]
    ck = load_checkpoint(out)
    if ck is None:
        # fresh run: FastScape's SetUp initialises the silt fraction Fmix to 0.5 everywhere (FastScape_ctx.f90 line 97);
        # the tool default is kept (no init_f call), the array below only seeds the first checkpoint
        h, f, b, etot = inp["h0"].astype(np.float64), np.full(inp["h0"].shape, 0.5), inp["h0"].astype(np.float64), np.zeros_like(inp["h0"], dtype=np.float64)
        t, step, restarts = 0.0, 0, int(restarts_count)
        sub_steps_total = 0
    else:
        h, f, b, etot = ck["h"], ck["f"], ck["b"], ck["etot"]
        t, step, restarts = float(ck["meta"]["t"]), int(ck["meta"]["step"]), int(restarts_count)
        sub_steps_total = int(ck["meta"].get("sub_steps_total", 0))
    nudges = list((ck["meta"].get("nudges") if ck else None) or [])
    if nudge:
        sl0 = float(np.interp(t, sea_t, sea_z))
        h, f, b, ninfo = apply_nudge(nudge, h, f, b, sl0)
        ninfo["t"] = t
        nudges.append(ninfo)

    def epoch_index(tt: float) -> int:
        i = int(np.searchsorted(ep_t1, tt, side="right"))
        return min(i, len(ep_t0) - 1)

    def sea_level(tt: float) -> float:
        return float(np.interp(tt, sea_t, sea_z))

    dt_now = float(recovery_dt) if recovery_dt else dt_base
    ei = epoch_index(t)
    model = FastScapeModel(nx=nx, ny=ny, dx=dx, dt=dt_now, h0=h, kf=inp["kf"], kd=inp["kd"], process=process, marine=marine,
                           sea_level=sea_level(t), precip=inp["precip"], uplift=ep_u[ei], bc=int(meta_in["bc"]), label=out.name)
    if marine is not None and ck is not None:
        driver.fs.fastscape_init_f(np.asarray(f, dtype=np.float64).ravel().copy())  # restore the checkpointed silt fraction
    t0 = time.perf_counter()
    try:
        while t < T - 1e-6:
            in_recovery = recovery_dt is not None and recovery_until is not None and t < recovery_until - 1e-6
            dt_step = float(recovery_dt) if in_recovery else dt_base
            dt_step = min(dt_step, T - t)
            if abs(dt_step - dt_now) > 1e-9:
                driver.fs.fastscape_set_dt(dt_step)
                model.dt = dt_step
                dt_now = dt_step
            ei_new = epoch_index(t)
            if ei_new != ei:
                ei = ei_new
                model.set_uplift(ep_u[ei])
            if marine is not None:
                model.set_sea_level(sea_level(t))  # evaluated at the step start, as in driver.run_schedule
            h_prev = h
            model.advance(1)
            h = model.h()
            u = ep_u[ei]
            b = np.minimum(b + u * dt_step, h)
            etot = etot + (h_prev + u * dt_step - h)
            f = model.silt_fraction() if marine is not None else f
            t += dt_step
            step += 1
            if in_recovery:
                sub_steps_total += 1
            write_checkpoint(out, {"t": t, "step": step, "dt_last": dt_step, "restarts": restarts, "sub_steps_total": sub_steps_total,
                                   "sea_level": model.sea_level, "wall_s": time.perf_counter() - t0, "nudges": nudges}, h, f, b, etot)
            if log_every and step % log_every == 0:
                print(f"[{out.name}] step {step} t={t/1e6:.3f} Myr dt={dt_step:g} land={model.land_fraction():.3f} sl={model.sea_level:+.1f} {time.perf_counter()-t0:.0f} s", flush=True)
        result = {"done": True, "t": t, "steps": step, "restarts": restarts, "sub_steps_total": sub_steps_total, "wall_s": time.perf_counter() - t0,
                  "step_mean_s": float(np.mean(model.step_times)) if model.step_times else None, "nudges": nudges}
        # final export data
        np.save(out / "final_h.npy", h)
        np.save(out / "final_b.npy", b)
        np.save(out / "final_etot.npy", etot)
        np.save(out / "final_f.npy", f)
        np.save(out / "final_area.npy", model.drainage_area())
        (out / "worker_done.json").write_text(json.dumps(result), encoding="utf-8")
        return result
    finally:
        model.close()


def orchestrate(out: Path, *, python: str | None = None, log=print, max_restarts: int = 200, env: dict | None = None) -> dict:
    """Run the worker as a child process; on an abort (child exits without ``worker_done.json``) restart it from the
    checkpoint with the step halved until the end of the failed base step. Repeated aborts at the same time halve the
    step again down to ``MIN_DT``; an abort at ``MIN_DT`` fails the sample."""
    import os
    import subprocess

    meta_in = json.loads((out / "worker_inputs.json").read_text(encoding="utf-8"))
    dt_base, T = float(meta_in["dt"]), float(meta_in["T"])
    python = python or sys.executable
    child_env = dict(os.environ)
    child_env.setdefault("OMP_NUM_THREADS", "1")
    child_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + child_env.get("PYTHONPATH", "")
    if env:
        child_env.update(env)
    done_p = out / "worker_done.json"
    if done_p.exists():
        done_p.unlink()
    restarts: list[dict] = []
    recovery_dt: float | None = None
    recovery_until: float | None = None
    last_fail_t: float | None = None
    same_t = 0  # consecutive aborts at the same simulated time
    nudge: str | None = None
    logf = open(out / "worker.log", "a", encoding="utf-8")
    try:
        for attempt in range(max_restarts + 1):
            cmd = [python, "-m", "lem_pipeline.worker", "--out", str(out), "--restarts", str(len(restarts))]
            if recovery_dt is not None:
                cmd += ["--recovery-dt", str(recovery_dt), "--recovery-until", str(recovery_until)]
            if nudge:
                cmd += ["--nudge", nudge]
            logf.write(f"attempt {attempt}: {' '.join(cmd[3:])}\n")
            logf.flush()
            proc = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT, env=child_env, cwd=os.getcwd())
            nudge = None
            if done_p.exists():
                res = json.loads(done_p.read_text(encoding="utf-8"))
                res["restarts"] = len(restarts)
                res["restart_log"] = restarts
                return res
            ck = load_checkpoint(out)
            t_fail = float(ck["meta"]["t"]) if ck else 0.0
            # stall trip (assumption): more than STALL_RESTARTS restarts within the last STALL_WINDOW_STEPS base steps
            # means the state keeps failing at nearly every step; give up instead of spending hours on one sample
            recent = [r for r in restarts if t_fail - float(r["t"]) <= STALL_WINDOW_STEPS * dt_base + 1e-6]
            if len(recent) >= STALL_RESTARTS:
                restarts.append({"t": t_fail, "action": "give up (stall)", "recent_restarts": len(recent), "exit_code": proc.returncode})
                return {"done": False, "t": t_fail, "restarts": len(restarts), "restart_log": restarts,
                        "error": f"marine abort stall: {len(recent)} restarts within {STALL_WINDOW_STEPS} base steps", "exit_code": proc.returncode}
            # chronic trip (assumption): after CHRONIC_MIN_STEPS base steps, more than CHRONIC_RATIO restarts per base step
            base_steps_done = t_fail / dt_base
            if base_steps_done >= CHRONIC_MIN_STEPS and len(restarts) > CHRONIC_RATIO * base_steps_done:
                restarts.append({"t": t_fail, "action": "give up (chronic)", "restarts_so_far": len(restarts), "base_steps": base_steps_done, "exit_code": proc.returncode})
                return {"done": False, "t": t_fail, "restarts": len(restarts), "restart_log": restarts,
                        "error": f"marine abort chronic: {len(restarts)} restarts over {base_steps_done:.0f} base steps", "exit_code": proc.returncode}
            in_block = recovery_dt is not None and recovery_until is not None and t_fail < recovery_until - 1e-6
            dt_failed = recovery_dt if in_block else dt_base
            same_t = same_t + 1 if (last_fail_t is not None and abs(t_fail - last_fail_t) < 1e-6) else 0
            # policy (assumption): halve the step twice at the same time; then minimal state nudges; then give up
            action: dict = {"t": t_fail, "dt_failed": dt_failed, "same_t": same_t, "exit_code": proc.returncode}
            if same_t <= 1:
                new_dt = dt_failed / 2.0
                if new_dt < MIN_DT - 1e-9:
                    new_dt = dt_failed
                    same_t = 2  # cannot halve further: fall through to the nudges on the next abort
                recovery_dt = new_dt
                action["recovery_dt"] = recovery_dt
            elif same_t - 2 < len(NUDGES):
                nudge = NUDGES[same_t - 2]
                action["nudge"] = nudge
                action["recovery_dt"] = recovery_dt
            else:
                action["action"] = "give up"
                restarts.append(action)
                return {"done": False, "t": t_fail, "restarts": len(restarts), "restart_log": restarts, "error": "marine abort persists after step halving and state nudges",
                        "exit_code": proc.returncode}
            recovery_until = min((np.floor(t_fail / dt_base + 1e-9) + 1.0) * dt_base, T)  # end of the base step containing t_fail
            if recovery_dt is None:
                recovery_dt = dt_base
            action["recovery_until"] = recovery_until
            restarts.append(action)
            last_fail_t = t_fail
            log(f"[{out.name}] abort at t={t_fail:.0f} (dt {dt_failed:g}); restart with dt {recovery_dt:g}{(' nudge ' + nudge) if nudge else ''} until t={recovery_until:.0f}")
        return {"done": False, "restarts": len(restarts), "restart_log": restarts, "error": "too many restarts"}
    finally:
        logf.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--recovery-dt", type=float, default=None)
    ap.add_argument("--recovery-until", type=float, default=None)
    ap.add_argument("--log-every", type=int, default=200)
    ap.add_argument("--restarts", type=int, default=0, help="number of restarts so far (set by the orchestrator, recorded in checkpoints)")
    ap.add_argument("--nudge", default=None, choices=[None, *NUDGES], help="minimal state modification applied once after loading the checkpoint")
    a = ap.parse_args()
    run_worker(Path(a.out), recovery_dt=a.recovery_dt, recovery_until=a.recovery_until, log_every=a.log_every, restarts_count=a.restarts, nudge=a.nudge)


if __name__ == "__main__":
    main()
