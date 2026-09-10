"""Reference-population statistics re-aggregated for the 34 low-latitude landmasses.

yZz decided on 2026-09-09 to use the landmasses with ``abs(latitude) < 60`` from D's 71 core landmasses as the
reference population (34 landmasses). Sessions A and D delivered per-landmass tables, so their class-1 and class-4
distributions can be re-aggregated here without touching the original deliveries. All outputs carry the evidence
state ``本项目借鉴或合成改造`` (re-aggregation of project computations).

Outputs are written to ``docs/work/2026-09-08-q1-data/merged/data-package/pop34/`` by ``scripts/pipeline_population34.py``.
"""
from __future__ import annotations

import ast
import csv
import json
from pathlib import Path

import numpy as np

from .paths import A_TABLES, D_TABLES

EVIDENCE = "本项目借鉴或合成改造"
QUANTS = [("minimum", 0.0), ("p05", 0.05), ("p25", 0.25), ("median", 0.5), ("p75", 0.75), ("p95", 0.95), ("maximum", 1.0)]


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def population_ids(lat_limit: float = 60.0) -> tuple[dict[str, dict], list[str]]:
    """Return ({id: row} for all 71, [ids with abs(latitude) < lat_limit])."""
    rows = read_csv(D_TABLES / "reference-landmasses.csv")
    all_rows = {r["id"]: r for r in rows}
    ids = [r["id"] for r in rows if fnum(r["latitude"]) is not None and abs(fnum(r["latitude"])) < lat_limit]
    return all_rows, ids


def quantiles(values, weights=None) -> dict:
    v = np.asarray([x for x in values if x is not None], dtype=float)
    out = {"n": int(v.size)}
    if v.size == 0:
        return out
    if weights is None:
        for k, q in QUANTS:
            out[k] = float(np.quantile(v, q))
        out["mean"] = float(v.mean())
    else:
        w = np.asarray(weights, dtype=float)
        order = np.argsort(v)
        v, w = v[order], w[order]
        cw = np.cumsum(w) / w.sum()
        for k, q in QUANTS:
            out[k] = float(v[min(int(np.searchsorted(cw, q, side="left")), v.size - 1)])
        out["mean"] = float(np.average(v, weights=w))
    return out


def pooled_histogram_quantiles(edges: list[float], weights: np.ndarray) -> dict:
    """Quantiles from a pooled histogram assuming a uniform density inside each bin."""
    e = np.asarray(edges, dtype=float)
    w = np.asarray(weights, dtype=float)
    if w.sum() <= 0:
        return {"n": 0}
    cw = np.concatenate([[0.0], np.cumsum(w)]) / w.sum()
    out = {"weight": float(w.sum())}
    for k, q in QUANTS:
        i = int(np.clip(np.searchsorted(cw, q, side="right") - 1, 0, len(w) - 1))
        frac = (q - cw[i]) / (cw[i + 1] - cw[i]) if cw[i + 1] > cw[i] else 0.0
        out[k] = float(e[i] + frac * (e[i + 1] - e[i]))
    return out


def load_a_landmasses(ids: list[str]) -> dict[str, dict]:
    files = {}
    for p in sorted((A_TABLES / "spatial-by-landmass").glob("*.json")):
        o = json.loads(p.read_text(encoding="utf-8"))
        rid = o.get("reference_id")
        if rid in ids and rid not in files:
            files[rid] = o
    return files


def _parse_hist(h) -> tuple[list[float], list[float]] | None:
    if isinstance(h, str):
        try:
            h = ast.literal_eval(h)
        except Exception:
            return None
    if not isinstance(h, dict) or "edges" not in h:
        return None
    edges = [float(x) for x in h["edges"]]
    weights = [float(x) for x in (h.get("weights") or h.get("counts") or [])]
    if len(weights) != len(edges) - 1:
        return None
    return edges, weights


