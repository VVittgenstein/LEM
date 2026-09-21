from __future__ import annotations
import sys,unittest,os
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.elastic import ElasticBox,sample_plane
from engine.common import load,OUT,stress_display
from engine.forcing import create_episodes,coefficients
from engine.faults import rates_at,cumulative_at,geometry_at
from engine.schedule import RiftingSchedule
from engine.response import field_from_coefficients,tetra_quadrature,slip_eigenstrain

class ElasticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.box=ElasticBox(20,5,4,10)
    def test_uniform_traction_analytic_solution(self):
        box=self.box;S=np.array([[8.,2.,1.],[2.,4.,-.5],[1.,-.5,3.]])
        f=box.traction(box.face_normal@S.T);u,reaction=box.solve(f)
        expected=np.array([8,4,3,2,-.5,1])
        self.assertLess(float(np.max(abs(box.nodal_stress(u)-expected))),1e-8)
        self.assertLess(reaction,1e-10)
    def test_uniform_eigenstrain(self):
        box=self.box;eps=np.array([.001,-.0002,.0003,.0004,.0001,0.])
        force=box.eigenstrain_load(np.tile(eps,(len(box.tet),1)))
        u,_=box.solve(force);calculated=box.nodal_stress(u)
        self.assertLess(float(np.max(abs(calculated-box.D@eps)))/np.max(abs(box.D@eps)),1e-10)
        self.assertLess(float(np.max(abs(box.R@force)))/np.linalg.norm(force),1e-10)
    def test_balance_correction(self):
        f=np.zeros(len(self.box.nodes)*3);f[-1]=1
        balanced,result=self.box.balanced(f)
        self.assertLess(result['relative_balance'],1e-12)
    def test_tensor_display(self):
        s=np.array([3.,1.,0.,0.,0.,0.]);m,a=stress_display(s)
        self.assertAlmostEqual(float(m),2);self.assertAlmostEqual(float(a),0)
    def test_fixed_basal_reference_analytic_solution(self):
        box=ElasticBox(20,5,4,10,young_pa=30e9,nu=0,support_bottom=True)
        stress=np.diag([0.,0.,-1e6])
        force=box.traction(box.face_normal@stress.T)
        u,_=box.solve(force)
        expected=-1e6/30e9*(box.nodes[:,2]+10000)
        np.testing.assert_allclose(u.reshape(-1,3)[:,2],expected,atol=1e-10)
        np.testing.assert_array_equal(u[box.fixed],0)
    def test_empty_fault_history(self):
        data=dict(times_Myr=np.array([0.,48.]),slip_rates_m_per_year=np.zeros((0,2,3)),cumulative_slip_m=np.zeros((0,2,3)))
        rate=rates_at(data,12.);cumulative=cumulative_at(data,12.)
        self.assertEqual(rate.shape,(0,3));self.assertEqual(cumulative.shape,(0,3))
        field=field_from_coefficients(np.zeros((0,8,8,3)),rate)
        np.testing.assert_array_equal(field,np.zeros((8,8,3)))
    def test_tetrahedral_quadrature_normalization(self):
        points,weights=tetra_quadrature(3)
        np.testing.assert_allclose(points.sum(axis=1),1,atol=1e-14)
        np.testing.assert_allclose(weights@points,np.full(4,.25),atol=1e-14)
        self.assertAlmostEqual(float(weights.sum()),1)
    def test_regularization_preserves_geometric_slip_moment(self):
        f=dict(dip_deg=60,dip_direction_rad=0,trace_xy_km=np.column_stack([np.full(21,10),np.linspace(7,13,21)]).tolist(),length_km=6,bottom_depth_km=5)
        a,aa=slip_eigenstrain(self.box,f,1,np.array([0,0]),regularization_width_km=3,patch_half_length_km=2)
        b,bb=slip_eigenstrain(self.box,f,1,np.array([0,0]),regularization_width_km=5,patch_half_length_km=7)
        self.assertEqual(aa['target_moment_area_m2'],bb['target_moment_area_m2'])
        np.testing.assert_allclose(self.box.volume@a,self.box.volume@b,rtol=1e-12,atol=1e-6)

