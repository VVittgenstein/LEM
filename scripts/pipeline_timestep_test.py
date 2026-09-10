"""Workstream D: run and analyse the timestep convergence matrix.

Examples (lem-env interpreter, from the repository root):
  PYTHONPATH=src lem-env/python.exe scripts/pipeline_timestep_test.py run --root output/timestep_test --workers 8 --t-end 4e6
  PYTHONPATH=src lem-env/python.exe scripts/pipeline_timestep_test.py analyze --root output/timestep_test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lem_pipeline import timestep_test as tt  # noqa: E402
from lem_pipeline.runner import run_jobs  # noqa: E402

DEFAULT_LADDER = [50e3, 25e3, 10e3, 5e3, 2.5e3]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "analyze", "jobs"])
    ap.add_argument("--root", default="output/timestep_test")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--t-end", type=float, default=4e6)
    ap.add_argument("--nx", type=int, default=500)
    ap.add_argument("--ny", type=int, default=500)
    ap.add_argument("--sets", default="uplift_spl,plus_diffusion,plus_marine,plus_sealevel")
    ap.add_argument("--ladder", default=",".join(str(int(x)) for x in DEFAULT_LADDER))
    ap.add_argument("--extra-finest", type=float, default=1250.0, help="additional finest step for the last set only (0 = none)")
    ap.add_argument("--deep-depth", type=float, default=3000.0, help="floor depth (m) of the deep periphery segment of the reference input")
    a = ap.parse_args()
    root = Path(a.root)
    sets = [s for s in a.sets.split(",") if s]
    ladder = [float(x) for x in a.ladder.split(",") if x]
    dts = {s: list(ladder) for s in sets}
    if a.extra_finest and sets:
        dts[sets[-1]] = list(ladder) + [a.extra_finest]
    if a.mode in ("run", "jobs"):
        jobs = tt.make_jobs(root, t_end=a.t_end, dts=dts, nx=a.nx, ny=a.ny, deep_depth=a.deep_depth)
        # run the expensive fine steps first so the tail of the batch is short
        jobs.sort(key=lambda j: j["dt"])
        if a.mode == "jobs":
            print(json.dumps(jobs, indent=1))
            return
        root.mkdir(parents=True, exist_ok=True)
        results = run_jobs("lem_pipeline.timestep_test.run_case", jobs, max_workers=a.workers, record_path=root / "jobs-record.json")
        failed = [r for r in results if not r["ok"]]
        print(f"done: {len(results) - len(failed)} ok, {len(failed)} failed")
        for r in failed:
            print("FAILED", r["job"], r["error"])
    summary = tt.analyze(root)
    md = tt.summary_markdown(summary)
    (root / "summary.md").write_text(md + "\n", encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
