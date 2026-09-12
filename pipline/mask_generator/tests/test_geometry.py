import unittest

import numpy as np
from shapely.affinity import rotate, scale, translate
from shapely.geometry import Polygon, box

from common.contours import extract_contours, rasterize_contours
from common.metrics import full_metrics, pca_shape, shape_metrics
from common.reference import align_geometry, footprint, geometry_diameter, rasterize_aligned


class ReferenceAlignmentTests(unittest.TestCase):
    def test_area_centroid_longest_span_and_axis_preserved(self):
        shape = Polygon([(0, 0), (9, 0), (9, 1), (4, 3), (0, 2)])
        aligned, info = align_geometry(shape)
        self.assertLess(np.linalg.norm(aligned.centroid.coords[0]), 1e-12)
        self.assertAlmostEqual(geometry_diameter(aligned), 1.0, places=12)
        _, second = align_geometry(aligned)
        self.assertAlmostEqual(info["native_axis_ratio"], second["native_axis_ratio"], places=10)
        self.assertAlmostEqual(second["alignment_angle_deg"], 0.0, places=8)

    def test_asymmetric_alignment_invariant_to_pose_and_scale(self):
        shape = Polygon([(0, 0), (8, 0), (8, 1), (3, 3), (0, 2)])
        first, _ = align_geometry(shape)
        changed = translate(rotate(scale(shape, xfact=71, yfact=71, origin=(0, 0)), 137, origin=(0, 0)), 893, -151)
        second, _ = align_geometry(changed)
        self.assertLess(first.symmetric_difference(second).area, 1e-10)
        self.assertTrue(np.array_equal(rasterize_aligned(first), rasterize_aligned(second)))

    def test_symmetric_fallback_is_deterministic(self):
        shape = box(-4, -1, 4, 1)
        first, record = align_geometry(shape)
        second, other = align_geometry(shape)
        self.assertEqual(record, other)
        self.assertIn("symmetric fallback", record["axis_sign_rule"])
        self.assertEqual(first.wkb, second.wkb)

    def test_lake_filled_bay_retained_in_reference_only(self):
        lake = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], holes=[[(4, 4), (6, 4), (6, 6), (4, 6)]])
        self.assertEqual(footprint(lake).area, 100)
        bay = box(0, 0, 10, 10).difference(box(4, 5, 6, 11))
        self.assertEqual(footprint(bay).area, bay.area)


class MaskGeometryTests(unittest.TestCase):
    def test_rectangle_pca_and_perimeter(self):
        mask = np.zeros((120, 120), bool)
        mask[40:60, 20:80] = True
        metrics = shape_metrics(mask)
        self.assertEqual(metrics["area_km2"], 1200)
        self.assertAlmostEqual(metrics["axis_ratio"], 3.0, places=12)
        self.assertEqual(metrics["coast_grid_km"], 160)

    def test_circle_crofton_coefficient_near_one(self):
        yy, xx = np.mgrid[:250, :250] + .5
        mask = (xx-125)**2 + (yy-125)**2 < 80**2
        metrics = shape_metrics(mask)
        self.assertAlmostEqual(metrics["axis_ratio"], 1, places=10)
        self.assertLess(abs(metrics["shoreline_development"]-1), .015)

    def test_closed_water_does_not_change_outer_coast_but_changes_area(self):
        solid = np.zeros((80, 80), bool)
        solid[15:65, 15:65] = True
        hole = solid.copy()
        hole[35:45, 35:45] = False
        a, b = shape_metrics(solid), shape_metrics(hole)
        self.assertEqual(a["coast_crofton_km"], b["coast_crofton_km"])
        self.assertEqual(a["area_km2"]-b["area_km2"], 100)
        self.assertEqual(full_metrics(hole)["closed_water_cells"], 100)
        self.assertFalse(hole[40, 40])

    def test_bay_multiple_components_and_internal_hole(self):
        mask = np.zeros((90, 90), bool)
        mask[15:60, 15:55] = True
        mask[40:60, 30:40] = False  # Bay open to the exterior.
        mask[25:28, 25:28] = False  # Closed water.
        mask[65:72, 65:73] = True
        original = mask.copy()
        metrics = full_metrics(mask)
        self.assertEqual(metrics["components_4"], 2)
        self.assertEqual(metrics["closed_water_cells"], 9)
        self.assertLess(metrics["largest_component_fraction"], 1)
        self.assertTrue(np.array_equal(original, mask))

    def test_contours_exact_with_holes_islands_and_diagonal_contacts(self):
        mask = np.zeros((16, 18), bool)
        mask[2:11, 3:12] = True
        mask[5:8, 6:9] = False
        mask[11, 12] = True  # Point contact, separate four-connected cell.
        mask[13, 15] = True
        contours = extract_contours(mask)
        self.assertTrue(contours["valid"])
        self.assertEqual(contours["area_km2"], int(mask.sum()))
        self.assertEqual(contours["interior_ring_count"], 1)
        self.assertEqual(contours["component_count"], 3)
        self.assertTrue(np.array_equal(mask, rasterize_contours(contours)))
        for component in contours["components"]:
            for ring in [component["outer"], *component["holes"]]:
                self.assertEqual(ring[0], ring[-1])

    def test_contours_single_cell_corners_and_scaled_coordinates(self):
        mask = np.zeros((5, 7), bool)
        mask[1, 3] = True
        contours = extract_contours(mask, dx=2)
        self.assertEqual(contours["area_km2"], 4)
        self.assertEqual(set(map(tuple, contours["components"][0]["outer"])), {(6, 2), (8, 2), (8, 4), (6, 4)})
        self.assertTrue(np.array_equal(mask, rasterize_contours(contours)))

    def test_empty_metrics_rejected(self):
        with self.assertRaises(ValueError):
            pca_shape(np.zeros((8, 8), bool))
