"""Calibrate the land-region generator against the 34-landmass reference shape statistics.

Scans the spectral exponent ``beta`` and the noise amplitude, draws the envelope axis ratio and the fill-ratio target
from the reference distributions, generates masks in shape-first mode, and compares the medians (and p25/p75) of
shoreline development, component count, PCA axis ratio and fill ratio with the reference. The best setting is written
to ``docs/work/2026-09-09-pipeline/landmask-calibration.json`` with the evidence state 本项目借鉴或合成改造.

Run: PYTHONPATH=experiments lem-env/python.exe experiments/lem_pipeline/scripts/pipeline_calibrate_landmask.py --samples 24
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file()) / "experiments"))

from lem_pipeline.distributions import QuantileTable  # noqa: E402
from lem_pipeline.landmask import LandmaskParams, generate_shape_first, mask_metrics  # noqa: E402
from lem_pipeline.paths import POP34_PACKAGE, ROOT  # noqa: E402
from lem_pipeline.checks import coastline_metrics, boundary_connected  # noqa: E402

OUT = ROOT / "docs" / "work" / "2026-09-09-pipeline"


def reference_tables() -> dict[str, QuantileTable]:
    with open(POP34_PACKAGE / "class4-shape-statistics-pop34.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    ref = {}
    for r in rows:
        if r["subset"] == "all":
            ref[r["statistic"]] = QuantileTable.from_row(r, r["statistic"])
    return ref


def sample_stats(beta: float, amp: float, n: int, rng: np.random.Generator, ref: dict) -> list[dict]:
    pca_tab = ref["pca_ratio"]
    out = []
    for i in range(n):
        ar = float(np.clip(pca_tab.sample(rng), 1.05, 4.0))
        fill = float("nan")
        p = LandmaskParams(axis_ratio=ar, orientation_deg=float(rng.uniform(0, 180)), beta=beta, noise_amplitude=amp, seed=int(rng.integers(1 << 30)))
        land, info = generate_shape_first(p)
        m = mask_metrics(land)
        # D-comparable shoreline development on the focal component's coastal envelope (Crofton)
        from scipy import ndimage as ndi
        lab, _ = ndi.label(land, ndi.generate_binary_structure(2, 1))
        sizes = np.bincount(lab.ravel()); sizes[0] = 0
        focal = lab == sizes.argmax()
        cm = coastline_metrics(focal, 1.0)
        out.append({"beta": beta, "amp": amp, "axis_ratio_in": ar, "fill_target": fill, "fill": m["fill_ratio_main"], "occupancy": info["occupancy_achieved"],
                    "components": m["components"], "pca": m["pca_ratio_main"], "sd_crofton": cm["shoreline_development_crofton"], "sd_grid": cm["shoreline_development_grid"]})
    return out


def score(samples: list[dict], ref: dict) -> dict:
    def q(vals, p):
        return float(np.quantile(vals, p))
    comp = {"pca_ratio": [s["pca"] for s in samples], "shoreline_development_crofton": [s["sd_crofton"] for s in samples],
            "focal_components_4": [s["components"] for s in samples], "fill_ratio_area_over_min_square": [s["fill"] for s in samples]}
    total = 0.0
    detail = {}
    for k, vals in comp.items():
        r = ref[k]
        err = 0.0
        for lv, w in ((0.25, 1.0), (0.5, 2.0), (0.75, 1.0)):
            rv = r.quantile(lv)
            sv = q(vals, lv)
            e = abs(np.log((sv + 1e-6) / (rv + 1e-6)))
            err += w * e
        detail[k] = {"sample_p25_p50_p75": [q(vals, .25), q(vals, .5), q(vals, .75)], "ref_p25_p50_p75": [r.quantile(.25), r.quantile(.5), r.quantile(.75)], "log_error": err}
        total += err
    return {"total": total, "detail": detail}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--betas", default="3.0,3.5,4.0,4.5")
    ap.add_argument("--amps", default="0.1,0.2,0.3,0.45")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out-name", default="landmask-calibration.json")
    a = ap.parse_args()
    ref = reference_tables()
    rng = np.random.default_rng(a.seed)
    results = []
    for beta in [float(x) for x in a.betas.split(",")]:
        for amp in [float(x) for x in a.amps.split(",")]:
            s = sample_stats(beta, amp, a.samples, rng, ref)
            sc = score(s, ref)
            occ = [x["occupancy"] for x in s]
            results.append({"beta": beta, "amp": amp, "score": sc["total"], "detail": sc["detail"],
                            "occupancy_p50": float(np.median(occ)), "share_reaching_0.5": float(np.mean(np.asarray(occ) >= 0.5))})
            print(f"beta {beta:.1f} amp {amp:.2f} score {sc['total']:.3f} | sd {sc['detail']['shoreline_development_crofton']['sample_p25_p50_p75'][1]:.2f} vs {ref['shoreline_development_crofton'].quantile(.5):.2f} | comps {sc['detail']['focal_components_4']['sample_p25_p50_p75'][1]:.0f} vs {ref['focal_components_4'].quantile(.5):.0f} | pca {sc['detail']['pca_ratio']['sample_p25_p50_p75'][1]:.2f} vs {ref['pca_ratio'].quantile(.5):.2f} | fill {sc['detail']['fill_ratio_area_over_min_square']['sample_p25_p50_p75'][1]:.2f} vs {ref['fill_ratio_area_over_min_square'].quantile(.5):.2f} | occ≥0.5 {results[-1]['share_reaching_0.5']:.2f}", flush=True)
    best = min(results, key=lambda r: r["score"])
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"created_utc": datetime.now(timezone.utc).isoformat(), "population": 34, "samples_per_setting": a.samples,
               "reference": "docs/work/2026-09-08-q1-data/merged/data-package/pop34/class4-shape-statistics-pop34.csv",
               "best": best, "all": results, "evidence_state": "本项目借鉴或合成改造",
               "notes": "轴比与填充比例从参考分布抽取；beta 与噪声幅度为标定量；分值为 p25/p50/p75 的对数误差加权和"}
    (OUT / a.out_name).write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print("best:", {k: best[k] for k in ("beta", "amp", "score", "occupancy_p50", "share_reaching_0.5")})


if __name__ == "__main__":
    main()
