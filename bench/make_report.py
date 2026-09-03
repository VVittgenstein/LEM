"""Build the self-contained HTML benchmark report for the L1 stage.

Reads bench/results/L1/runs/*.json, manifest.jsonl, exports/*.npy, results/_smoke and
results/env_check.json; writes bench/results/L1/benchmark_report.html (no external assets).
"""
import glob
import json
import statistics as st
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RES = HERE / "results" / "L1"
OUT = RES / "benchmark_report.html"

CONFIGS = [
    ("FS", "fastscape · execute_step", "fastscapelib-fortran 2.8.4，FastScape API 直接调用"),
    ("PFFR", "Landlab · PriorityFloodFlowRouter", "richdem 优先洪泛填洼 + D8"),
    ("DFR", "Landlab · DepressionFinderAndRouter", "FlowAccumulator(D8) + 洼地识别改道"),
    ("LMB", "Landlab · LakeMapperBarnes", "FlowAccumulator(D8) + 纯 Python 优先洪泛填洼"),
]
KS = ["1e-06", "1e-05", "1e-04"]
K_LABEL = {"1e-06": "K = 1e-6", "1e-05": "K = 1e-5", "1e-04": "K = 1e-4"}
COMPS = [("route", "汇流与洼地处理"), ("spl", "河道侵蚀"), ("diff", "坡面扩散"), ("accum", "累积"), ("uplift", "抬升")]


