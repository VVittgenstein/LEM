"""Summarize an abort/recovery scan directory (run_sample jobs with max_steps) as a markdown table.

Run: PYTHONPATH=experiments lem-env/python.exe tests/experiments/lem_pipeline/experiments/pipeline_scan_summary.py --root output/dev/scan_f05 --configs nosink,sink --out docs/work/2026-09-09-pipeline/scan-f05.md
"""
from __future__ import annotations

from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('.', 'experiments'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)


import argparse
import json
from pathlib import Path

import numpy as np


def load(root: Path, cfg: str) -> list[dict]:
    rows = []
    for d in sorted(p for p in (root / cfg).iterdir() if p.is_dir() and p.name.startswith("sample")):
        seed = int(d.name.replace("sample", ""))
        row = {"cfg": cfg, "seed": seed}
        c = json.loads((d / "config.json").read_text(encoding="utf-8")) if (d / "config.json").exists() else {}
        row["case"] = c.get("case")
        row["regime"] = (c.get("periphery") or {}).get("regime")
        row["kmult"] = max((z["k_multiplier"] for z in (c.get("parameters") or {}).get("lithology_zones", [])), default=None)
        wl = d / "worker.log"
        row["restarts"] = sum(1 for line in wl.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("attempt ")) - 1 if wl.exists() else None
        if (d / "check.json").exists():
            ch = json.loads((d / "check.json").read_text(encoding="utf-8"))
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            row.update({"done": True, "accepted": ch["accepted"], "land": ch["land_fraction"], "band_land": ch["land_in_ocean_band"], "reasons": "; ".join(ch["reasons"]),
                        "sub_steps": (meta.get("loop") or {}).get("sub_steps_total"), "nudges": len((meta.get("loop") or {}).get("nudges") or [])})
        elif (d / "run-failed.json").exists():
            fr = json.loads((d / "run-failed.json").read_text(encoding="utf-8"))
            row.update({"done": False, "accepted": False, "reasons": fr.get("error"), "t_reached": fr.get("t"), "sub_steps": None})
        else:
            row.update({"done": None, "accepted": None, "reasons": "running or missing"})
        rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--configs", default="nosink,sink")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    root = Path(a.root)
    cfgs = a.configs.split(",")
    lines = [f"# {a.title or root.name}", "", f"来源：`{root}`（各样本的 `config.json`、`worker.log`、`check.json` 或 `run-failed.json`）。", ""]
    allrows = {}
    for cfg in cfgs:
        rows = load(root, cfg)
        allrows[cfg] = rows
        lines += [f"## 配置 {cfg}", "", "| 种子 | 案例 | 周边 | K 倍数最大 | 重启 | 细步 | 状态 | 陆地比例 | 海域带内有陆地 | 通过 | 原因 |", "|---:|---|---|---:|---:|---:|---|---:|:--:|:--:|---|"]
        for r in rows:
            st = "完成" if r.get("done") else ("停滞放弃" if r.get("done") is False else "运行中")
            lines.append(f"| {r['seed']} | {r.get('case') or ''} | {r.get('regime') or ''} | {r.get('kmult') if r.get('kmult') is None else round(r['kmult'])} | {r.get('restarts')} | "
                         f"{r.get('sub_steps') if r.get('sub_steps') is not None else ''} | {st} | {'' if r.get('land') is None else f'{r['land']:.3f}'} | "
                         f"{'' if r.get('band_land') is None else ('是' if r['band_land'] else '否')} | {'是' if r.get('accepted') else '否'} | {r.get('reasons') or ''} |")
        done = [r for r in rows if r.get("done")]
        rest = [r["restarts"] for r in rows if r.get("restarts") is not None]
        lines += ["", f"- 完成 {len(done)} / {len(rows)}；停滞放弃 {sum(1 for r in rows if r.get('done') is False)}；通过里程碑 1 规则 {sum(1 for r in done if r.get('accepted'))}；"
                      f"海域带内有陆地 {sum(1 for r in done if r.get('band_land'))}；占据率带外 {sum(1 for r in done if 'occupancy' in (r.get('reasons') or ''))}。",
                  f"- 重启次数：中位 {np.median(rest):.0f}，最大 {max(rest)}，合计 {sum(rest)}；无重启的样本 {sum(1 for x in rest if x == 0)}。" if rest else "", ""]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(l for l in lines if l.startswith("- ") or l.startswith("## ")))


if __name__ == "__main__":
    main()
