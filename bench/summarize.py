"""Aggregate L1 benchmark results into Markdown tables."""
import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(results_dir):
    runs = []
    for p in sorted(Path(results_dir, "runs").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("status") != "ok":
            continue
        rid = d["run_id"]
        d["round"] = int(rid.split("_")[0][1:])
        d["cell"] = rid.split("_", 1)[1]
        runs.append(d)
    return runs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", default=str(HERE / "results" / "L1"))
    p.add_argument("--include-warmup", action="store_true")
    a = p.parse_args()
    runs = load(a.results_dir)
    if not a.include_warmup:
        runs = [r for r in runs if r["round"] > 0]
    by_cell = defaultdict(list)
    for r in runs:
        by_cell[r["cell"]].append(r)

    print("## 每单元汇总（各轮中位数；每步耗时排除前 5 步）\n")
    print("| 单元 | 轮数 | 步数 | 每步 ms 中位 | 每步 ms 轮间范围 | 首步 ms | 建立 s | 导入 s | 峰值内存 MB | 导出 ms | 末态洼地格数 | z 范围 | A 最大 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    rows = {}
    for cell in sorted(by_cell):
        rs = by_cell[cell]
        ms = [r["stats"]["steady_mean_s"] * 1e3 for r in rs]
        first = st.median(r["stats"]["first_step_s"] * 1e3 for r in rs)
        setup = st.median(r["t_setup_s"] for r in rs)
        imp = st.median(r["t_import_s"] for r in rs)
        mem = st.median(r["peak_wset_MB"] for r in rs)
        exp = st.median(sum(r["export_s"].values()) * 1e3 for r in rs)
        flooded = st.median(r["output"]["flooded_nodes_final"] for r in rs)
        z = rs[-1]["output"]
        rows[cell] = {"ms": st.median(ms), "mem": mem, "exp": exp}
        print(f"| {cell} | {len(rs)} | {rs[-1]['stats']['steps']} | {st.median(ms):.1f} | {min(ms):.1f} 至 {max(ms):.1f} "
              f"| {first:.1f} | {setup:.2f} | {imp:.2f} | {mem:.0f} | {exp:.1f} | {flooded:.0f} "
              f"| [{z['z_min']:.1f}, {z['z_max']:.1f}] | {z['A_max']:.3g} |")

    print("\n## 分部分每步耗时（ms，各轮中位数）\n")
    comps = ["uplift", "route", "route_fill", "accum", "spl", "diff", "total"]
    print("| 单元 | " + " | ".join(comps) + " |")
    print("|---|" + "---|" * len(comps))
    for cell in sorted(by_cell):
        rs = by_cell[cell]
        vals = []
        for c in comps:
            xs = [r["stats"]["components_steady_mean_s"].get(c) for r in rs]
            xs = [x * 1e3 for x in xs if x is not None]
            vals.append(f"{st.median(xs):.2f}" if xs else "")
        print(f"| {cell} | " + " | ".join(vals) + " |")

    print("\n## 比值\n")
    print("| 比较 | 值 |")
    print("|---|---|")
    for cell, v in sorted(rows.items()):
        if cell.endswith("_FS") or cell.endswith("_FS_PIECEWISE"):
            continue
        base = cell.rsplit("_", 1)[0] + "_FS"
        if base in rows:
            print(f"| {cell} ÷ {base}，每步耗时 | {v['ms'] / rows[base]['ms']:.2f} |")
    for cell, v in sorted(rows.items()):
        if "K1e-05" in cell:
            continue
        ref = cell.replace("K1e-04", "K1e-05").replace("K1e-06", "K1e-05")
        if ref in rows:
            print(f"| {cell} ÷ {ref}，每步耗时，K 对照 | {v['ms'] / rows[ref]['ms']:.2f} |")
    for cell, v in sorted(rows.items()):
        if "_elev_da_" in cell:
            ref = cell.replace("_elev_da_", "_elev_")
            if ref in rows:
                print(f"| {cell} ÷ {ref}，每步耗时，导出对照 | {v['ms'] / rows[ref]['ms']:.2f} |")


if __name__ == "__main__":
    main()
