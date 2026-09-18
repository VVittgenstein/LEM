"""Export and verify the concrete results without changing any mask cells."""
from pathlib import Path

import numpy as np

from .config import BAND, DX_KM, SIZE, VERSION, WINDOWS
from .contours import extract_contours, rasterize_contours
from .io import array_sha256, read_json, utc_now, write_json
from .metrics import full_metrics
from .numerics import allowed_region
from .render import (OCEAN, PLATFORM, contour_png, decode_mask_png,
                     save_mask_png, scalar_png)


def export_sample(result, reference, directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    arrays = {"mask": result.mask, "envelope": result.envelope, "combined": result.combined,
              **{f"noise_{window}": result.shared.fields[window] for window in WINDOWS}}
    hashes = {}
    for name, array in arrays.items():
        np.save(directory / f"{name}.npy", array, allow_pickle=False)
        hashes[name] = array_sha256(array)
        if name == "mask":
            save_mask_png(directory / "mask.png", array)
        else:
            scalar_png(directory / f"{name}.png", array, "noise" if name.startswith("noise_") else name)
    contours = extract_contours(result.mask)
    write_json(directory / "contours.json", contours)
    contour_png(directory / "contours.png", result.mask, contours)
    metrics = full_metrics(result.mask)
    allowed = allowed_region(result.mask.shape, BAND)
    metrics["excluded_band_cells_above_final_threshold"] = int(np.count_nonzero(
        ~allowed & (result.combined > result.threshold["value"])))
    config = {"created_utc": utc_now(), "version": VERSION, "method": result.method,
              **result.shared.describe(), "parameters": result.parameters, "threshold": result.threshold,
              "cell_km": DX_KM, "ocean_band_cells": BAND, "array_sha256": hashes,
              "reference": {"version": reference.manifest["version"], "source": reference.manifest["source"],
                            "member_ids": reference.manifest["member_ids"],
                            "coverage_array_sha256": reference.manifest["coverage_array_sha256"],
                            "manifest_relative_path": "../../reference/manifest.json"},
              "coordinates": {"npy": "row 0 at bottom; x=column+0.5 km; y=row+0.5 km",
                              "png": "top image row equals last NPY row; decode by reversing the row order",
                              "contours": "exact cell corners in local kilometres"},
              "png_palette": {"ocean_rgb": list(OCEAN), "platform_rgb": list(PLATFORM)},
              "preview_ranges": {"envelope": [0, 1], "noise": [-3, 3], "combined": [-.25, 1.25]},
              "preview_note": "连续场图片使用固定色标，超出色标范围的颜色截断；NPY 保留完整 float64 数值。",
              "engineering_settings": ["随机场窗口和系数", "中心±25 km", "长轴方向判定的对称回退规则",
                                       "参考最长跨度1对应500像素", "阈值同值按行优先格子索引选择"]}
    checks = {"shape_500_by_500": result.mask.shape == (SIZE, SIZE), "boolean_dtype": result.mask.dtype == np.bool_,
              "exact_target_area": int(result.mask.sum()) == round(result.shared.target_fraction*SIZE*SIZE),
              "fraction_50_to_60_percent": .5 <= result.mask.mean() <= .6,
              "ocean_band_empty": not np.any(result.mask[~allowed]),
              "png_exact_roundtrip": np.array_equal(decode_mask_png(directory / "mask.png"), result.mask),
              "contours_valid": contours["valid"], "contour_area_exact": contours["area_km2"] == int(result.mask.sum()),
              "contour_exact_roundtrip": np.array_equal(rasterize_contours(contours), result.mask)}
    longest = max(metrics["longest_straight_band_contact_km"].values())
    issues = []
    if longest >= 25:
        issues.append({"code": "continuous_band_contact", "observation": f"外圈海洋带内缘存在连续 {longest} km 的接触。",
                       "threshold_basis": "25 km 为本次自动标记的工程阈值；自然外观仍需图像检查。"})
    status = {"execution": "complete" if all(checks.values()) else "failed_geometry_checks",
              "geometry_checks": checks, "issues": issues,
              "statistical_comparison": "calibrated_on_two_metrics" if result.method == "ellipse" else "diagnostic_only_no_calibration",
              "visual_review": {"state": "pending_image_review", "user_acceptance": "pending"},
              "postprocessing": "none: no filling, component deletion, smoothing or cell edits"}
    write_json(directory / "config.json", config)
    write_json(directory / "metrics.json", metrics)
    write_json(directory / "status.json", status)
    if not all(checks.values()):
        raise RuntimeError(f"geometry checks failed for {directory}: {checks}")
    return {"seed": result.shared.seed, "method": result.method, "relative_path": f"seed{result.shared.seed}/{result.method}",
            "config": config, "metrics": metrics, "status": status}


def load_samples(output: Path, seeds: list[int]) -> list[dict]:
    from .config import METHODS
    return [{"seed": seed, "method": method, "relative_path": f"seed{seed}/{method}",
             **{key: read_json(output / f"seed{seed}" / method / f"{key}.json") for key in ("config", "metrics", "status")}}
            for seed in seeds for method in METHODS]


def audit_results(output: Path, reference, selected: dict, seeds: list[int], log=print) -> dict:
    from ellipse.generator import generate_ellipse_mask
    from reference_overlay.generator import generate_reference_mask
    from .numerics import shared_sample
    from .config import CALIBRATION_SEEDS, GAINS, METHODS, STRETCHES, TEMPLATE_SIZE
    from .io import read_csv

    checks = []
    members = reference.manifest["member_ids"]
    count = np.zeros((TEMPLATE_SIZE, TEMPLATE_SIZE), dtype=np.uint8)
    alignment = read_json(output / "reference/alignment.json")
    aligned_hashes_match = True
    for member in alignment:
        aligned = np.load(output / "reference/aligned" / member["id"] / "mask.npy", allow_pickle=False)
        aligned_hashes_match &= array_sha256(aligned) == member["aligned_mask_sha256"]
        count += aligned.astype(np.uint8)
    checks.append({"method": "reference", "all_34_members": len(members) == len(set(members)) == 34
                   and [m["id"] for m in alignment] == members,
                   "alignment_centers": all(np.linalg.norm(m["aligned_centroid"]) < 1e-10 for m in alignment),
                   "aligned_hashes": bool(aligned_hashes_match),
                   "equal_weights": all(m["weight"] == 1/34 for m in alignment),
                   "overlay_reconstruction": np.array_equal(count.astype(float)/34, reference.template)})
    calibration_rows = read_csv(output / "calibration/sample_statistics.csv")
    expected_search = {(stretch, gain, seed) for stretch in STRETCHES for gain in GAINS for seed in CALIBRATION_SEEDS}
    actual_search = {(float(r["stretch"]), float(r["gain"]), int(r["seed"])) for r in calibration_rows}
    calibration = read_json(output / "calibration/calibration.json")
    minimum = min(calibration["candidates"], key=lambda c: (c["loss"], c["stretch"], c["gain"]))
    checks.append({"method": "calibration", "all_1280_candidate_samples": len(calibration_rows) == 1280
                   and actual_search == expected_search,
                   "minimum_loss_selected": all(selected[k] == minimum[k] for k in ("stretch", "gain", "loss")),
                   "final_seeds_disjoint": not set(seeds).intersection(CALIBRATION_SEEDS)})
    for seed in seeds:
        shared = shared_sample(seed)
        pair = [generate_ellipse_mask(seed, reference, selected, shared=shared),
                generate_reference_mask(seed, reference, shared=shared)]
        configs = []
        for result in pair:
            directory = output / f"seed{seed}" / result.method
            config = read_json(directory / "config.json")
            configs.append(config)
            stored = np.load(directory / "mask.npy", allow_pickle=False)
            checks.append({"seed": seed, "method": result.method,
                           "mask_replay": np.array_equal(stored, result.mask),
                           "png_roundtrip": np.array_equal(decode_mask_png(directory / "mask.png"), stored),
                           "contour_roundtrip": np.array_equal(rasterize_contours(read_json(directory / "contours.json")), stored),
                           "stored_array_hashes": all(array_sha256(np.load(directory / f"{name}.npy", allow_pickle=False)) == expected
                                                      for name, expected in config["array_sha256"].items()),
                           "noise_replay": all(array_sha256(shared.fields[w]) == config["array_sha256"][f"noise_{w}"] for w in WINDOWS)})
        checks.append({"seed": seed, "method": "pair", "shared_parameters": all(configs[0][k] == configs[1][k]
                       for k in ("seed", "target_fraction", "angle_deg", "center_x_km", "center_y_km")),
                       "shared_noise": all(configs[0]["array_sha256"][f"noise_{w}"] == configs[1]["array_sha256"][f"noise_{w}"] for w in WINDOWS),
                       "method_b_fixed": configs[1]["parameters"]["calibration_applied"] is False
                       and configs[1]["parameters"]["coefficients"] == [.005, .015, .05]})
        log(f"audit seed {seed}: replay, PNG, contours and paired fields checked", flush=True)
    masks = sorted(output.glob("seed*/*/mask.npy"))
    pictures = sorted(output.glob("seed*/*/mask.png"))
    actual = {p.parent.relative_to(output).as_posix() for p in masks}
    expected = {f"seed{s}/{method}" for s in seeds for method in METHODS}
    counts = {"mask_count": len(masks), "primary_png_count": len(pictures), "expected_count": len(seeds)*2,
              "exact_sample_set": actual == expected, "png_count_matches": len(pictures) == len(seeds)*2}
    passed = all(all(v is True for k, v in check.items() if k not in ("seed", "method")) for check in checks)
    result = {"created_utc": utc_now(), "passed": passed and counts["exact_sample_set"] and counts["png_count_matches"],
              "counts": counts, "checks": checks, "scope": "执行和几何核查；自然外观的用户验收另行记录。"}
    write_json(output / "audit.json", result)
    if not result["passed"]:
        raise RuntimeError("final output audit failed")
    return result
