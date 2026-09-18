"""Parallel execution of model jobs, one FastScape instance per subprocess.

Each job runs in its own interpreter process (``python -m lem_pipeline.runner --job job.json``) with
``OMP_NUM_THREADS=1``. A Fortran ``STOP`` (for example the marine module's "Multi-lithology diffusion not
converging; decrease time step") terminates only that process; the parent records the failure with the tail of the
process output and continues with the remaining jobs. Results are JSON dictionaries written by the child.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from .paths import ROOT


def _resolve(dotted: str):
    mod, _, name = dotted.rpartition(".")
    return getattr(importlib.import_module(mod), name)


def _child_main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--callable", required=True)
    ap.add_argument("--result", required=True)
    a = ap.parse_args(argv)
    kwargs = json.loads(Path(a.job).read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    try:
        result = _resolve(a.callable)(**kwargs)
        payload = {"ok": True, "result": result, "wall_s": time.perf_counter() - t0, "job": kwargs.get("label")}
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "error": repr(exc), "traceback": traceback.format_exc(),
                   "wall_s": time.perf_counter() - t0, "job": kwargs.get("label")}
    Path(a.result).write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return 0 if payload["ok"] else 1


def run_jobs(dotted: str, jobs: list[dict], *, max_workers: int = 8, log=print, record_path: Path | str | None = None,
             python: str | None = None, poll_s: float = 2.0, env: dict | None = None) -> list[dict]:
    """Run ``dotted(**job)`` for every job, at most ``max_workers`` single-core subprocesses at a time."""
    python = python or sys.executable
    root = Path(record_path).parent if record_path else Path("output") / "jobs"
    work = root / "job-logs"
    work.mkdir(parents=True, exist_ok=True)
    child_env = dict(os.environ)
    child_env.setdefault("OMP_NUM_THREADS", "1")
    child_env.setdefault("MKL_NUM_THREADS", "1")
    child_env.setdefault("OPENBLAS_NUM_THREADS", "1")
    src = str(Path(__file__).resolve().parents[1])
    child_env["PYTHONPATH"] = os.pathsep.join((src, str(ROOT), child_env.get("PYTHONPATH", "")))
    if env:
        child_env.update(env)
    labels = [str(j.get("label", f"job{i}")) for i, j in enumerate(jobs)]
    dup = sorted({l for l in labels if labels.count(l) > 1})
    if dup:  # job, result and log files are named by the label; duplicates would overwrite each other (2026-09-09 incident)
        raise ValueError(f"duplicate job labels: {dup}")
    pending = list(enumerate(jobs))
    running: dict[int, tuple[subprocess.Popen, dict, Path, Path, float]] = {}
    results: list[dict] = []
    t0 = time.perf_counter()
    while pending or running:
        while pending and len(running) < max_workers:
            idx, job = pending.pop(0)
            label = str(job.get("label", f"job{idx}"))
            jp, rp, lp = work / f"{label}.job.json", work / f"{label}.result.json", work / f"{label}.log"
            jp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            if rp.exists():
                rp.unlink()
            lf = open(lp, "w", encoding="utf-8")
            proc = subprocess.Popen([python, "-m", "lem_pipeline.runner", "--job", str(jp), "--callable", dotted, "--result", str(rp)],
                                    stdout=lf, stderr=subprocess.STDOUT, env=child_env, cwd=os.getcwd())
            running[idx] = (proc, job, rp, lp, time.perf_counter())
            lf.close()
        done = [i for i, (proc, *_rest) in running.items() if proc.poll() is not None]
        for i in done:
            proc, job, rp, lp, ts = running.pop(i)
            wall = time.perf_counter() - ts
            if rp.exists():
                res = json.loads(rp.read_text(encoding="utf-8"))
            else:
                tail = ""
                try:
                    lines = [l for l in lp.read_text(encoding="utf-8", errors="replace").splitlines() if not l.startswith("Warning:")]
                    tail = "\n".join(lines[-6:])
                except Exception:
                    pass
                res = {"ok": False, "error": f"process exited with code {proc.returncode} without a result", "tail": tail,
                       "wall_s": wall, "job": job.get("label")}
            res.setdefault("wall_s", wall)
            res["exit_code"] = proc.returncode
            results.append(res)
            if log is not None:
                status = "ok" if res["ok"] else "FAILED"
                log(f"[{len(results)}/{len(jobs)}] {res.get('job')}: {status} {res['wall_s']:.0f} s (elapsed {time.perf_counter()-t0:.0f} s)"
                    + ("" if res["ok"] else f" :: {res.get('error')} {res.get('tail','')[-160:]}"), flush=True)
        if running:
            time.sleep(poll_s)
    if record_path is not None:
        Path(record_path).write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return results


if __name__ == "__main__":
    sys.exit(_child_main())
