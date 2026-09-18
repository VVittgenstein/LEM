"""Twenty fixed configurations, 64 common seeds, two equal-weight losses."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import multiprocessing as mp
import time

import numpy as np
from scipy.stats import wasserstein_distance

from common.config import CALIBRATION_SEEDS, GAINS, STRETCHES, VERSION
from common.io import file_sha256, utc_now, write_csv, write_json
from common.metrics import shape_metrics
from common.numerics import shared_sample
from common.reference import ReferenceBundle, expected_log_metric
from common.runtime import worker_initializer
from .generator import generate_ellipse_mask


def _seed_results(seed: int, model: dict) -> list[dict]:
    common = shared_sample(seed)
    # Method A needs the reference model, not the overlay array.
    reference = ReferenceBundle(np.empty((0, 0)), model, {}, Path("."))
    rows = []
    for stretch in STRETCHES:
        for gain in GAINS:
            sample = generate_ellipse_mask(seed, reference, {"stretch": stretch, "gain": gain}, shared=common)
            metrics = shape_metrics(sample.mask)
            rows.append({"seed": seed, "stretch": stretch, "gain": gain, "area_km2": metrics["area_km2"],
                         "target_fraction": common.target_fraction, "axis_ratio": metrics["axis_ratio"],
                         "shoreline_development": metrics["shoreline_development"]})
    return rows


def configuration_score(rows: list[dict], model: dict) -> dict:
    areas = np.asarray([r["area_km2"] for r in rows])
    detail = {}
    for key in ("axis_ratio", "shoreline_development"):
        residuals = np.log([r[key] for r in rows]) - expected_log_metric(model, key, areas)
        ref = model["metrics"][key]
        distance = float(wasserstein_distance(residuals, ref["residuals"]))
        detail[key] = {"wasserstein_log_residual": distance, "normalizer": ref["loss_normalizer"],
                       "normalized_loss": distance / ref["loss_normalizer"],
                       "generated_p05_p50_p95": np.quantile([r[key] for r in rows], [.05, .5, .95]).tolist()}
    return {"loss": sum(d["normalized_loss"] for d in detail.values()), "detail": detail}


def calibrate(reference: ReferenceBundle, directory: Path, workers: int = 8, cpus: list[int] | None = None, log=print) -> dict:
    start = time.perf_counter()
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    # The limit includes the coordinator: at most seven children plus one parent.
    available = min(workers, len(cpus)) if cpus else workers
    if available == 1:
        for number, seed in enumerate(CALIBRATION_SEEDS, 1):
            rows.extend(_seed_results(seed, reference.model))
            log(f"calibration seed {number}/64", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=available-1, mp_context=mp.get_context("spawn"),
                                 initializer=worker_initializer, initargs=(cpus[1:] if cpus else None,)) as pool:
            futures = [pool.submit(_seed_results, seed, reference.model) for seed in CALIBRATION_SEEDS]
            for number, future in enumerate(as_completed(futures), 1):
                rows.extend(future.result())
                log(f"calibration seed {number}/64 ({time.perf_counter()-start:.1f}s)", flush=True)
    rows.sort(key=lambda r: (r["stretch"], r["gain"], r["seed"]))
    candidates = []
    for stretch in STRETCHES:
        for gain in GAINS:
            selected = [r for r in rows if r["stretch"] == stretch and r["gain"] == gain]
            candidates.append({"stretch": stretch, "gain": gain, "n": len(selected), **configuration_score(selected, reference.model)})
    best = min(candidates, key=lambda row: (row["loss"], row["stretch"], row["gain"]))
    result = {"created_utc": utc_now(), "version": VERSION, "seeds": list(CALIBRATION_SEEDS),
              "candidates": candidates, "selected": best, "wall_s": time.perf_counter()-start,
              "source_members": reference.model["member_ids"],
              "reference_model_sha256": file_sha256(reference.directory / "shape_model.json"),
              "reference_coverage_sha256": reference.manifest["coverage_array_sha256"],
              "loss_definition": "sum of two Wasserstein distances between log-metric area residuals / max(reference residual IQR,0.1)",
              "status": "selected_configuration", "visual_review": "pending",
              "note": "在固定搜索范围内选取误差最小配置；不据此宣布自然外观验收通过。"}
    write_csv(directory / "sample_statistics.csv", rows)
    write_csv(directory / "candidate_statistics.csv", [{"stretch": c["stretch"], "gain": c["gain"], "n": c["n"], "loss": c["loss"],
               **{k+"_loss": v["normalized_loss"] for k, v in c["detail"].items()}} for c in candidates])
    write_json(directory / "calibration.json", result)
    write_json(directory / "selected.json", {"stretch": best["stretch"], "gain": best["gain"], "loss": best["loss"], "version": VERSION,
                                            "reference_model_sha256": result["reference_model_sha256"],
                                            "reference_coverage_sha256": result["reference_coverage_sha256"]})
    log(f"selected stretch={best['stretch']} gain={best['gain']} loss={best['loss']:.4f}", flush=True)
    return result
