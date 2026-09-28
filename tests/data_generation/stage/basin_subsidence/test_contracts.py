"""Numerical tests for the new event generator; no full LEM execution."""
import unittest
from pathlib import Path
import itertools
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.integrate import quad
from data_generation.stage.basin_subsidence.common import CHECKS, save, EPOCHS
from data_generation.stage.basin_subsidence.spatial import FieldMap, energy, moments, sample_system, long_side
from data_generation.stage.basin_subsidence.temporal import NodeHistory, simulate, frame_times

class ProbabilityTests(unittest.TestCase):
    def test_cold_samples_match_enumerated_target(self):
        points = np.array([[-.2, -.2], [.2, -.2], [-.2, .2], [.2, .2]])
        edges = np.array([[0, 1], [0, 2], [1, 3], [2, 3]], dtype=np.int64)
        neighbors = np.array([[1, 2], [0, 3], [0, 3], [1, 2]], dtype=np.int32)
        weights = np.ones((4, 2)); mass = np.full(4, .25)
        preference = np.column_stack([[.2, -.1, .1, .3], np.ones(4)])
        pars = np.array([2., .5, 1., .5, .4, .7, .6, 2.])
        states = np.array(list(itertools.product([0., 1.], repeat=4)))[1:]
        scores = np.array([energy(s, edges, np.ones(4), moments(s, mass, points), .5, pars, preference) for s in states])
        probabilities = np.exp(-scores+scores.min()); probabilities /= probabilities.sum()
        expected = np.bincount(states.sum(axis=1).astype(int), weights=probabilities, minlength=5)
        _, trace, _, _ = sample_system(912, np.array([1., 1., 0., 0.]), np.ones(9), np.arange(4, dtype=np.int32),
            neighbors, weights, edges, np.ones(4), mass, points, preference, .5, pars, np.array([1., 1.4, 2.]), 2000, 20000, 4)
        actual = np.bincount(np.rint(trace[:, 0]*4).astype(int), minlength=5)/len(trace)
        self.assertLess(float(np.max(abs(expected-actual))), .025)

    def test_minimum_rectangle_measurement_rotation_invariant(self):
        p = np.array([[0., 0.], [3., 0.], [3., 1.], [0., 1.]])
        a = .72; R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        self.assertAlmostEqual(long_side(p), 3.)
        self.assertAlmostEqual(long_side(p@R), 3.)

class InterpolationTests(unittest.TestCase):
    def setUp(self):
        self.xy = np.array([[0., 0.], [1., 0.], [0., 1.], [1., 1.]])
        self.mapper = FieldMap(self.xy, np.array([False, True, True, True]))
        self.rate = np.array([0., -.01, -.03, -.02])

    def test_nodes_and_exterior(self):
        query = self.mapper.weights(np.vstack([self.xy, [-2., 3.]]))
        values = self.mapper.evaluate(self.rate, query)
        np.testing.assert_allclose(values[:4], self.rate, atol=1e-15)
        self.assertEqual(values[4], 0.)

    def test_spatial_continuity_and_zero_taper(self):
        q = self.mapper.weights(np.array([[1e-5, 0.], [2e-5, 0.], [.5, .5-1e-8], [.5, .5+1e-8]]))
        v = self.mapper.evaluate(self.rate, q)
        self.assertLess(abs(v[0]), 1e-10)
        self.assertLess(abs(v[2]-v[3]), 1e-8)

    def test_spatial_operator_is_linear_in_history(self):
        q = self.mapper.weights(np.random.default_rng(7).random((50, 2)))
        np.testing.assert_allclose(self.mapper.evaluate(self.rate*3+self.rate*.2, q),
                                   self.mapper.evaluate(self.rate, q)*3+self.mapper.evaluate(self.rate*.2, q), atol=1e-15)

class TimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = CHECKS/'test_fixture'
        cls.folder.mkdir(parents=True, exist_ok=True)
        event = dict(start_sim_Myr=3., duration_Myr=10., natural_end_sim_Myr=13.)
        save(cls.folder/'event.json', event)
        np.savez(cls.folder/'mesh.npz', reference_u_m_per_yr=np.array([-.0001, -.0002]))
        knots = np.array([0., .3, .65, 1.])
        values = np.array([[1., 2., -.4, 1.], [1.5, .3, 2., .5]])
        curve = PchipInterpolator(knots, values, axis=1)
        np.savez(cls.folder/'time_model.npz', phase_nodes=knots, coefficients=np.moveaxis(curve.c, -1, 0),
                 growth_begin=np.array([0., .1]), growth_end=np.array([.2, .4]),
                 fall_begin=np.array([.75, .6]), fall_end=np.array([1., .95]))
        cls.history = NodeHistory(cls.folder)

    def test_causal_support_and_query_repeatability(self):
        h = self.history
        np.testing.assert_array_equal(h.rate(3), [0., 0.]); np.testing.assert_array_equal(h.rate(13), [0., 0.])
        v = h.rate(7).copy(); h.rate(12); np.testing.assert_array_equal(h.rate(7), v)

    def test_integral_matches_independent_quadrature(self):
        h = self.history
        actual = h.displacement(0, 20)
        points = sorted(set([3., 4., 5., 6., 7., 9., 9.5, 10.5, 12.5, 13.]))
        expected = np.array([quad(lambda t: h.rate(t)[i]*1e6, 0, 20, points=points, epsabs=1e-8)[0] for i in range(2)])
        np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-7)

    def test_interval_additivity_and_signed_motion(self):
        h = self.history
        np.testing.assert_allclose(h.displacement(0, 20), h.displacement(0, 7.17)+h.displacement(7.17, 20), atol=1e-8)
        self.assertGreater(h.rate(9.5)[0], 0)
        with self.assertRaises(ValueError):
            h.displacement(10, 1)

    def test_trigger_invariance_and_embargo(self):
        trigger = dict(shape=2., reference_median_wait_Myr=8., epochs=[dict(growth_multiplier=1.) for _ in EPOCHS])
        duration = dict(selected=dict(family='weibull', parameters=[np.log(1.6), np.log(10.)]))
        design = dict(hold_probability=0., hold_fraction_beta=[2., 6.], rise_beta=[3., 3.])
        a = simulate(1007, .9, trigger, duration, design)
        b = simulate(1007, .013, trigger, duration, design)
        np.testing.assert_allclose([e['start_sim_Myr'] for e in a['events']], [e['start_sim_Myr'] for e in b['events']], atol=1e-9)
        for first, second in zip(a['events'][:-1], a['events'][1:]):
            end = first['natural_end_sim_Myr']
            epoch = next(i for i, (_, _, old, young) in enumerate(EPOCHS) if 48-old <= end < 48-young)
            self.assertGreaterEqual(second['start_sim_Myr'], 48-EPOCHS[epoch][3])

    def test_modern_partial_phase_and_zero_hold(self):
        e = dict(start_sim_Myr=10., rise_Myr=20., hold_Myr=0., fall_Myr=40., rise_end_sim_Myr=30.,
                 hold_end_sim_Myr=30., natural_end_sim_Myr=70., duration_Myr=60., ongoing_at_modern=True)
        f = frame_times(e)
        self.assertTrue(f[-1]['modern']); self.assertAlmostEqual(f[-1]['labels'][0]['elapsed_fraction'], .45)
        self.assertTrue(all(v['sim_Myr'] <= 48 for v in f))
        self.assertFalse(any(x['stage'] == '维持' for v in f for x in v['labels']))

if __name__ == '__main__':
    unittest.main()
