"""Measure the surface relief spectrum exponent of the 34 reference landmasses from session A's GEBCO subsets.

Writes docs/work/2026-09-09-pipeline/reference-surface-spectrum.csv (one row per landmass and window) and
reference-surface-spectrum.json (quantiles). Run: PYTHONPATH=experiments lem-env/python.exe experiments/lem_pipeline/scripts/pipeline_reference_spectrum.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file()) / "experiments"))

from lem_pipeline.paths import D_TABLES, REFERENCE_DATA, ROOT  # noqa: E402
from lem_pipeline.reference import population_ids, read_csv  # noqa: E402
from lem_pipeline.spectrum import radial_spectrum, fit_beta, subset_spacing_km, focal_window  # noqa: E402

OUT = ROOT / "docs" / "work" / "2026-09-09-pipeline"
SUBSETS = REFERENCE_DATA / "2026-09-08-q1-data" / "A" / "subsets"
BANDS = {"4-100km": (4.0, 100.0), "4-200km": (4.0, 200.0), "10-200km": (10.0, 200.0)}


def main() -> None:
    all_rows, ids = population_ids(60.0)
    gshhg = {r["id"]: r["gshhg_id"] for r in read_csv(D_TABLES / "reference-landmasses.csv")}
    rows = []
    for lid in ids:
        gid = gshhg.get(lid, "")
        path = SUBSETS / f"GSHHG-{int(gid):06d}-gebco2026-s30.npz" if gid.isdigit() else None
        if path is None or not path.exists():
            rows.append({"id": lid, "name": all_rows[lid]["name"], "gshhg_id": gid, "window": "none", "status": "no subset"})
            continue
        d = np.load(path)
        z, lat, lon = d["z"].astype(float), d["lat"], d["lon"]
        dx, dy = subset_spacing_km(lat, lon)
        for wname, (zz, box) in (("subset", (z, None)), ("focal460", focal_window(z, lat, lon, 460.0))):
            k, p, c = radial_spectrum(zz, dx, dy)
            row = {"id": lid, "name": all_rows[lid]["name"], "gshhg_id": gid, "window": wname, "status": "ok",
                   "ny": zz.shape[0], "nx": zz.shape[1], "dx_km": round(dx, 4), "dy_km": round(dy, 4),
                   "extent_x_km": round(zz.shape[1] * dx, 1), "extent_y_km": round(zz.shape[0] * dy, 1),
                   "land_share": round(float((zz > 0).mean()), 4), "z_std_m": round(float(zz.std()), 1)}
            for bname, (lo, hi) in BANDS.items():
                f = fit_beta(k, p, c, lo, hi)
                row[f"beta_{bname}"] = round(f["beta"], 3) if np.isfinite(f["beta"]) else ""
                row[f"r2_{bname}"] = round(f["r2"], 3) if np.isfinite(f["r2"]) else ""
                row[f"nbins_{bname}"] = f["n_bins"]
            rows.append(row)
            print(f"{lid} {all_rows[lid]['name'][:24]:24s} {wname:8s} {zz.shape} beta4-100 {row['beta_4-100km']} beta4-200 {row['beta_4-200km']} beta10-200 {row['beta_10-200km']}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    keys = sorted({k for r in rows for k in r}, key=lambda s: (s not in ("id", "name", "gshhg_id", "window", "status"), s))
    with open(OUT / "reference-surface-spectrum.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "population": 34, "n_with_subset": sum(1 for r in rows if r["window"] == "subset"),
               "source": "references/data/2026-09-08-q1-data/A/subsets (GEBCO 2026 30 arc-second), D reference-landmasses.csv ids",
               "method": "2D FFT power per wavenumber cell, Hann taper, radial log bins, least squares in log-log; P(k) ∝ k^-beta",
               "evidence_state": "本项目由第一级数据计算", "quantiles": {}}
    for wname in ("subset", "focal460"):
        for bname in BANDS:
            vals = np.array([float(r[f"beta_{bname}"]) for r in rows if r.get("window") == wname and r.get(f"beta_{bname}", "") != ""])
            if vals.size:
                summary["quantiles"][f"{wname}_{bname}"] = {"n": int(vals.size), "p05": float(np.quantile(vals, .05)), "p25": float(np.quantile(vals, .25)),
                                                            "p50": float(np.median(vals)), "p75": float(np.quantile(vals, .75)), "p95": float(np.quantile(vals, .95)),
                                                            "min": float(vals.min()), "max": float(vals.max())}
    (OUT / "reference-surface-spectrum.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["quantiles"], indent=1))


if __name__ == "__main__":
    main()