def load_runs():
    runs = []
    for p in sorted((RES / "runs").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("status") != "ok":
            continue
        d["round"] = int(d["run_id"].split("_")[0][1:])
        d["cell"] = d["run_id"].split("_", 1)[1]
        runs.append(d)
    return runs


def med(xs):
    return float(st.median(xs))


def local_minima(z):
    c = z[1:-1, 1:-1]
    m = np.ones_like(c, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            m &= c < z[1 + dy:z.shape[0] - 1 + dy, 1 + dx:z.shape[1] - 1 + dx]
    return int(m.sum())


def main():
    runs = [r for r in load_runs() if r["round"] > 0]
    by = defaultdict(list)
    for r in runs:
        by[r["cell"]].append(r)

    cells = {}
    for cell, rs in by.items():
        ms = [r["stats"]["steady_mean_s"] * 1e3 for r in rs]
        comps = {}
        for k in ["uplift", "route", "route_fill", "accum", "spl", "diff", "total"]:
            xs = [r["stats"]["components_steady_mean_s"].get(k) for r in rs]
            xs = [x * 1e3 for x in xs if x is not None]
            if xs:
                comps[k] = med(xs)
        o = rs[-1]["output"]
        cells[cell] = {
            "rounds": len(rs), "steps": rs[-1]["stats"]["steps"],
            "ms": med(ms), "ms_min": min(ms), "ms_max": max(ms),
            "first_ms": med([r["stats"]["first_step_s"] * 1e3 for r in rs]),
            "setup_s": med([r["t_setup_s"] for r in rs]), "import_s": med([r["t_import_s"] for r in rs]),
            "mem_mb": med([r["peak_wset_MB"] for r in rs]),
            "export_ms": med([sum(r["export_s"].values()) * 1e3 for r in rs]),
            "flooded": int(med([r["output"]["flooded_nodes_final"] for r in rs])),
            "z_min": o["z_min"], "z_max": o["z_max"], "A_max": o["A_max"], "comps": comps,
        }

    # per-step series, K=1e-5, elev group: median across rounds per step
    series = {}
    for cfg, _, _ in CONFIGS:
        rs = by[f"K1e-05_elev_{cfg}"]
        n = len(rs[0]["per_step"]["total"])
        series[cfg] = [med([r["per_step"]["total"][i] for r in rs]) * 1e3 for i in range(n)]

    # fastscape component split from piecewise runs
    fs_pw = cells["K1e-05_elev_FS_PIECEWISE"]["comps"]

    # local minima from exports (round 1)
    z0 = np.random.RandomState(1234).rand(500, 500)
    minima = {"initial": local_minima(z0)}
    for K in KS:
        for cfg, _, _ in CONFIGS:
            z = np.load(RES / "exports" / f"r1_K{K}_elev_{cfg}_elev.npy")
            minima[f"{K}_{cfg}"] = local_minima(z)

    # smoke (60x60) for per-node scaling
    smoke = {}
    for cfg, _, _ in CONFIGS:
        p = HERE / "results" / "_smoke" / f"r0_{cfg}.json"
        if p.exists():
            smoke[cfg] = json.loads(p.read_text(encoding="utf-8"))["stats"]["steady_mean_s"] * 1e3

    # manifest: wall time split
    man = [json.loads(l) for l in (RES / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    wall = defaultdict(float)
    nrun = defaultdict(int)
    for r in man:
        wall[r["config"]] += r["wall_s"]
        nrun[r["config"]] += 1
    total_wall = sum(r["wall_s"] for r in man)
    max_cpu = max(max(r["precheck"]["cpu_percent_samples"]) for r in man)
    min_mem = min(r["precheck"]["mem_available_MB"] for r in man) / 1024

    env = json.loads((HERE / "results" / "env_check.json").read_text(encoding="utf-8"))
    versions = {k: v.get("version") for k, v in env["imports"].items() if v["ok"]}

    base = cells["K1e-05_elev_FS"]["ms"]
    data = {
        "configs": [{"id": c, "name": n, "desc": d} for c, n, d in CONFIGS],
        "ks": KS, "kLabel": K_LABEL,
        "cells": cells, "series": series, "fsSplit": fs_pw, "minima": minima,
        "comps": COMPS,
    }

    # ---------- HTML tables (twins) ----------
    def tr(cols, th=False):
        tag = "th" if th else "td"
        return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cols) + "</tr>"

    t_main = ["<table><thead>" + tr(["配置", "K", "组", "轮数", "每步 ms 中位", "轮间范围", "首步 ms", "峰值内存 MB", "导出 ms", "第 50 步淹没格数", "z 范围 m", "A 最大 m²"], True) + "</thead><tbody>"]
    for cfg, name, _ in CONFIGS:
        for K in KS:
            for g, gl in [("elev", "高程"), ("elev_da", "高程+汇水面积")]:
                c = cells[f"K{K}_{g}_{cfg}"]
                t_main.append(tr([name, K_LABEL[K][4:], gl, c["rounds"], f"{c['ms']:,.0f}", f"{c['ms_min']:,.0f} 至 {c['ms_max']:,.0f}", f"{c['first_ms']:,.0f}", f"{c['mem_mb']:.0f}", f"{c['export_ms']:.1f}", f"{c['flooded']:,}" if cfg != "LMB" else "未记录", f"[{c['z_min']:.1f}, {c['z_max']:.1f}]", f"{c['A_max']:.3g}"]))
    t_main.append("</tbody></table>")

    t_comp = ["<table><thead>" + tr(["配置"] + [n for _, n in COMPS] + ["合计"], True) + "</thead><tbody>"]
    for cfg, name, _ in CONFIGS:
        comps = fs_pw if cfg == "FS" else cells[f"K1e-05_elev_{cfg}"]["comps"]
        vals = [comps.get(k) for k, _ in COMPS]
        t_comp.append(tr([name] + [f"{v:,.2f}" if v is not None else "无此环节" for v in vals] + [f"{comps['total']:,.1f}"]))
    t_comp.append("</tbody></table>")

    t_min = ["<table><thead>" + tr(["配置", "K = 1e-6", "K = 1e-5", "K = 1e-4"], True) + "</thead><tbody>"]
    t_min.append(tr(["初始地形（第 0 步）"] + [f"{minima['initial']:,}"] * 3))
    for cfg, name, _ in CONFIGS:
        t_min.append(tr([name] + [f"{minima[f'{K}_{cfg}']:,}" for K in KS]))
    t_min.append("</tbody></table>")

    t_series = ["<table><thead>" + tr(["步"] + [n for _, n, _ in CONFIGS], True) + "</thead><tbody>"]
    for i in range(len(series["FS"])):
        t_series.append(tr([i + 1] + [f"{series[c][i]:,.0f}" for c, _, _ in CONFIGS]))
    t_series.append("</tbody></table>")

    t_scale = ["<table><thead>" + tr(["配置", "60×60（3,600 格）ms/步", "500×500（250,000 格）ms/步", "每格 µs，60×60", "每格 µs，500×500"], True) + "</thead><tbody>"]
    for cfg, name, _ in CONFIGS:
        s = smoke.get(cfg)
        b = cells[f"K1e-05_elev_{cfg}"]["ms"]
        t_scale.append(tr([name, f"{s:.1f}" if s else "", f"{b:,.0f}", f"{s / 3600 * 1e3:.2f}" if s else "", f"{b / 250000 * 1e3:.2f}"]))
    t_scale.append("</tbody></table>")

    t_wall = ["<table><thead>" + tr(["配置", "运行次数", "墙钟时间 min", "占比"], True) + "</thead><tbody>"]
    for cfg in ["DFR", "LMB", "PFFR", "FS", "FS_PIECEWISE"]:
        t_wall.append(tr([cfg, nrun[cfg], f"{wall[cfg] / 60:.1f}", f"{100 * wall[cfg] / total_wall:.1f}%"]))
    t_wall.append(tr(["合计", len(man), f"{total_wall / 60:.1f}", "100%"]))
    t_wall.append("</tbody></table>")

    t_env = ["<table><tbody>"]
    t_env.append(tr(["硬件", "AMD Ryzen 9 9950X3D，16 核 32 线程；内存 95.6 GB；台式机，电源方案“高性能”"]))
    t_env.append(tr(["系统", "Windows 11 专业版 build 26200；" + env["python"].split()[0] + " (conda-forge)"]))
    t_env.append(tr(["软件包", "，".join(f"{k} {v}" for k, v in versions.items() if k in ("landlab", "fastscape", "fastscapelib_fortran", "richdem", "numpy", "scipy", "numba", "xarray", "zarr", "xsimlab")).replace("fastscapelib_fortran n/a", "fastscapelib_fortran 2.8.4")]))
    t_env.append(tr(["运行条件", "每次运行为独立进程；CPU 亲和固定逻辑 CPU 4；OMP/NUMBA/BLAS 线程数 1；运行前 3 s CPU 负载采样，阈值 15%，实测最高 " + f"{max_cpu:.1f}%" + f"；可用内存最低 {min_mem:.1f} GB"]))
    t_env.append(tr(["统一物理设置", "500×500，dx = 1000 m，dt = 1000 年，50 步；m = 0.4，n = 1；D = 0.01 m²/yr；U = 0.001 m/yr；K = 1e-6、1e-5、1e-4；初始地形为种子 1234 的 0 至 1 m 均匀噪声；四边固定高程；D8 单流向；抬升不作用于边界"]))
    t_env.append(tr(["轮次", "预热 1 轮（5 步）加计时 3 轮（50 步），四种配置在轮内交替；统计排除每次运行前 5 步；表中数值为三轮中位数"]))
    t_env.append("</tbody></table>")

    kpi = []
    for cfg, name, _ in CONFIGS:
        c = cells[f"K1e-05_elev_{cfg}"]
        ratio = c["ms"] / base
        kpi.append(f'<div class="tile"><div class="tile-label">{name}</div><div class="tile-value">{c["ms"]:,.0f}<span class="unit"> ms/步</span></div><div class="tile-sub">{"基准" if cfg == "FS" else f"fastscape 的 {ratio:,.0f} 倍"} · 峰值内存 {c["mem_mb"]:.0f} MB</div></div>')

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    html = html.replace("__KPI__", "".join(kpi)).replace("__T_MAIN__", "".join(t_main)).replace("__T_COMP__", "".join(t_comp))
    html = html.replace("__T_MIN__", "".join(t_min)).replace("__T_SERIES__", "".join(t_series)).replace("__T_SCALE__", "".join(t_scale))
    html = html.replace("__T_WALL__", "".join(t_wall)).replace("__T_ENV__", "".join(t_env)).replace("__GENERATED__", generated)
    html = html.replace("__TOTAL_WALL_H__", f"{total_wall / 3600:.1f}").replace("__NRUNS__", str(len(man)))
    OUT.write_text(html, encoding="utf-8")
    print("written", OUT, f"{OUT.stat().st_size / 1024:.0f} KB")


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LEM L1 性能基准</title>
<style>
:root{
  color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4;
  --o1:#86b6ef; --o2:#3987e5; --o3:#1c5cab;
}
@media (prefers-color-scheme: dark){
  :root:where(:not([data-theme="light"])){
    color-scheme: dark;
    --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181;
    --o1:#6da7ec; --o2:#2a78d6; --o3:#184f95;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181;
  --o1:#6da7ec; --o2:#2a78d6; --o3:#184f95;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
main{max-width:1180px;margin:0 auto;padding:32px 24px 64px}
h1{font-size:26px;font-weight:600;margin:0 0 4px}
h2{font-size:18px;font-weight:600;margin:40px 0 12px}
p.lead{color:var(--ink2);margin:0 0 20px}
p.note{color:var(--ink2);margin:8px 0 0;font-size:13px}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:20px 0 8px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.tile-label{color:var(--ink2);font-size:13px}
.tile-value{font-size:30px;font-weight:600;line-height:1.2;margin:4px 0 2px}
.tile-value .unit{font-size:13px;font-weight:400;color:var(--ink2)}
.tile-sub{color:var(--muted);font-size:12px}
figure{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px 12px;margin:0 0 16px}
figcaption{font-weight:600;margin-bottom:2px}
.sub{color:var(--ink2);font-size:13px;margin-bottom:12px}
.multiples{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px 28px}
.panel-title{font-size:13px;color:var(--ink2);margin:0 0 4px;display:flex;align-items:center;gap:8px}
.key{display:inline-block;width:14px;height:3px;border-radius:2px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:4px 0 12px;color:var(--ink2);font-size:13px}
.legend .sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-2px;margin-right:6px}
svg{display:block;overflow:visible}
svg text{font-family:inherit}
.grid{stroke:var(--grid);stroke-width:1}
.axis{stroke:var(--axis);stroke-width:1}
.ref{stroke:var(--muted);stroke-width:1}
.tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.label{fill:var(--ink2);font-size:12px}
.value{fill:var(--ink);font-size:12px;font-variant-numeric:tabular-nums}
.inlabel{font-size:11px;font-variant-numeric:tabular-nums;pointer-events:none}
.mark{transition:opacity .12s}
.hit{fill:transparent;cursor:default;outline:none}
.hit:hover + .mark, .hit:focus + .mark{opacity:.78}
.line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.dot{stroke:var(--surface);stroke-width:2}
.cross{stroke:var(--axis);stroke-width:1}
#tip{position:absolute;z-index:10;background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:12px;box-shadow:0 4px 16px rgba(0,0,0,.12);pointer-events:none;max-width:280px}
#tip .tip-row{display:flex;gap:8px;align-items:baseline}
#tip strong{font-variant-numeric:tabular-nums;font-weight:600}
#tip span{color:var(--ink2)}
details{margin-top:8px}
summary{cursor:pointer;color:var(--ink2);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--grid);white-space:nowrap}
th{color:var(--ink2);font-weight:600}
td{font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}
.wrap td{white-space:normal}
.wrap td:first-child{white-space:nowrap;color:var(--ink2);width:110px}
ul.facts{margin:8px 0 0;padding-left:20px;color:var(--ink2)}
ul.facts li{margin:4px 0}
footer{color:var(--muted);font-size:12px;margin-top:40px}
</style>
</head>
<body>
<div id="tip" hidden></div>
<main>
<h1>LEM L1 性能基准</h1>
<p class="lead">data1000m 生产设置（500×500 @ 1 km）下 Landlab 与 fastscape 的每步耗时、分部分耗时、内存与地形演化对照。__NRUNS__ 次运行，总墙钟 __TOTAL_WALL_H__ 小时，生成于 __GENERATED__。</p>

<div class="kpi">__KPI__</div>
<p class="note">稳态每步耗时：K = 1e-5，高程组，三轮中位数，排除每次运行前 5 步。倍数以 fastscape 为 1。</p>

<h2>1. 每步耗时与 K 的关系</h2>
<figure>
<figcaption>稳态每步耗时（ms），按配置分面，每面各自的横轴</figcaption>
<div class="sub">每面三条为 K 的三档。悬停显示轮间范围和“高程+汇水面积”组的数值。</div>
<div class="multiples" id="fig-k"></div>
<details><summary>数据表</summary><div class="scroll">__T_MAIN__</div></details>
</figure>

<h2>2. 每步耗时的构成</h2>
<figure>
<figcaption>各环节占每步耗时的份额（K = 1e-5，高程组）</figcaption>
<div class="sub">fastscape 的份额来自逐例程调用（与 execute_step 合计一致）；Landlab 的份额来自脚本对各组件的分别计时。累积在 Landlab 中包含于汇流。</div>
<div class="legend" id="leg-comp"></div>
<div id="fig-comp"></div>
<details><summary>数据表（ms）</summary><div class="scroll">__T_COMP__</div></details>
</figure>

<h2>3. 50 步内每步耗时的变化</h2>
<figure>
<figcaption>每步耗时随步数的变化（K = 1e-5，高程组，三轮逐步中位数）</figcaption>
<div class="sub">每面各自的纵轴；横轴为步序。悬停显示该步数值。</div>
<div class="multiples" id="fig-series"></div>
<details><summary>数据表（ms）</summary><div class="scroll">__T_SERIES__</div></details>
</figure>

<h2>4. 第 50 步时地形中的洼地</h2>
<figure>
<figcaption>导出高程中的严格局部极小值格数（与工具无关的统计）</figcaption>
<div class="sub">初始地形含 <span id="init-min"></span> 个局部极小值（竖线）。K 越大侵蚀越快，洼地消失越快；同一 K 下两工具的地形演化速度不同。</div>
<div class="legend" id="leg-min"></div>
<div id="fig-min"></div>
<details><summary>数据表</summary><div class="scroll">__T_MIN__</div></details>
</figure>

<h2>5. 峰值内存</h2>
<figure>
<figcaption>单次运行的峰值工作集（MB，K = 1e-5，高程组）</figcaption>
<div id="fig-mem"></div>
</figure>

<h2>6. 运行时间分摊、规模换算与环境</h2>
<figure>
<figcaption>99 次运行的墙钟时间按配置分摊</figcaption>
<div class="scroll">__T_WALL__</div>
</figure>
<figure>
<figcaption>从 60×60 到 500×500 的每格耗时（K = 1e-5，高程组）</figcaption>
<div class="scroll">__T_SCALE__</div>
<p class="note">每格耗时在两种规模下接近的配置按线性规模变化；DepressionFinderAndRouter 的每格耗时随规模上升。</p>
</figure>
<figure>
<figcaption>环境与统一设置</figcaption>
<div class="scroll wrap">__T_ENV__</div>
<ul class="facts">
<li>fastscape 0.1.0 经 xarray-simlab 0.5.0 的路径在本环境无法运行（zarr 3 移除 <code>MemoryStore</code> 旧位置与 <code>Group.create_dataset</code>，numpy 2.5 移除 <code>in1d</code>）；fastscape 线因此直接调用 fastscapelib-fortran 的 FastScape API，<code>execute_step</code> 与逐例程调用的结果逐位一致。</li>
<li>LakeMapperBarnes 不写入 <code>flood_status_code</code>，该配置的“第 50 步淹没格数”未记录；其局部极小值计数来自导出高程。</li>
<li>两工具在相同设置下的流向与洼地改道结果不同：K = 1e-5 时最大汇水面积 fastscape 为 1.01×10¹¹ m²，Landlab 三种配置为 5.05×10¹⁰ 至 5.06×10¹⁰ m²。</li>
</ul>
</figure>

<footer>数据来源：bench/results/L1/runs/*.json、manifest.jsonl、exports/*.npy、results/_smoke、results/env_check.json。生成脚本 bench/make_report.py。</footer>
</main>
<script>
const D = __DATA__;
const NS = "http://www.w3.org/2000/svg";
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function el(tag, attrs, parent){ const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
function txt(parent, attrs, s){ const t = el('text', attrs, parent); t.textContent = s; return t; }
function fmt(v, d){ d = d === undefined ? 0 : d; return Number(v).toLocaleString('en-US', {maximumFractionDigits: d, minimumFractionDigits: d}); }
function niceStep(range, n){ const raw = range / n, p = Math.pow(10, Math.floor(Math.log10(raw))), r = raw / p; return (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * p; }
function hbar(x, y, w, h, r){ r = Math.min(r, w / 2, h / 2); return `M${x},${y} H${x + w - r} A${r},${r} 0 0 1 ${x + w},${y + r} V${y + h - r} A${r},${r} 0 0 1 ${x + w - r},${y + h} H${x} Z`; }
const tip = document.getElementById('tip');
function showTip(x, y, rows){ tip.replaceChildren(); rows.forEach(([v, l]) => { const r = document.createElement('div'); r.className = 'tip-row'; const s = document.createElement('strong'); s.textContent = v; const sp = document.createElement('span'); sp.textContent = l; r.append(s, sp); tip.appendChild(r); }); tip.hidden = false; tip.style.left = Math.min(x + 14, document.documentElement.clientWidth - tip.offsetWidth - 12) + 'px'; tip.style.top = (y + 14) + 'px'; }
function hideTip(){ tip.hidden = true; }
function hover(hit, rows){ hit.addEventListener('pointermove', e => showTip(e.pageX, e.pageY, rows)); hit.addEventListener('pointerleave', hideTip); hit.addEventListener('focus', () => { const b = hit.getBoundingClientRect(); showTip(b.right + window.scrollX, b.top + window.scrollY, rows); }); hit.addEventListener('blur', hideTip); }
const SERIES = ['--s1', '--s2', '--s3', '--s4', '--s5'];
const ORD = ['--o1', '--o2', '--o3'];
const cfgColor = {}; D.configs.forEach((c, i) => cfgColor[c.id] = SERIES[i]);

// 1. small multiples: bars per configuration, K tiers as ordinal ramp
(function(){
  const host = document.getElementById('fig-k');
  D.configs.forEach(cfg => {
    const wrap = document.createElement('div');
    const t = document.createElement('div'); t.className = 'panel-title'; t.textContent = cfg.name; wrap.appendChild(t);
    const W = 360, labelW = 62, valW = 70, barH = 18, gap = 12, padT = 6, axisH = 24;
    const rows = D.ks.map((K, i) => ({K, c: D.cells[`K${K}_elev_${cfg.id}`], da: D.cells[`K${K}_elev_da_${cfg.id}`], color: ORD[i]}));
    const H = padT + rows.length * (barH + gap) + axisH;
    const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': cfg.name + ' 每步耗时'}, wrap);
    const x0 = labelW, plotW = W - labelW - valW;
    const max = Math.max(...rows.map(r => r.c.ms_max)); const step = niceStep(max, 3); const top = Math.ceil(max / step) * step;
    const sx = v => x0 + v / top * plotW;
    for (let v = 0; v <= top + 1e-9; v += step){ el('line', {x1: sx(v), x2: sx(v), y1: padT, y2: H - axisH, class: 'grid'}, svg); txt(svg, {x: sx(v), y: H - 7, class: 'tick', 'text-anchor': 'middle'}, fmt(v)); }
    el('line', {x1: x0, x2: x0, y1: padT, y2: H - axisH, class: 'axis'}, svg);
    rows.forEach((r, i) => {
      const y = padT + i * (barH + gap);
      txt(svg, {x: x0 - 8, y: y + barH / 2 + 4, class: 'label', 'text-anchor': 'end'}, D.kLabel[r.K].replace('K = ', ''));
      const hit = el('rect', {x: x0, y: y - gap / 2, width: W - x0, height: barH + gap, class: 'hit', tabindex: 0}, svg);
      el('path', {d: hbar(x0, y, Math.max(sx(r.c.ms) - x0, 1), barH, 4), fill: `var(${r.color})`, class: 'mark'}, svg);
      txt(svg, {x: sx(r.c.ms) + 6, y: y + barH / 2 + 4, class: 'value'}, fmt(r.c.ms) + ' ms');
      hover(hit, [[fmt(r.c.ms) + ' ms', '每步中位数，' + D.kLabel[r.K]], [fmt(r.c.ms_min) + ' 至 ' + fmt(r.c.ms_max) + ' ms', '三轮范围'], [fmt(r.da.ms) + ' ms', '高程+汇水面积组'], [fmt(r.c.first_ms) + ' ms', '首步']]);
    });
    txt(svg, {x: W - 2, y: H - 7, class: 'tick', 'text-anchor': 'end'}, 'ms');
    host.appendChild(wrap);
  });
})();

// 2. 100% stacked horizontal bars: components
(function(){
  const host = document.getElementById('fig-comp'); const leg = document.getElementById('leg-comp');
  D.comps.forEach(([k, name], i) => { const s = document.createElement('span'); const sw = document.createElement('span'); sw.className = 'sw'; sw.style.background = `var(${SERIES[i]})`; s.append(sw, document.createTextNode(name)); leg.appendChild(s); });
  const W = 900, labelW = 250, barH = 20, gap = 14, padT = 6, axisH = 24, right = 16;
  const H = padT + D.configs.length * (barH + gap) + axisH;
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': '每步耗时构成'}, host);
  const x0 = labelW, plotW = W - labelW - right;
  for (let p = 0; p <= 100; p += 25){ const x = x0 + p / 100 * plotW; el('line', {x1: x, x2: x, y1: padT, y2: H - axisH, class: 'grid'}, svg); txt(svg, {x, y: H - 7, class: 'tick', 'text-anchor': 'middle'}, p + '%'); }
  D.configs.forEach((cfg, i) => {
    const y = padT + i * (barH + gap);
    const comps = cfg.id === 'FS' ? D.fsSplit : D.cells[`K1e-05_elev_${cfg.id}`].comps;
    const parts = D.comps.map(([k, name], j) => ({k, name, v: comps[k] || 0, color: SERIES[j]})).filter(p => p.v > 0);
    const total = parts.reduce((a, p) => a + p.v, 0);
    txt(svg, {x: x0 - 10, y: y + barH / 2 + 4, class: 'label', 'text-anchor': 'end'}, cfg.name);
    const gaps = 2 * (parts.length - 1); let x = x0;
    parts.forEach((p, j) => {
      const w = p.v / total * (plotW - gaps);
      const isLast = j === parts.length - 1, isFirst = j === 0;
      let d;
      if (isLast) d = hbar(x, y, Math.max(w, 1), barH, 4); else d = `M${x},${y} H${x + Math.max(w, 1)} V${y + barH} H${x} Z`;
      const hit = el('rect', {x: x, y: y - gap / 2, width: Math.max(w, 6), height: barH + gap, class: 'hit', tabindex: 0}, svg);
      el('path', {d, fill: `var(${p.color})`, class: 'mark'}, svg);
      const share = 100 * p.v / total;
      if (w >= 64) txt(svg, {x: x + w / 2, y: y + barH / 2 + 4, class: 'inlabel', 'text-anchor': 'middle', fill: (p.color === '--s4' || p.color === '--s3') ? '#0b0b0b' : '#ffffff'}, `${p.name} ${share.toFixed(share < 10 ? 1 : 0)}%`);
      hover(hit, [[fmt(p.v, p.v < 10 ? 2 : 1) + ' ms', p.name], [share.toFixed(share < 1 ? 2 : 1) + '%', '占每步耗时'], [fmt(total, 1) + ' ms', '每步合计']]);
      x += w + 2;
    });
  });
})();

// 3. small multiples: per-step series
(function(){
  const host = document.getElementById('fig-series');
  D.configs.forEach(cfg => {
    const vals = D.series[cfg.id];
    const wrap = document.createElement('div');
    const t = document.createElement('div'); t.className = 'panel-title'; const key = document.createElement('span'); key.className = 'key'; key.style.background = `var(${cfgColor[cfg.id]})`; t.append(key, document.createTextNode(cfg.name)); wrap.appendChild(t);
    const W = 360, H = 170, ml = 58, mr = 62, mt = 10, mb = 26;
    const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': cfg.name + ' 每步耗时序列'}, wrap);
    const n = vals.length, lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.25 || hi * 0.05; const step = niceStep((hi - lo + 2 * pad) || 1, 3);
    const y0 = Math.floor((lo - pad) / step) * step, y1 = Math.ceil((hi + pad) / step) * step;
    const sx = i => ml + (i) / (n - 1) * (W - ml - mr), sy = v => mt + (1 - (v - y0) / (y1 - y0)) * (H - mt - mb);
    for (let v = y0; v <= y1 + 1e-9; v += step){ el('line', {x1: ml, x2: W - mr, y1: sy(v), y2: sy(v), class: 'grid'}, svg); txt(svg, {x: ml - 6, y: sy(v) + 4, class: 'tick', 'text-anchor': 'end'}, fmt(v)); }
    [1, 10, 20, 30, 40, 50].forEach(s => { if (s <= n) txt(svg, {x: sx(s - 1), y: H - 8, class: 'tick', 'text-anchor': 'middle'}, s); });
    el('line', {x1: ml, x2: W - mr, y1: H - mb, y2: H - mb, class: 'axis'}, svg);
    const d = vals.map((v, i) => (i ? 'L' : 'M') + sx(i).toFixed(1) + ',' + sy(v).toFixed(1)).join(' ');
    el('path', {d, class: 'line', stroke: `var(${cfgColor[cfg.id]})`}, svg);
    const cross = el('line', {x1: 0, x2: 0, y1: mt, y2: H - mb, class: 'cross', visibility: 'hidden'}, svg);
    const dotH = el('circle', {r: 4, class: 'dot', fill: `var(${cfgColor[cfg.id]})`, visibility: 'hidden'}, svg);
    el('circle', {cx: sx(n - 1), cy: sy(vals[n - 1]), r: 4, class: 'dot', fill: `var(${cfgColor[cfg.id]})`}, svg);
    txt(svg, {x: sx(n - 1) + 8, y: sy(vals[n - 1]) + 4, class: 'value'}, fmt(vals[n - 1]));
    txt(svg, {x: W - 2, y: H - 8, class: 'tick', 'text-anchor': 'end'}, '步');
    const hit = el('rect', {x: ml, y: mt, width: W - ml - mr, height: H - mt - mb, class: 'hit'}, svg);
    hit.addEventListener('pointermove', e => { const b = svg.getBoundingClientRect(); const px = (e.clientX - b.left) / b.width * W; let i = Math.round((px - ml) / (W - ml - mr) * (n - 1)); i = Math.max(0, Math.min(n - 1, i)); cross.setAttribute('x1', sx(i)); cross.setAttribute('x2', sx(i)); cross.setAttribute('visibility', 'visible'); dotH.setAttribute('cx', sx(i)); dotH.setAttribute('cy', sy(vals[i])); dotH.setAttribute('visibility', 'visible'); showTip(e.pageX, e.pageY, [[fmt(vals[i]) + ' ms', '第 ' + (i + 1) + ' 步']]); });
    hit.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); dotH.setAttribute('visibility', 'hidden'); hideTip(); });
    host.appendChild(wrap);
  });
})();

// 4. grouped bars: local minima by K and configuration, with initial reference
(function(){
  const host = document.getElementById('fig-min'); const leg = document.getElementById('leg-min');
  document.getElementById('init-min').textContent = fmt(D.minima.initial);
  D.configs.forEach((c, i) => { const s = document.createElement('span'); const sw = document.createElement('span'); sw.className = 'sw'; sw.style.background = `var(${SERIES[i]})`; s.append(sw, document.createTextNode(c.name)); leg.appendChild(s); });
  const W = 900, labelW = 80, valW = 80, barH = 14, gap = 2, groupGap = 18, padT = 26, axisH = 24;
  const groupH = D.configs.length * (barH + gap) - gap;
  const H = padT + D.ks.length * (groupH + groupGap) + axisH;
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': '局部极小值格数'}, host);
  const x0 = labelW, plotW = W - labelW - valW;
  const max = D.minima.initial; const step = niceStep(max, 4); const top = Math.ceil(max / step) * step;
  const sx = v => x0 + v / top * plotW;
  for (let v = 0; v <= top + 1e-9; v += step){ el('line', {x1: sx(v), x2: sx(v), y1: padT, y2: H - axisH, class: 'grid'}, svg); txt(svg, {x: sx(v), y: H - 7, class: 'tick', 'text-anchor': 'middle'}, fmt(v)); }
  el('line', {x1: x0, x2: x0, y1: padT, y2: H - axisH, class: 'axis'}, svg);
  el('line', {x1: sx(max), x2: sx(max), y1: padT - 6, y2: H - axisH, class: 'ref'}, svg);
  txt(svg, {x: sx(max) - 6, y: 12, class: 'tick', 'text-anchor': 'end'}, '初始地形 ' + fmt(max));
  D.ks.forEach((K, gi) => {
    const gy = padT + gi * (groupH + groupGap);
    txt(svg, {x: x0 - 8, y: gy + groupH / 2 + 4, class: 'label', 'text-anchor': 'end'}, D.kLabel[K]);
    D.configs.forEach((c, i) => {
      const y = gy + i * (barH + gap); const v = D.minima[`${K}_${c.id}`];
      const hit = el('rect', {x: x0, y: y - 1, width: W - x0, height: barH + gap, class: 'hit', tabindex: 0}, svg);
      el('path', {d: hbar(x0, y, Math.max(sx(v) - x0, 1), barH, 4), fill: `var(${SERIES[i]})`, class: 'mark'}, svg);
      txt(svg, {x: sx(v) + 6, y: y + barH / 2 + 4, class: 'value'}, fmt(v));
      const c50 = D.cells[`K${K}_elev_${c.id}`];
      hover(hit, [[fmt(v), '局部极小值格数，' + c.name + '，' + D.kLabel[K]], [(100 * (1 - v / max)).toFixed(0) + '%', '相对初始地形已消失'], [c.id === 'LMB' ? '未记录' : fmt(c50.flooded), '工具报告的淹没格数']]);
    });
  });
})();

// 5. memory bars (single series)
(function(){
  const host = document.getElementById('fig-mem');
  const W = 900, labelW = 250, valW = 90, barH = 18, gap = 12, padT = 6, axisH = 24;
  const rows = D.configs.map(c => ({c, v: D.cells[`K1e-05_elev_${c.id}`].mem_mb}));
  const H = padT + rows.length * (barH + gap) + axisH;
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': '峰值内存'}, host);
  const x0 = labelW, plotW = W - labelW - valW;
  const max = Math.max(...rows.map(r => r.v)); const step = niceStep(max, 4); const top = Math.ceil(max / step) * step;
  const sx = v => x0 + v / top * plotW;
  for (let v = 0; v <= top + 1e-9; v += step){ el('line', {x1: sx(v), x2: sx(v), y1: padT, y2: H - axisH, class: 'grid'}, svg); txt(svg, {x: sx(v), y: H - 7, class: 'tick', 'text-anchor': 'middle'}, fmt(v)); }
  el('line', {x1: x0, x2: x0, y1: padT, y2: H - axisH, class: 'axis'}, svg);
  rows.forEach((r, i) => {
    const y = padT + i * (barH + gap);
    txt(svg, {x: x0 - 10, y: y + barH / 2 + 4, class: 'label', 'text-anchor': 'end'}, r.c.name);
    const hit = el('rect', {x: x0, y: y - gap / 2, width: W - x0, height: barH + gap, class: 'hit', tabindex: 0}, svg);
    el('path', {d: hbar(x0, y, Math.max(sx(r.v) - x0, 1), barH, 4), fill: 'var(--s1)', class: 'mark'}, svg);
    txt(svg, {x: sx(r.v) + 6, y: y + barH / 2 + 4, class: 'value'}, fmt(r.v) + ' MB');
    hover(hit, [[fmt(r.v) + ' MB', '峰值工作集，' + r.c.name]]);
  });
  txt(svg, {x: W - 2, y: H - 7, class: 'tick', 'text-anchor': 'end'}, 'MB');
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