class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.seed=int(os.environ.get('RIFTING_TEST_SEED','1001'));cls.schedule=RiftingSchedule(cls.seed);cls.data_run=cls.schedule.run
    def test_seed_reproduction(self):
        a=create_episodes(self.seed,self.data_run.model);b=create_episodes(self.seed,self.data_run.model)
        self.assertEqual(a,b)
        for new,old in zip(a,self.data_run.episodes):
            for key in ['id','knots_Myr','position_km','direction','noise_phases']:self.assertEqual(new[key],old[key])
    def test_local_directions_cover_the_full_circle(self):
        vectors=np.array([e['direction'] for seed in range(100) for e in create_episodes(seed,self.data_run.model) if e['kind']=='local'])
        self.assertLess(float(abs(vectors[:,:2].mean(axis=0)).max()),.1)
        self.assertLess(float(vectors[:,1].min()),-.9);self.assertGreater(float(vectors[:,1].max()),.9)
    def test_stress_superposition(self):
        points=np.array([[300,1600],[400,1800],[550,1700]])
        a=self.schedule.stress_at(points,20e6,'far');b=self.schedule.stress_at(points,20e6,'local');c=self.schedule.stress_at(points,20e6)
        np.testing.assert_allclose(c,a+b,atol=1e-10)
    def test_window_coordinates_match_global_queries(self):
        planes=self.data_run.planes(20);origin=np.array(self.data_run.window['origin_km']);xy=origin+np.array([[.5,.5],[250.5,301.5],[499.5,499.5]])
        a=self.schedule.stress_at(xy,20e6);b=sample_plane(planes['total'],xy[:,0],xy[:,1],self.data_run.length)
        np.testing.assert_allclose(a,b,atol=1e-12,rtol=1e-13)
    def test_no_fault_before_birth(self):
        first=min(f['birth_Myr'] for f in self.data_run.faults)
        self.assertEqual(len(self.schedule.faults_at((first-1e-6)*1e6)),0)
        self.assertFalse(np.any(self.schedule.at_time((first-1e-6)*1e6)))
    def test_geometry_does_not_grow_without_slip(self):
        rates=self.data_run.history['slip_rates_m_per_year']
        for i,f in enumerate(self.data_run.faults):
            g=np.array(f['geometry_fraction']);self.assertTrue(np.all(np.diff(g)>=-1e-12))
            idle=(rates[i,:-1,1]==0)&(rates[i,1:,1]==0)
            self.assertTrue(np.all(abs(np.diff(g)[idle])<1e-12))
    def test_cumulative_history_retained(self):
        for i,f in enumerate(self.data_run.faults):
            cumulative=self.data_run.history['cumulative_slip_m'][i]
            self.assertTrue(np.all(np.diff(cumulative,axis=0)>=-1e-8))
    def test_integral_additivity_and_mean_rate(self):
        a=self.schedule.displacement(0,48e6);b=self.schedule.displacement(0,19.3e6)+self.schedule.displacement(19.3e6,48e6)
        np.testing.assert_allclose(a,b,atol=1e-8)
        np.testing.assert_allclose(self.schedule.mean_rate(12e6,24e6)*12e6,self.schedule.displacement(12e6,24e6),atol=1e-9)
    def test_no_rng_in_response_queries(self):
        with patch('numpy.random.default_rng',side_effect=AssertionError('Unexpected random draw')):
            a=self.schedule.at_time(18e6);self.schedule.at_time(4e6);b=self.schedule.at_time(18e6)
        np.testing.assert_array_equal(a,b)
    def test_zero_and_signed_output(self):
        self.assertFalse(np.any(self.schedule.at_time(0)))
        self.assertLess(float(np.min(self.data_run.vertical)),0);self.assertGreater(float(np.max(self.data_run.vertical)),0)
    def test_all_display_times_and_window(self):
        metrics=load(self.data_run.path/'frame_metrics.json')
        self.assertTrue(all(x['window_qualifies'] for x in metrics))
        self.assertEqual(len(metrics),len(self.data_run.timeline['frames']))
        times=[f['time_year'] for f in self.data_run.timeline['frames']]
        self.assertEqual(times,sorted(set(times)));self.assertEqual(times[-1],48e6)
        self.assertEqual(sum(len(p['frame_ids']) for p in self.data_run.timeline['nine_panel_pages']),len(times))
    def test_invalid_time(self):
        with self.assertRaises(ValueError):self.schedule.at_time(-1)
        with self.assertRaises(ValueError):self.schedule.at_time(49e6)
        with self.assertRaises(ValueError):self.schedule.mean_rate(2,1)
        with self.assertRaises(ValueError):self.schedule.stress_at([[-1,1]],0)
        with self.assertRaises(ValueError):self.schedule.stress_at([[float('nan'),1]],0)

if __name__=='__main__':unittest.main(verbosity=2)
