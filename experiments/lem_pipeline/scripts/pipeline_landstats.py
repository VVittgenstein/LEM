"""Land statistics (elevation, slope, drainage area, stream-power kernel) of the 34 reference landmasses at about 1 km.

Reads session A's GEBCO 30 arc-second subsets, writes docs/work/2026-09-09-pipeline/reference-land-statistics.csv
(one row per landmass) and reference-land-statistics.json (pooled quantiles, cell-weighted). Run:
  PYTHONPATH=experiments lem-env/python.exe experiments/lem_pipeline/scripts/pipeline_landstats.py [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file()) / "experiments"))

from lem_pipeline.landstats import QUANTS, d8_area_and_slope, land_quantiles, to_square_cells  # noqa: E402
from lem_pipeline.paths import D_TABLES, REFERENCE_DATA, ROOT  # noqa: E402
from lem_pipeline.reference import population_ids, read_csv  # noqa: E402

OUT = ROOT / "docs" / "work" / "2026-09-09-pipeline"
SUBSETS = REFERENCE_DATA / "2026-09-08-q1-data" / "A" / "subsets"
M, N = 0.45, 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    all_rows, ids = population_ids(60.0)
    gshhg = {r["id"]: r["gshhg_id"] for r in read_csv(D_TABLES / "reference-landmasses.csv")}
    rows, pooled = [], {"elevation_m": [], "slope": [], "area_m2": [], "kernel_AmSn": []}
    for lid in ids[: a.limit]:
        gid = gshhg.get(lid, "")
        path = SUBSETS / f"GSHHG-{int(gid):06d}-gebco2026-s30.npz" if gid.isdigit() else None
        if path is None or not path.exists():
            rows.append({"id": lid, "name": all_rows[lid]["name"], "status": "no subset"})
            continue
        t0 = time.perf_counter()
        d = np.load(path)
        zs, cell_km = to_square_cells(d["z"], d["lat"], d["lon"])
        area, slope, land_all = d8_area_and_slope(zs, cell_km)
        # restrict to the focal landmass: the land component nearest to D's landmass coordinate (the subset windows are
        # bounding boxes that can contain neighbouring land, e.g. southern Sweden in Zealand's window)
        from scipy import ndimage as ndi
        lab, ncomp = ndi.label(land_all, ndi.generate_binary_structure(2, 1))
        expected_km2 = float(all_rows[lid].get("land_area_km2") or 0.0)
        if ncomp == 0:
            land, ratio = land_all, float("nan")
        else:
            sizes = np.bincount(lab.ravel())[1:] * cell_km ** 2
            k = int(np.argmin(np.abs(np.log((sizes + 1e-9) / max(expected_km2, 1e-9))))) + 1 if expected_km2 > 0 else int(np.argmax(sizes)) + 1
            land = lab == k
            ratio = float(sizes[k - 1] / expected_km2) if expected_km2 > 0 else float("nan")
        q = land_quantiles(zs.astype(np.float64), area, slope, land, M, N, cell_km=cell_km)
        q["land_cells_window"] = int(land_all.sum())
        q["focal_area_ratio"] = ratio  # focal component area over D's landmass area; outside 0.5 to 2 the component is not the landmass (e.g. joined to a mainland at 1 km)
        focal_ok = np.isfinite(ratio) and 0.5 <= ratio <= 2.0
        row = {"id": lid, "name": all_rows[lid]["name"], "gshhg_id": gid, "status": "ok", "cell_km": round(cell_km, 4),
               "ny": zs.shape[0], "nx": zs.shape[1], "land_cells": q["land_cells"], "land_cells_window": q["land_cells_window"],
               "focal_area_km2": round(q["land_cells"] * cell_km ** 2, 1), "expected_area_km2": expected_km2, "focal_area_ratio": round(ratio, 3),
               "focal_ok": focal_ok, "wall_s": round(time.perf_counter() - t0, 1)}
        for name in ("elevation_m", "slope", "area_m2", "kernel_AmSn"):
            for k, v in q[name].items():
                row[f"{name}_{k}"] = v
        for key in ("kernel_AmSn_A_ge_1km2", "kernel_AmSn_A_ge_10km2", "kernel_AmSn_A_ge_100km2"):
            if key in q:
                for k, v in q[key].items():
                    row[f"{key}_{k}"] = v
        rows.append(row)
        # pooled sample (subsample land cells to bound memory; weight by cell count through replication factor)
        if not focal_ok:
            print(f"{lid} {all_rows[lid]['name'][:24]:24s} focal component area ratio {ratio:.2f}: excluded from the pooled quantiles", flush=True)
            continue
        sel = land & (area > 0)
        idx = np.flatnonzero(sel)
        take = idx if idx.size <= 200000 else np.random.default_rng(0).choice(idx, 200000, replace=False)
        w = idx.size / take.size
        pooled["elevation_m"].append((zs.ravel()[take].astype(np.float64), w))
        pooled["slope"].append((slope.ravel()[take], w))
        pooled["area_m2"].append((area.ravel()[take], w))
        pooled["kernel_AmSn"].append((np.power(area.ravel()[take], M) * np.power(np.maximum(slope.ravel()[take], 1e-6), N), w))
        print(f"{lid} {all_rows[lid]['name'][:24]:24s} cells {zs.shape} land {q['land_cells']} slope p50 {q['slope']['p50']:.4f} "
              f"A p95 {q['area_m2']['p95']:.3g} kernel p50 {q['kernel_AmSn']['p50']:.3g} p95 {q['kernel_AmSn']['p95']:.3g} ({row['wall_s']} s)", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(OUT / "reference-land-statistics.csv", "w", encoding="utf-8", newline="") as f:
        wri = csv.DictWriter(f, fieldnames=keys)
        wri.writeheader()
        wri.writerows(rows)
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "population": 34, "n_ok": sum(1 for r in rows if r.get("status") == "ok"),
               "m": M, "n": N, "source": "references/data/2026-09-08-q1-data/A/subsets (GEBCO 2026 30 arc-second), richdem D8 after epsilon depression filling",
               "cell": "square cells of the latitude spacing (about 0.925 km) after scaling the longitude axis by cos(latitude)",
               "evidence_state": "本项目由第一级数据计算", "pooled_quantiles_cell_weighted": {}}
    for name, parts in pooled.items():
        if not parts:
            continue
        vals = np.concatenate([p[0] for p in parts])
        wts = np.concatenate([np.full(p[0].size, p[1]) for p in parts])
        order = np.argsort(vals)
        vals, wts = vals[order], wts[order]
        cw = np.cumsum(wts) / wts.sum()
        summary["pooled_quantiles_cell_weighted"][name] = {f"p{int(q * 100):02d}": float(vals[min(int(np.searchsorted(cw, q)), vals.size - 1)]) for q in QUANTS}
    (OUT / "reference-land-statistics.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["pooled_quantiles_cell_weighted"], indent=1))


if __name__ == "__main__":
    main()
