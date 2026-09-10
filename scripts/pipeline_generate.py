"""Generate a batch of samples with the pipeline (one process per sample, up to --workers in parallel).

Time-step rule (runtime default 1, yZz 2026-09-09 11:06): every sample starts at --dt; when the FastScape marine solver
aborts ("Multi-lithology diffusion not convergning"), the same sample (same seed, same drawn configuration) is rerun
with the next smaller step of --ladder until it completes or the ladder is exhausted. The step used and the attempts
are recorded per sample in summary.json.

Examples (lem-env interpreter, repository root):
  PYTHONPATH=src lem-env/python.exe scripts/pipeline_generate.py --n 8 --out output/batch-test --workers 8 --dt 10000
  PYTHONPATH=src lem-env/python.exe scripts/pipeline_generate.py --n 64 --seed0 1000 --out output/batch-examples --workers 8
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lem_pipeline.runner import run_jobs  # noqa: E402

ABORT_TEXT = "not convergning"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--seed0", type=int, default=1)
    ap.add_argument("--out", default="output/batch-test")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dt", type=float, default=10e3)
    ap.add_argument("--ladder", default="10000,5000,2500,1250", help="fallback steps (yr) tried in order after an abort at --dt")
    ap.add_argument("--T", type=float, default=None, help="fixed simulated duration in years (default: sample 5 to 30 Myr)")
    ap.add_argument("--case", default=None, choices=[None, "submerged", "emergence"])
    ap.add_argument("--band", default="0.5,0.6")
    ap.add_argument("--calibration", default=None)
    ap.add_argument("--max-steps", type=int, default=None, help="truncate every run (diagnostics only)")
    ap.add_argument("--sink-band", default=None, help="depth (m) of the outer ocean band used as a sediment sink, or 'none'; default: sample.SINK_BAND_M")
    a = ap.parse_args()
    root = Path(a.out)
    root.mkdir(parents=True, exist_ok=True)
    band = [float(x) for x in a.band.split(",")]
    ladder = [float(x) for x in a.ladder.split(",")]
    ladder = [d for d in ladder if d < a.dt]
    overrides = {}
    if a.sink_band is not None:
        overrides["sink_band_m"] = None if a.sink_band.lower() == "none" else float(a.sink_band)

    def job(seed: int, dt: float) -> dict:
        return dict(label=f"sample{seed}_dt{int(dt)}", seed=seed, out_dir=str(root / f"sample{seed:05d}"), T=a.T, dt=dt, occupancy_band=band,
                    calibration=a.calibration, case=a.case, max_steps=a.max_steps, overrides=overrides)

    t0 = datetime.now(timezone.utc)
    pending = {seed: a.dt for seed in range(a.seed0, a.seed0 + a.n)}
    attempts: dict[int, list] = {seed: [] for seed in pending}
    final: dict[int, dict] = {}
    round_no = 0
    while pending:
        round_no += 1
        jobs = [job(seed, dt) for seed, dt in pending.items()]
        results = run_jobs("lem_pipeline.sample.run_sample", jobs, max_workers=a.workers, record_path=root / f"jobs-record-round{round_no}.json")
        by_seed = {}
        for r in results:
            seed = int(r["job"].split("_dt")[0].replace("sample", ""))
            by_seed[seed] = r
        next_pending = {}
        for seed, r in by_seed.items():
            dt = pending[seed]
            # an abort now surfaces either as a dead job process (legacy path) or as a job result with stage "run"
            # (the checkpointed worker exhausted its recovery ladder); both fall back to the next coarser-to-finer step
            res_ = r.get("result") or {}
            stalled = r["ok"] and res_.get("stage") == "run" and "stall" in str(res_.get("reason") or "")
            aborted = (not stalled) and (((not r["ok"]) and ABORT_TEXT in (r.get("tail") or "")) or (r["ok"] and res_.get("stage") == "run"))
            attempts[seed].append({"dt_yr": dt, "ok": bool(r["ok"]), "marine_abort": aborted, "error": r.get("error")})
            smaller = [d for d in ladder if d < dt]
            if aborted and smaller:
                next_pending[seed] = smaller[0]
                shutil.rmtree(root / f"sample{seed:05d}", ignore_errors=True)
            else:
                final[seed] = r
        pending = next_pending
    ok = {s: r for s, r in final.items() if r["ok"]}
    accepted = {s: r for s, r in ok.items() if r["result"].get("accepted")}
    summary = {"started_utc": t0.isoformat(), "finished_utc": datetime.now(timezone.utc).isoformat(), "n": a.n, "dt_start_yr": a.dt, "ladder_yr": ladder,
               "band": band, "T_fixed_yr": a.T, "case": a.case, "max_steps": a.max_steps, "overrides": overrides,
               "ran": len(ok), "failed_process": len(final) - len(ok), "accepted": len(accepted),
               "dt_used": {str(s): attempts[s][-1]["dt_yr"] for s in final}, "attempts": {str(s): attempts[s] for s in final},
               "samples_needing_fallback": sorted(s for s in final if len(attempts[s]) > 1),
               "discard_reasons": {str(s): (r["result"].get("reasons") or r["result"].get("reason")) for s, r in ok.items() if not r["result"].get("accepted")},
               "wall_s": {str(s): r["result"].get("wall_s") for s, r in ok.items()}, "steps": {str(s): r["result"].get("steps") for s, r in ok.items()},
               "T_yr": {str(s): r["result"].get("T_yr") for s, r in ok.items()}, "case_by_seed": {str(s): r["result"].get("case") for s, r in ok.items()},
               "spl_number_max": {str(s): r["result"].get("spl_number_max") for s, r in ok.items()},
               "failures": [{"seed": s, "error": r.get("error"), "tail": r.get("tail")} for s, r in final.items() if not r["ok"]]}
    (root / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("n", "ran", "failed_process", "accepted", "samples_needing_fallback", "dt_used", "discard_reasons")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