def aggregate_class1(landmasses: dict[str, dict]) -> list[dict]:
    """Depths, shelf geometry, roughness and land elevation for the population."""
    rows: list[dict] = []
    # depths: per environment × band × margin
    keys = {}
    for rid, o in landmasses.items():
        for d in o.get("depths", []):
            key = (d["environment"], str(d["distance_min_km"]), str(d["distance_max_km"]), d.get("margin", "all"))
            keys.setdefault(key, []).append((rid, d))
    for (env, dmin, dmax, margin), items in sorted(keys.items()):
        meds = [fnum(d.get("median")) for _, d in items if fnum(d.get("n")) and fnum(d.get("n")) > 0]
        q = quantiles(meds)
        rows.append({"group": "depth", "environment": env, "band_km": f"{dmin}-{dmax}", "margin": margin, "statistic": "landmass_medians",
                     "unit": "m", **q, "landmass_count": len(meds), "evidence_state": EVIDENCE,
                     "notes": "各陆块中位水深的跨陆块分布，用于抽取每段弧的趋势深度"})
        edges, wsum = None, None
        for _, d in items:
            ph = _parse_hist(d.get("histogram"))
            if ph is None:
                continue
            e, w = ph
            if edges is None:
                edges, wsum = e, np.zeros(len(w))
            if e == edges:
                wsum += np.asarray(w)
        if edges is not None:
            pq = pooled_histogram_quantiles(edges, wsum)
            rows.append({"group": "depth", "environment": env, "band_km": f"{dmin}-{dmax}", "margin": margin, "statistic": "pooled_pixels",
                         "unit": "m", **pq, "landmass_count": len(items), "evidence_state": EVIDENCE,
                         "notes": "各陆块像元直方图合并后的分位数，分箱内按均匀密度插值"})
    # shelf geometry
    for param, unit in (("width_km", "km"), ("break_depth_m", "m"), ("slope_gradient_m_per_m", "m/m")):
        for margin in ("all", "active", "passive"):
            meds = []
            for rid, o in landmasses.items():
                for sg in o.get("shelf_geometry", []):
                    if sg.get("margin") != margin:
                        continue
                    stat = sg.get(param)
                    if isinstance(stat, str):
                        try:
                            stat = ast.literal_eval(stat)
                        except Exception:
                            stat = None
                    if isinstance(stat, dict) and fnum(stat.get("n")) and fnum(stat.get("n")) > 0 and fnum(stat.get("median")) is not None:
                        meds.append(fnum(stat["median"]))
            q = quantiles(meds)
            rows.append({"group": "shelf_geometry", "environment": "shelf_continental", "band_km": "0-250", "margin": margin, "statistic": f"landmass_medians:{param}",
                         "unit": unit, **q, "landmass_count": len(meds), "evidence_state": EVIDENCE,
                         "notes": "A 会话的格网坡折统计；F 会话的沿法向统计另见前置任务合并包"})
    # roughness
    keys = {}
    for rid, o in landmasses.items():
        for r in o.get("roughness", []):
            keys.setdefault((r["environment"], str(r["window_km"])), []).append(r)
    for (env, win), items in sorted(keys.items(), key=lambda kv: (kv[0][0], float(kv[0][1]))):
        meds = [fnum(r.get("median")) for r in items if fnum(r.get("n")) and fnum(r.get("n")) > 0]
        q = quantiles(meds)
        rows.append({"group": "roughness", "environment": env, "band_km": f"window {win}", "margin": "all", "statistic": "landmass_medians",
                     "unit": "m", **q, "landmass_count": len(meds), "evidence_state": EVIDENCE,
                     "notes": "方窗内局部标准差的陆块中位数分布；1 km 尺度未取得，外推为假设"})
    # land elevation
    for k in ("p05", "p25", "median", "p75", "p95"):
        vals = [fnum(o.get("land", {}).get(k)) for o in landmasses.values()]
        q = quantiles(vals)
        rows.append({"group": "land_elevation", "environment": "land", "band_km": "", "margin": "all", "statistic": f"landmass_{k}",
                     "unit": "m", **q, "landmass_count": len([v for v in vals if v is not None]), "evidence_state": EVIDENCE,
                     "notes": "各陆块现代陆地高程分位数的跨陆块分布；淹没情形的低平面高度从低分位分布抽取"})
    edges, wsum = None, None
    for o in landmasses.values():
        ph = _parse_hist(o.get("land_histogram"))
        if ph is None:
            continue
        e, w = ph
        if edges is None:
            edges, wsum = e, np.zeros(len(w))
        if e == edges:
            wsum += np.asarray(w)
    if edges is not None:
        rows.append({"group": "land_elevation", "environment": "land", "band_km": "", "margin": "all", "statistic": "pooled_pixels",
                     "unit": "m", **pooled_histogram_quantiles(edges, wsum), "landmass_count": len(landmasses), "evidence_state": EVIDENCE,
                     "notes": "各陆块陆地像元直方图合并"})
    return rows


