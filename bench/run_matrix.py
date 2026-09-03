"""L1 benchmark driver: interleaved rounds, one subprocess per run, fixed affinity and thread counts.

Round 0 is a warm-up round with few steps. Rounds 1..R are timed. Within a round the four
configurations alternate, so repeats of one configuration never run back to back.
Runs whose result file already exists with status ok are skipped (resumable).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
CONFIGS = [("landlab", "DFR"), ("landlab", "LMB"), ("landlab", "PFFR"), ("fastscape", "FS")]
KS = [1e-5, 1e-4, 1e-6]
GROUPS = ["elev", "elev_da"]
PROFILING = [(1e-5, "elev", "fastscape", "FS_PIECEWISE")]


def cell_id(K, group, config):
    return f"K{K:.0e}_{group}_{config}"


def precheck(threshold, max_wait_s):
    waited = 0.0
    while True:
        samples = [psutil.cpu_percent(interval=1) for _ in range(3)]
        mean = sum(samples) / len(samples)
        if mean <= threshold or waited >= max_wait_s:
            return {"cpu_percent_samples": samples, "waited_s": waited, "over_threshold": mean > threshold,
                    "mem_available_MB": psutil.virtual_memory().available / 2**20}
        time.sleep(10)
        waited += 13


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--steps", type=int, required=True)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--warmup-steps", type=int, default=5)
    p.add_argument("--affinity", default="4")
    p.add_argument("--results-dir", default=str(HERE / "results" / "L1"))
    p.add_argument("--cpu-threshold", type=float, default=15.0)
    p.add_argument("--max-wait", type=float, default=300.0)
    p.add_argument("--configs", default=None, help="comma list to restrict configs, e.g. DFR,FS")
    p.add_argument("--ks", default=None, help="comma list to restrict K values")
    p.add_argument("--no-profiling", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--nx", type=int, default=500)
    p.add_argument("--ny", type=int, default=500)
    a = p.parse_args()

    configs = CONFIGS if not a.configs else [c for c in CONFIGS if c[1] in a.configs.split(",")]
    ks = KS if not a.ks else [float(k) for k in a.ks.split(",")]
    cells = [(K, g, tool, cfg) for K in ks for g in GROUPS for (tool, cfg) in configs]
    results = Path(a.results_dir)
    runs_dir = results / "runs"
    exp_dir = results / "exports"
    runs_dir.mkdir(parents=True, exist_ok=True)
    manifest = results / "manifest.jsonl"

    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "NUMBA_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "BENCH_AFFINITY": a.affinity, "PYTHONUNBUFFERED": "1"})

    plan = []
    for r in range(0, a.rounds + 1):
        steps = a.warmup_steps if r == 0 else a.steps
        rcells = list(cells)
        if r > 0 and not a.no_profiling:
            rcells += [c for c in PROFILING if c[0] in ks]
        for (K, g, tool, cfg) in rcells:
            plan.append((r, steps, K, g, tool, cfg))
    print(f"plan: {len(plan)} runs ({len(cells)} cells, rounds 0..{a.rounds}), affinity {a.affinity}, grid {a.nx}x{a.ny}")
    if a.dry_run:
        for item in plan:
            print(item)
        return

    for (r, steps, K, g, tool, cfg) in plan:
        rid = f"r{r}_{cell_id(K, g, cfg)}"
        out = runs_dir / f"{rid}.json"
        if out.exists():
            try:
                if json.loads(out.read_text(encoding="utf-8")).get("status") == "ok":
                    print(f"skip {rid} (exists)")
                    continue
            except Exception:  # noqa: BLE001
                pass
        pre = precheck(a.cpu_threshold, a.max_wait)
        cmd = [sys.executable, str(HERE / "run_cell.py"), "--tool", tool, "--config", cfg, "--group", g,
               "--K", repr(K), "--steps", str(steps), "--out", str(out), "--export-dir", str(exp_dir),
               "--nx", str(a.nx), "--ny", str(a.ny)]
        t0 = time.perf_counter()
        started = datetime.now(timezone.utc).isoformat()
        cp = subprocess.run(cmd, env=env, capture_output=True, text=True)
        wall = time.perf_counter() - t0
        rec = {"run_id": rid, "round": r, "steps": steps, "K": K, "group": g, "tool": tool, "config": cfg,
               "started_utc": started, "wall_s": wall, "returncode": cp.returncode, "precheck": pre}
        if cp.returncode != 0:
            rec["stderr_tail"] = cp.stderr[-2000:]
            out.write_text(json.dumps({"run_id": rid, "status": "error", "returncode": cp.returncode,
                                       "stderr_tail": cp.stderr[-4000:], "cmd": cmd}, indent=1), encoding="utf-8")
            last = cp.stderr.strip().splitlines()[-1] if cp.stderr.strip() else ""
            print(f"ERROR {rid} rc={cp.returncode}: {last}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] " + cp.stdout.strip().splitlines()[-1])
        with open(manifest, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    print("matrix finished")


if __name__ == "__main__":
    main()
