"""Sampling gates, non-deterministic preferences and saved-field geometry contracts."""
import unittest
from unittest.mock import patch
import numpy as np
from data_generation.stage.basin_subsidence.common import CHECKS, save, rng
from data_generation.stage.basin_subsidence.sampling_geometry import (
    FullSupport, Platform, mask_polygon, shapely, rotation, to_source, to_local, WORLD, window_polygon)
from data_generation.stage.basin_subsidence.window import (
    DESIGN, gate, weight_terms, selection_probabilities, propose_paths, candidate_metrics, choose_window)


class AreaAndProbabilityTests(unittest.TestCase):
    def test_normal_and_small_event_gates(self):
        self.assertEqual(gate(9.99, 30, 100), 'below_minimum')
        self.assertEqual(gate(10., 30, 100), 'eligible')
        self.assertEqual(gate(70., 200, 100), 'eligible')
        self.assertEqual(gate(70.01, 200, 100), 'above_maximum')
        self.assertEqual(gate(.1, 9., 100), 'eligible')
        self.assertEqual(gate(0., 9., 100), 'no_overlap')
        self.assertEqual(gate(9., 10., 100), 'below_minimum')

    def test_every_size_has_strong_central_attenuation(self):
        for area in (1e-10, 4., 50., 100., 10000.):
            values = [weight_terms(1., area, 100., .5, d)['position_factor'] for d in (0., .25, .5, .75, 1.)]
            self.assertTrue(np.all(np.diff(values) < 0))
            self.assertLessEqual(values[-1], np.exp(-6.))
            self.assertGreater(values[-1], 0.)
        values = [weight_terms(1., area, 100., .5, .3)['position_factor'] for area in (1., 10., 100., 1000.)]
        self.assertTrue(np.all(np.diff(values) < 0))

    def test_coverage_attenuation_starts_at_fifty_percent(self):
        values = [weight_terms(c, 200., 100., .5, .3)['coverage_factor'] for c in (10., 30., 50., 55., 60., 70.)]
        np.testing.assert_array_equal(values[:3], np.ones(3))
        self.assertTrue(np.all(np.diff(values[2:]) < 0))
        self.assertGreater(values[-1], 0.)

    def test_weighted_draw_has_no_single_depth_assignment(self):
        logs = [weight_terms(8., 9., 100., 1., d)['log_weight'] for d in (0.1, .4, .8)]
        probabilities = selection_probabilities(logs)
        np.testing.assert_allclose(probabilities, selection_probabilities(np.array(logs)+1000), atol=1e-13)
        self.assertAlmostEqual(probabilities.sum(), 1.)
        self.assertTrue(np.all(probabilities > 0.))
        draws = np.random.default_rng(81).choice(3, size=60000, p=probabilities)
        frequencies = np.bincount(draws, minlength=3)/len(draws)
        self.assertTrue(np.all(frequencies > 0.))
        np.testing.assert_allclose(frequencies, probabilities, atol=.007)


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = CHECKS/'test_window_fixture'
        cls.folder.mkdir(parents=True, exist_ok=True)
        x, y = np.meshgrid(np.arange(-2, 3)*40., np.arange(-2, 3)*40.)
        points = np.column_stack([x.ravel(), y.ravel()])
        active = np.all(points == 0, axis=1)
        np.savez(cls.folder/'mesh.npz', points_km=points, active=active,
                 reference_u_m_per_yr=-.001*active)
        np.savez(cls.folder/'reference.npz', x_km=np.arange(-80, 81), y_km=np.arange(-80, 81))
        np.savez(cls.folder/'time_model.npz', identity=np.array([17.]))
        cls.event = dict(seed=123, event_seed=789, event_id='synthetic-sampling-fixture')
        save(cls.folder/'event.json', cls.event)
        cls.field = FullSupport(cls.folder)
        cls.land = object.__new__(Platform)
        cls.land.mask = np.zeros((500, 500), dtype=bool)
        cls.land.mask[80:420, 90:410] = True
        cls.land.mask[80:230, 300:410] = False
        cls.land.mask[260:280, 180:205] = False
        cls.land.geometry = mask_polygon(cls.land.mask)
        cls.land.outer_geometry = shapely.Polygon(cls.land.geometry.exterior)
        cls.land.area = cls.land.geometry.area
        cls.land.distance = np.zeros((500, 500))
        yy, xx = np.nonzero(cls.land.mask)
        cls.land.distance[yy, xx] = shapely.distance(shapely.points(xx+.5, yy+.5), cls.land.geometry.boundary)
        cls.land.maximum_distance = float(cls.land.distance.max())
        cls.land.path = cls.folder/'base.npz'
        np.savez(cls.land.path, mask=cls.land.mask)

    def test_support_matches_actual_evaluator(self):
        points = np.random.default_rng(616).uniform(-90, 90, (25000, 2))
        nonzero = self.field.mapper.evaluate(self.field.rate, self.field.mapper.weights(points)) != 0
        inside = shapely.contains_xy(self.field.geometry, points[:, 0], points[:, 1])
        np.testing.assert_array_equal(nonzero, inside)
        self.assertLess(self.field.boundary_max_rate, 1e-12)

    def test_platform_union_keeps_holes_and_exact_area(self):
        self.assertAlmostEqual(self.land.area, self.land.mask.sum())
        self.assertFalse(self.land.geometry.contains(shapely.Point(190, 270)))
        self.assertAlmostEqual(self.land.distance[280, 190], .5)

    def test_paths_cover_entire_traversal_and_stratify_depths(self):
        config = dict(DESIGN, paths_per_block=12)
        paths = list(propose_paths(self.field, rng(346, 501), config))
        for path, centers, fractions, matrix in paths:
            self.assertFalse(self.field.geometry.intersects(window_polygon(path['start_center_source_km'], matrix)))
            self.assertFalse(self.field.geometry.intersects(window_polygon(path['end_center_source_km'], matrix)))
            np.testing.assert_array_equal((fractions*24).astype(int), np.arange(24))
            self.assertTrue(any(window_polygon(center, matrix).contains(self.field.geometry) for center in centers))
        self.assertGreater(np.std([p[0]['rotation_deg'] for p in paths]), 20.)

    def test_transform_roundtrip_and_natural_boundary_excludes_crop(self):
        matrix, center = rotation(.319), np.array([-250., 0.])
        points = np.array([[5., 230.], [150., 110.], [320., 75.]])
        np.testing.assert_allclose(to_local(to_source(points, center, matrix), center, matrix), points, atol=1e-12)
        local = self.field.local_geometry(center, matrix)
        cropped = local.intersection(WORLD)
        true_boundary = self.field.local_boundary(center, matrix).intersection(WORLD)
        self.assertGreater(cropped.boundary.length, true_boundary.length)

    def test_selection_reproducible_and_uses_original_field(self):
        config = dict(DESIGN, paths_per_block=16)
        with patch('data_generation.stage.basin_subsidence.window.platform', return_value=self.land):
            first = choose_window(self.event, self.folder, self.folder/'first', config)
            second = choose_window(self.event, self.folder, self.folder/'second', config)
        self.assertEqual(first['candidate_id'], second['candidate_id'])
        np.testing.assert_array_equal(first['center_source_km'], second['center_source_km'])
        with np.load(self.folder/'first/window.npz') as a, np.load(self.folder/'second/window.npz') as b:
            np.testing.assert_array_equal(a['u_m_per_yr'], b['u_m_per_yr'])
            x, y = np.meshgrid(np.arange(500)+.5, np.arange(500)+.5)
            points = to_source(np.column_stack([x.ravel(), y.ravel()]), np.array(first['center_source_km']), np.array(first['rotation_matrix']))
            direct = self.field.mapper.evaluate(self.field.rate, self.field.mapper.weights(points)).reshape(500, 500)
            np.testing.assert_allclose(direct, a['u_m_per_yr'], atol=1e-15)
            self.assertEqual(int(a['pink_overlap'].sum()), first['raster_overlap_km2'])


if __name__ == '__main__':
    unittest.main()
