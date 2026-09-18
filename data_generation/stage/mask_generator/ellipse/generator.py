"""Method A. It consumes a selected calibration; it never calibrates during sampling."""
import numpy as np

from common.config import COEFFICIENTS, SIZE, MaskResult, SharedSample
from common.numerics import combine, local_coordinates, normalize_envelope, rng_for, shared_sample
from common.reference import ReferenceBundle, expected_log_metric


def generate_ellipse_mask(seed: int, reference: ReferenceBundle, calibration: dict,
                          target_fraction: float | None = None, shared: SharedSample | None = None) -> MaskResult:
    common = shared if shared is not None else shared_sample(seed, target_fraction)
    if common.seed != seed:
        raise ValueError("shared sample seed mismatch")
    if target_fraction is not None and abs(target_fraction - common.target_fraction) > 1e-12:
        raise ValueError("shared target fraction mismatch")
    model = reference.model
    entry = model["metrics"]["axis_ratio"]
    index = int(rng_for(seed, "ellipse_residual").integers(model["n"]))
    area = common.target_fraction * SIZE * SIZE
    raw_ratio = float(np.exp(expected_log_metric(model, "axis_ratio", area) + entry["residuals"][index]))
    stretch = float(calibration["stretch"])
    gain = float(calibration["gain"])
    ratio = float(max(1.0, raw_ratio) ** stretch)
    b = float(np.sqrt(area / (np.pi * ratio)))
    a = b * ratio
    x, y = local_coordinates(common)
    raw = 1.0 - np.sqrt((x/a)**2 + (y/b)**2)
    envelope, normalization = normalize_envelope(raw)
    combined, mask, threshold = combine(envelope, common, gain)
    bounds = model["area_range_km2"]
    params = {"envelope": "1-sqrt((x/a)^2+(y/b)^2)", "semi_major_km": a, "semi_minor_km": b,
              "raw_reference_axis_ratio": raw_ratio, "axis_ratio": ratio, "axis_ratio_floor": 1.0,
              "residual_member_id": model["member_ids"][index], "stretch": stretch, "gain": gain,
              "coefficients": [gain*c for c in COEFFICIENTS], "normalization": normalization,
              "reference_area_extrapolation": bool(not bounds[0] <= area <= bounds[1]),
              "calibration_applied": True, "calibration_configuration": calibration,
              "evidence_state": "参考形状校准；随机场与位置设置为工程假设；外观待检查"}
    return MaskResult("ellipse", common, envelope, combined, mask, threshold, params)

