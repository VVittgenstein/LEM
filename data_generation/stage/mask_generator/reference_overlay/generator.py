"""Method B. Fixed equal-weight overlay and fixed noise; no fitting dependency."""
import numpy as np
from scipy.ndimage import map_coordinates

from common.config import COEFFICIENTS, PIXELS_PER_UNIT, TEMPLATE_SIZE, MaskResult, SharedSample
from common.numerics import combine, local_coordinates, normalize_envelope, shared_sample
from common.reference import ReferenceBundle


def generate_reference_mask(seed: int, reference: ReferenceBundle, target_fraction: float | None = None,
                            shared: SharedSample | None = None) -> MaskResult:
    common = shared if shared is not None else shared_sample(seed, target_fraction)
    if common.seed != seed:
        raise ValueError("shared sample seed mismatch")
    if target_fraction is not None and abs(target_fraction - common.target_fraction) > 1e-12:
        raise ValueError("shared target fraction mismatch")
    x, y = local_coordinates(common)
    # One output cell samples one template pixel; normalized span 1 maps to 500 pixels.
    rows, cols = y + (TEMPLATE_SIZE-1)/2, x + (TEMPLATE_SIZE-1)/2
    raw = map_coordinates(reference.template, [rows, cols], order=1, mode="constant", cval=0.0, prefilter=False)
    envelope, normalization = normalize_envelope(raw)
    combined, mask, threshold = combine(envelope, common, gain=1.0)
    params = {"envelope": "equal-weight aligned reference coverage", "members": reference.model["n"],
              "member_ids": reference.model["member_ids"], "gain": 1.0, "coefficients": list(COEFFICIENTS),
              "pixels_per_relative_unit": PIXELS_PER_UNIT, "template_size": TEMPLATE_SIZE,
              "sampling": "rotate/translate the output coordinates, then bilinear sample the overlay",
              "normalization": normalization, "calibration_applied": False,
              "template_array_sha256": reference.manifest["coverage_array_sha256"],
              "evidence_state": "参考形状等权叠加；使用固定工程参数，不做统计校准；外观待检查"}
    return MaskResult("reference_overlay", common, envelope, combined, mask, threshold, params)