def aggregate_class4(ids: list[str]) -> tuple[list[dict], list[dict]]:
    """Shape statistics (unconditional and by area tercile) and inner-sea proxy frequency for the population."""
    metrics = [r for r in read_csv(D_TABLES / "landmass-metrics-1km.csv") if r["id"] in ids]
    for r in metrics:
        area, sq = fnum(r["net_land_area_1km_km2"]), fnum(r["min_square_grid_search_upper_km"])
        r["_fill"] = area / sq ** 2 if area and sq else None
        r["_area"] = area
    stats = [("net_land_area_1km_km2", "km²"), ("max_feret_km", "km"), ("pca_ratio", "1"), ("rectangle_ratio", "1"),
             ("shoreline_development_crofton", "1"), ("shoreline_development_grid", "1"), ("coast_crofton4_km", "km"),
             ("neighbour_count_1km2", "count"), ("neighbour_count_10km2", "count"), ("focal_components_4", "count"), ("_fill", "1")]
    rows: list[dict] = []
    areas = np.asarray([r["_area"] for r in metrics], dtype=float)
    terciles = np.quantile(areas, [1 / 3, 2 / 3])
    for col, unit in stats:
        vals = [fnum(r[col]) if col != "_fill" else r["_fill"] for r in metrics]
        rows.append({"statistic": col.strip("_") if col != "_fill" else "fill_ratio_area_over_min_square", "subset": "all", "unit": unit,
                     **quantiles(vals), "evidence_state": EVIDENCE, "notes": "34 个陆块，D 会话逐陆块表"})
        for label, lo, hi in (("area_tercile_small", -np.inf, terciles[0]), ("area_tercile_mid", terciles[0], terciles[1]), ("area_tercile_large", terciles[1], np.inf)):
            sub = [(fnum(r[col]) if col != "_fill" else r["_fill"]) for r in metrics if lo <= r["_area"] < hi or (hi == np.inf and r["_area"] >= lo)]
            rows.append({"statistic": col.strip("_") if col != "_fill" else "fill_ratio_area_over_min_square", "subset": label, "unit": unit,
                         **quantiles(sub), "evidence_state": EVIDENCE, "notes": f"面积三分组边界 {terciles[0]:.0f}、{terciles[1]:.0f} km²"})
    # rank correlation with area
    from scipy.stats import spearmanr
    for col, unit in stats[1:]:
        vals = np.asarray([fnum(r[col]) if col != "_fill" else r["_fill"] for r in metrics], dtype=float)
        ok = np.isfinite(vals)
        rho = spearmanr(areas[ok], vals[ok]).statistic if ok.sum() > 3 else float("nan")
        rows.append({"statistic": col.strip("_") if col != "_fill" else "fill_ratio_area_over_min_square", "subset": "spearman_vs_area", "unit": "1",
                     "n": int(ok.sum()), "median": float(rho), "evidence_state": EVIDENCE, "notes": "与净陆地面积的秩相关"})
    # occupancy reachable after scaling into a 480 km window
    fills = np.asarray([r["_fill"] for r in metrics if r["_fill"] is not None])
    for target in (0.3, 0.4, 0.5, 0.55, 0.6):
        rows.append({"statistic": "shapes_reaching_occupancy", "subset": f"target_{target:.2f}", "unit": "count", "n": int(fills.size),
                     "median": int((fills * 0.9216 >= target).sum()), "evidence_state": EVIDENCE,
                     "notes": "填充比例乘 0.9216（留 10 km 海洋带的 480 km 窗口）不小于目标占比的形状数"})
    # inner-sea proxy frequency
    emb = [r for r in read_csv(D_TABLES / "embayment-proxy-1km.csv") if r.get("gshhg_id")]
    id_by_gshhg = {r["gshhg_id"]: r["id"] for r in read_csv(D_TABLES / "reference-landmasses.csv")}
    emb = [r for r in emb if id_by_gshhg.get(r["gshhg_id"]) in ids]
    freq: list[dict] = []
    keys = {}
    for r in emb:
        keys.setdefault((r["radius_km"], r["nominal_mouth_width_km"], r["min_area_km2"]), []).append(r)
    for (radius, mouth, min_area), items in sorted(keys.items(), key=lambda kv: (float(kv[0][0] or 0), float(kv[0][1] or 0), float(kv[0][2] or 0))):
        counts = [fnum(r["count"]) for r in items]
        present = [c for c in counts if c is not None and c > 0]
        freq.append({"radius_km": radius, "mouth_width_km": mouth, "min_area_km2": min_area, "landmass_count": len(items),
                     "with_candidate": len(present), "fraction_with_candidate": len(present) / len(items) if items else None,
                     "evidence_state": EVIDENCE, "notes": "闭运算残余海域的几何代理，地学含义未验证"})
    return rows, freq


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    if not rows:
        return
    cols = columns or list(dict.fromkeys(k for r in rows for k in r.keys()))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
