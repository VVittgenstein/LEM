"""Apply the statistical time-step criterion (lem_pipeline.convergence) to the timestep-test outputs.

For every process set under --root, every step is compared with the finest step; the noise floor comes from the
perturbed finest runs under --perturbed (same process-set names, run directories whose meta.json carries
input.perturb_std_m > 0). Writes docs/work/2026-09-09-pipeline/timestep-criterion.json and prints a table.

Run: PYTHONPATH=src lem-env/python.exe scripts/pipeline_timestep_criterion.py --root output/timestep_test --perturbed output/timestep_test_perturbed
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lem_pipeline.convergence import ABS_FLOOR, NOISE_FACTOR, judge, landscape_stats, noise_floor, stat_differences  # noqa: E402
from lem_pipeline.paths import ROOT  # noqa: E402

OUT = ROOT / "docs" / "work" / "2026-09-09-pipeline"


def load_runs(pset_dir: Path) -> dict[float, dict]:
    runs = {}
    for d in sorted(pset_dir.iterdir()):
        mp = d / "meta.json"
        if not mp.exists():
            continue
        meta = json.loads(mp.read_text(encoding="utf-8"))
        h = np.load(d / "elevation.npy")
        sl = float(meta.get("settings", {}).get("sea_level_final_m", 0.0) or 0.0)
        inp = meta.get("input") or (meta.get("extra") or {}).get("input") or {}
        runs[d.name] = {"dt": float(meta["settings"]["dt_yr"]), "meta": meta, "stats": landscape_stats(h, sl),
                        "perturbed": float(inp.get("perturb_std_m", 0.0) or 0.0) > 0}
    return runs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="output/timestep_test")
    ap.add_argument("--perturbed", default="output/timestep_test_perturbed")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    root, pert = Path(a.root), Path(a.perturbed)
    result = {"created_utc": datetime.now(timezone.utc).isoformat(), "root": str(root), "perturbed": str(pert), "noise_factor": NOISE_FACTOR,
              "abs_floor": ABS_FLOOR, "evidence_state": "本项目自定义判据（假设）", "sets": {}}
    lines = ["| 过程集 | dt (kyr) | 陆地比例差 pp | 陆地高程分位差 m | 坡度分位相对差 | 起伏差 m | 最高点差 m | 海域高程分位差 m | 通过 |", "|---|---:|---:|---:|---:|---:|---:|---:|:--:|"]
    for pset_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        runs = load_runs(pset_dir)
        base = {k: v for k, v in runs.items() if not v["perturbed"]}
        if len(base) < 2:
            continue
        finest_key = min(base, key=lambda k: base[k]["dt"])
        finest = base[finest_key]
        pruns = load_runs(pert / pset_dir.name) if (pert / pset_dir.name).exists() else {}
        pstats = [v["stats"] for v in pruns.values() if v["perturbed"] and abs(v["dt"] - finest["dt"]) < 1e-6]
        floors = noise_floor(finest["stats"], pstats)
        entry = {"finest_dt_yr": finest["dt"], "n_perturbed": len(pstats), "noise_floor": floors, "steps": {}}
        largest_pass = None
        for key, run in sorted(base.items(), key=lambda kv: -kv[1]["dt"]):
            if key == finest_key:
                continue
            diff = stat_differences(run["stats"], finest["stats"])
            ok, detail = judge(diff, floors)
            entry["steps"][key] = {"dt_yr": run["dt"], "pass": ok, "detail": detail, "stats": run["stats"]}
            if ok and (largest_pass is None or run["dt"] > largest_pass):
                largest_pass = run["dt"]
            lines.append(f"| {pset_dir.name} | {run['dt']/1e3:g} | {diff.get('land_fraction_pp', 0):.2f} | {diff.get('land_elev_q_m', 0):.1f} | "
                         f"{diff.get('land_slope_q_rel', 0):.2f} | {diff.get('land_relief_m', 0):.1f} | {diff.get('z_max_m', 0):.1f} | {diff.get('ocean_elev_q_m', 0):.1f} | {'是' if ok else '否'} |")
        entry["finest_stats"] = finest["stats"]
        entry["largest_passing_dt_yr"] = largest_pass
        result["sets"][pset_dir.name] = entry
        fl = ", ".join(f"{k} {v:.2f}" for k, v in floors.items())
        lines.append(f"| {pset_dir.name} | 本底（{len(pstats)} 次扰动，最细 {finest['dt']/1e3:g} kyr） | {fl} | | | | | | |")
        lines.append(f"| {pset_dir.name} | 通过判据的最大步长 | {largest_pass} | | | | | | |")
    OUT.mkdir(parents=True, exist_ok=True)
    name = f"timestep-criterion{('-' + a.label) if a.label else ''}.json"
    (OUT / name).write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\n".join(lines))
    print("written", OUT / name)


if __name__ == "__main__":
    main()
