from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from common.config import COEFFICIENTS, POPULATION, REFERENCE_MASKS, WINDOWS
from common.io import array_sha256, read_csv
from common.numerics import allowed_region, exact_mask, normalize_envelope, random_fields, rng_for, shared_sample
from common.reference import ReferenceBundle, fit_reference_model
from common.render import decode_mask_png, save_mask_png
from ellipse.calibrate import configuration_score
from ellipse.generator import generate_ellipse_mask
from reference_overlay.generator import generate_reference_mask


def fixture_reference():
    yy, xx = np.mgrid[:1024, :1024]
    template = np.exp(-((xx-512)/210)**2-((yy-512)/120)**2)
    rows = [{"id": str(i), "area_km2": 5000+12000*i, "axis_ratio": 1.2+.02*i,
             "shoreline_development": 1.4+.01*i} for i in range(34)]
    return ReferenceBundle(template, fit_reference_model(rows), {"coverage_array_sha256": array_sha256(template)}, Path("."))


class RandomFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fields = random_fields(23019)

    def test_mean_std_and_replay(self):
        replay = random_fields(23019)
        for window in WINDOWS:
            field = self.fields[window]
            self.assertEqual(field.shape, (500, 500))
            self.assertLess(abs(field.mean()), 1e-13)
            self.assertLess(abs(field.std()-1), 1e-13)
            self.assertTrue(np.array_equal(field, replay[window]))

    def test_window_average_adjacent_correlation(self):
        for window in WINDOWS:
            field = self.fields[window]
            correlation = np.corrcoef(field[:, 1:].ravel(), field[:, :-1].ravel())[0, 1]
            self.assertLess(abs(correlation-(window-1)/window), .025)

    def test_independent_scale_streams(self):
        for first, second in ((1, 5), (5, 25), (1, 25)):
            corr = np.corrcoef(self.fields[first].ravel(), self.fields[second].ravel())[0, 1]
            self.assertLess(abs(corr), .04)
        self.assertFalse(np.array_equal(rng_for(1, "noise_1").normal(size=30), rng_for(1, "noise_5").normal(size=30)))

    def test_padding_is_true_local_average_at_corner(self):
        base = rng_for(23019, "noise_25").standard_normal((524, 524))
        # Explicit sliding-window evaluation has no boundary padding in its support.
        from numpy.lib.stride_tricks import sliding_window_view
        direct = sliding_window_view(base, (25, 25)).mean(axis=(-1, -2))
        direct = (direct-direct.mean())/direct.std()
        self.assertTrue(np.allclose(direct, self.fields[25], atol=1e-13))


class ThresholdAndImageTests(unittest.TestCase):
    def test_equal_value_tie_order_and_ocean_band(self):
        mask, record = exact_mask(np.ones((8, 8)), 7, band=1)
        self.assertEqual(np.flatnonzero(mask).tolist(), [9, 10, 11, 12, 13, 14, 17])
        self.assertEqual(record["actual_cells"], 7)
        self.assertFalse(np.any(mask[~allowed_region((8, 8), 1)]))

    def test_threshold_rejects_invalid_inputs(self):
        for values, count in ((np.ones((8, 8)), 37), (np.full((8, 8), np.nan), 4)):
            with self.assertRaises(ValueError):
                exact_mask(values, count, band=1)
        with self.assertRaises(ValueError):
            shared_sample(1, .61)

    def test_envelope_minmax(self):
        output, record = normalize_envelope(np.array([[-2, 0], [1, 2]]))
        self.assertEqual(output.min(), 0)
        self.assertEqual(output.max(), 1)
        self.assertEqual(record["raw_min"], -2)
        with self.assertRaises(ValueError):
            normalize_envelope(np.ones((2, 2)))

    def test_png_exact_size_colors_orientation_and_roundtrip(self):
        mask = np.zeros((500, 500), bool)
        mask[1, 4] = mask[480:490, 150:201] = True
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mask.png"
            save_mask_png(path, mask)
            self.assertEqual(Image.open(path).size, (500, 500))
            self.assertEqual(len(Image.open(path).getcolors()), 2)
            self.assertTrue(np.array_equal(mask, decode_mask_png(path)))


class MethodAndSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = fixture_reference()

    def test_selected_population_has_34_unique_available_focal_inputs(self):
        members = read_csv(POPULATION)
        self.assertEqual(len(members), 34)
        self.assertEqual(len({m["id"] for m in members}), 34)
        for member in members:
            self.assertTrue((REFERENCE_MASKS / (member["id"]+".npz")).is_file())

    def test_paired_fields_and_pose_independent_of_method_order(self):
        before = generate_reference_mask(1001, self.reference)
        ellipse = generate_ellipse_mask(1001, self.reference, {"stretch": 1, "gain": 2})
        after = generate_reference_mask(1001, self.reference)
        self.assertEqual(before.shared.describe(), ellipse.shared.describe())
        self.assertTrue(np.array_equal(before.mask, after.mask))
        for window in WINDOWS:
            self.assertTrue(np.array_equal(before.shared.fields[window], ellipse.shared.fields[window]))

    def test_b_does_not_call_fitting_or_calibration_and_keeps_coefficients(self):
        with patch("ellipse.calibrate.calibrate", side_effect=AssertionError("calibration forbidden")), \
             patch("common.reference.fit_reference_model", side_effect=AssertionError("fitting forbidden")), \
             patch("ellipse.generator.generate_ellipse_mask", side_effect=AssertionError("method A forbidden")):
            result = generate_reference_mask(111, self.reference)
        self.assertFalse(result.parameters["calibration_applied"])
        self.assertEqual(result.parameters["coefficients"], list(COEFFICIENTS))
        self.assertEqual(result.parameters["members"], 34)

    def test_masks_shape_dtype_area_extremes_and_band(self):
        for fraction in (.5, .6):
            common = shared_sample(98, fraction)
            for result in (generate_ellipse_mask(98, self.reference, {"stretch": 1.25, "gain": .5}, shared=common),
                           generate_reference_mask(98, self.reference, shared=common)):
                self.assertEqual(result.mask.shape, (500, 500))
                self.assertEqual(result.mask.dtype, np.bool_)
                self.assertEqual(result.mask.sum(), round(fraction*250000))
                self.assertFalse(result.mask[~allowed_region()].any())

    def test_log_area_fit_residuals_and_zero_distribution_loss(self):
        rows = [{"id": str(i), "area_km2": 10**(i/5+2), "axis_ratio": np.exp(.2)*10**((i/5+2)*.15),
                 "shoreline_development": np.exp(.3)*10**((i/5+2)*.12)} for i in range(34)]
        model = fit_reference_model(rows)
        self.assertAlmostEqual(model["metrics"]["axis_ratio"]["slope"], .15, places=12)
        self.assertAlmostEqual(model["metrics"]["shoreline_development"]["intercept"], .3, places=12)
        self.assertEqual(model["metrics"]["axis_ratio"]["loss_normalizer"], .1)
        self.assertLess(configuration_score(rows, model)["loss"], 1e-12)
