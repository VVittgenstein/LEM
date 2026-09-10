"""Summarize a generated batch (output of scripts/pipeline_generate.py) as a markdown table plus aggregate facts.

Run: PYTHONPATH=src lem-env/python.exe scripts/pipeline_batch_report.py --batch output/batch-test --out docs/work/2026-09-09-pipeline/batch-test.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    root = Path(a.batch)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    rows = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("sample")):
        cfg_p, chk_p, fail_p = d / "config.json", d / "check.json", d / "run-failed.json"
        if not cfg_p.exists():
            continue
        cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
        row = {"seed": cfg.get("seed"), "case": cfg.get("case"), "T_Myr": (cfg.get("T_yr") or 0) / 1e6, "dt": summary.get("dt_used", {}).get(str(cfg.get("seed"))),
               "occ0": (cfg.get("landmask") or {}).get("occupancy_achieved"), "regime": (cfg.get("periphery") or {}).get("regime"),
               "kmult": max((z["k_multiplier"] for z in (cfg.get("parameters") or {}).get("lithology_zones", [])), default=None),
               "discarded": cfg.get("discarded", False), "reason": cfg.get("reason")}
        if chk_p.exists():
            chk = json.loads(chk_p.read_text(encoding="utf-8"))
            row.update({"land_T": chk.get("land_fraction"), "accepted": chk.get("accepted"), "reasons": "; ".join(chk.get("reasons") or []),
                        "spl": chk.get("spl_number_max"), "components": chk.get("land_components_4"), "closed_km2": chk.get("closed_sub_sea_level_area_km2")})
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
            loop = meta.get("loop") or {}
            row.update({"steps": loop.get("steps"), "restarts": loop.get("restarts"), "sub_steps": loop.get("sub_steps_total"), "wall_s": loop.get("wall_s"),
                        "sl_T": (meta.get("settings") or {}).get("sea_level_final_m")})
        elif fail_p.exists():
            fr = json.loads(fail_p.read_text(encoding="utf-8"))
            row.update({"accepted": False, "reasons": f"run failed: {fr.get('error')}", "restarts": fr.get("restarts")})
        rows.append(row)
    lines = [f"# {a.title or root.name}", "", f"来源：`{root}`（`summary.json` 与各样本的 `config.json`、`check.json`、`meta.json`）。", "",
             "| 种子 | 案例 | T (Myr) | dt (yr) | 初始占据率 | 周边 | K 倍数最大 | 步数 | 重启 | 细步数 | 用时 s | 海平面(T) m | 陆地比例(T) | 分量 | 通过 | 原因 |",
             "|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|---|"]
    for r in rows:
        f = lambda v, fmt: (fmt.format(v) if isinstance(v, (int, float)) and v is not None else ("" if v is None else str(v)))
        lines.append(f"| {r['seed']} | {r['case']} | {f(r['T_Myr'], '{:.1f}')} | {f(r.get('dt'), '{:.0f}')} | {f(r.get('occ0'), '{:.3f}')} | {r.get('regime') or ''} | {f(r.get('kmult'), '{:.0f}')} | "
                     f"{f(r.get('steps'), '{}')} | {f(r.get('restarts'), '{}')} | {f(r.get('sub_steps'), '{}')} | {f(r.get('wall_s'), '{:.0f}')} | {f(r.get('sl_T'), '{:.1f}')} | "
                     f"{f(r.get('land_T'), '{:.3f}')} | {f(r.get('components'), '{}')} | {'是' if r.get('accepted') else '否'} | {r.get('reasons') or r.get('reason') or ''} |")
    n = len(rows)
    acc = sum(1 for r in rows if r.get("accepted"))
    ran = sum(1 for r in rows if r.get("steps"))
    walls = [r["wall_s"] for r in rows if r.get("wall_s")]
    restarts = [r["restarts"] for r in rows if r.get("restarts") is not None]
    lines += ["", "## 汇总（事实）", "",
              f"- 样本 {n} 个：完成运行 {ran} 个，通过里程碑 1 检查 {acc} 个；形状阶段舍弃 {sum(1 for r in rows if r.get('discarded'))} 个；运行失败 {sum(1 for r in rows if str(r.get('reasons', '')).startswith('run failed'))} 个。",
              f"- 用时：单样本 {min(walls):.0f} 至 {max(walls):.0f} s（中位 {np.median(walls):.0f} s）；超过 180 s 的样本 {sum(1 for w in walls if w > 180)} 个。" if walls else "- 用时：无完成样本。",
              f"- 步内恢复：有重启的样本 {sum(1 for x in restarts if x)} 个，重启次数合计 {sum(restarts)}。" if restarts else "",
              f"- 舍弃原因：{dict((k, sum(1 for r in rows if k in str(r.get('reasons')))) for k in ('ocean band', 'occupancy band', 'run failed', 'no shape'))}。",
              f"- 批次设置：起始步长 {summary.get('dt_start_yr')} yr，阶梯 {summary.get('ladder_yr')}，占据率带 {summary.get('band')}，固定 T {summary.get('T_fixed_yr')}，开始 {summary.get('started_utc')}，结束 {summary.get('finished_utc')}。"]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(l for l in lines if l is not None) + "\n", encoding="utf-8")
    print("\n".join(lines[-6:]))


if __name__ == "__main__":
    main()
