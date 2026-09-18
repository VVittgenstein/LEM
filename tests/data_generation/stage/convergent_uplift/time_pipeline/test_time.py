"""Behavioral checks for the time model and the user's display contracts."""

from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/convergent_uplift/time_pipeline', 'data_generation/stage/mask_generator', 'data_generation/stage/seafloor_generator', 'viewer', 'data_generation/stage/convergent_uplift'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import unittest, io, csv
from timing import *
from spacetime import Evaluator

def synthetic(start=0.,up=4.,hold=1.,down=5.):
    total=up+hold+down
    return dict(start_sim_Myr=start,duration_Myr=total,rise_Myr=up,hold_Myr=hold,fall_Myr=down,
                rise_end_sim_Myr=start+up,hold_end_sim_Myr=start+up+hold,natural_end_sim_Myr=start+total)

def zero_noise():
    return dict(omega_xy=[[.1,0],[0,.1]],omega_t=[1.,2.],a=[1.,-.2],b=[.5,.3],sigma_log=0.)

class TestTime(unittest.TestCase):
    def test_event_spatial_seed_independence(self):
        from spatial_binding import spatial_seed
        seeds=[spatial_seed(world,index) for world in range(1001,1009) for index in range(4)]
        self.assertEqual(len(seeds),len(set(seeds)))
        self.assertNotEqual(spatial_seed(1001,0),1001)
        self.assertEqual(spatial_seed(1001,2),spatial_seed(1001,2))
        self.assertNotEqual(spatial_seed(1001,2,0),spatial_seed(1001,2,1))

    def test_geometry_hash_excludes_metadata(self):
        from spatial_binding import coordinate_hash
        a={'edges':[[[0.,0.],[1.,0.]]],'seed':1};b={'edges':a['edges'],'seed':99}
        self.assertEqual(coordinate_hash(a),coordinate_hash(b))
        b['edges']=[[[0.,0.],[1.,1.]]];self.assertNotEqual(coordinate_hash(a),coordinate_hash(b))

    def test_duration_censor_likelihood(self):
        from fit_models import log_likelihood
        rows=[dict(duration_low_Myr=8,duration_high_Myr=8,kind='ongoing',weight=1.)]
        self.assertAlmostEqual(log_likelihood(rows,'weibull',[0.,np.log(10)]),-.8)

    def test_source_family_weights(self):
        rows=list(csv.DictReader((SOURCES/'duration_evidence.csv').open(encoding='utf-8-sig')))
        for family in set(r['family'] for r in rows):self.assertAlmostEqual(sum(float(r['weight']) for r in rows if r['family']==family),1.)
        self.assertEqual(sum(r['family']=='Southern_Alps' for r in rows),1)

    def test_lifetime_sum_and_hold_atom(self):
        random=rng(9890);model=load(MODELS/'duration.json');design=load(MODELS/'design.json')
        samples=[lifetime(random,model,design) for _ in range(500)]
        self.assertTrue(any(x['hold_Myr']==0 for x in samples));self.assertTrue(any(x['hold_Myr']>0 for x in samples))
        self.assertTrue(any(x['duration_Myr']>48 for x in samples))
        for x in samples:self.assertAlmostEqual(x['duration_Myr'],x['rise_Myr']+x['hold_Myr']+x['fall_Myr'])

    def test_probability_uses_conditional_physical_time(self):
        model=load(MODELS/'trigger.json');w=3.;p1=step_probability(w,.1,2,model);p2=step_probability(w+.1,.2,2,model)
        self.assertAlmostEqual(1-(1-p1)*(1-p2),step_probability(w,.3,2,model),places=14)
        self.assertGreater(step_probability(10,.1,2,model),p1)

    def test_event_times_invariant_under_dt(self):
        for seed in (1001,1003,1004):
            a=simulate(seed,.4);b=simulate(seed,.005)
            self.assertEqual(len(a['events']),len(b['events']))
            for x,y in zip(a['events'],b['events']):
                self.assertAlmostEqual(x['start_sim_Myr'],y['start_sim_Myr'],places=8)
                self.assertEqual(x['duration_Myr'],y['duration_Myr'])

    def test_epoch_end_embargo(self):
        for seed in range(1001,1009):
            events=simulate(seed)['events']
            for a,b in zip(events[:-1],events[1:]):
                i=epoch_index(a['natural_end_sim_Myr']);self.assertGreaterEqual(b['start_sim_Myr'],48-EPOCHS[i][3])
                self.assertGreater(b['start_sim_Myr'],a['natural_end_sim_Myr'])

    def test_no_trigger_is_preserved(self):
        model=load(MODELS/'trigger.json');model['reference_median_wait_Myr']=1e8
        result=simulate(1001,dt_Myr=.2,trigger_model=model)
        self.assertEqual(result['events'],[]);self.assertEqual(result['embargoes'],[])

    def test_ten_and_seven_frames(self):
        self.assertEqual(len(frame_times(synthetic())),10)
        self.assertEqual(len(frame_times(synthetic(hold=0))),7)

    def test_exact_33_66_fractions(self):
        frames=frame_times(synthetic());fractions={l['elapsed_fraction'] for f in frames for l in f['labels']}
        self.assertEqual(fractions,{0.,.33,.66,1.})

    def test_modern_at_35_percent_fall(self):
        event=synthetic(start=39.5,up=3,hold=2,down=10);frames=frame_times(event)
        self.assertEqual(frames[-1]['sim_Myr'],48);self.assertTrue(frames[-1]['modern'])
        self.assertAlmostEqual(frames[-1]['labels'][0]['elapsed_fraction'],.35)
        self.assertTrue(any(l['stage']=='下降' and l['elapsed_fraction']==.33 for f in frames for l in f['labels']))
        self.assertEqual(event['natural_end_sim_Myr'],54.5)
        self.assertFalse(any(f['sim_Myr']>48 for f in frames))

    def test_no_duplicate_modern_boundary(self):
        frames=frame_times(synthetic(start=43,up=3,hold=2,down=10))
        self.assertEqual(sum(abs(f['sim_Myr']-48)<1e-12 for f in frames),1)
        self.assertEqual(len(frames[-1]['labels']),2)

    def test_lifetime_longer_than_geological_axis(self):
        e=synthetic(start=5,up=30,hold=10,down=45);frames=frame_times(e)
        self.assertEqual(e['duration_Myr'],85);self.assertEqual(e['natural_end_sim_Myr'],90)
        self.assertTrue(frames[-1]['modern']);self.assertLessEqual(max(f['sim_Myr'] for f in frames),48)

    def test_start_and_end_exact_zero_full_at_rise_end(self):
        e=synthetic();on=np.linspace(0,.7,100);off=np.linspace(0,1,100)
        self.assertTrue(np.all(envelope(0,e,on,off)==0));self.assertTrue(np.all(envelope(10,e,on,off)==0))
        np.testing.assert_allclose(envelope(4,e,on,off),1.)
        np.testing.assert_allclose(envelope(5,e,on,off),1.)
        self.assertTrue(np.any(envelope(1,e,on,off)==0));self.assertTrue(np.any(envelope(1,e,on,off)>0))
        self.assertTrue(np.any(envelope(8,e,on,off)==0));self.assertTrue(np.any(envelope(8,e,on,off)>0))

    def test_phase_boundary_continuity(self):
        e=synthetic();on=np.linspace(0,.7,100);off=np.linspace(0,1,100)
        for t in (4,5):np.testing.assert_allclose(envelope(t-1e-7,e,on,off),envelope(t+1e-7,e,on,off),atol=1e-10)

    def test_fourier_cache_reproduces_direct_function(self):
        points=rng(9980).normal(size=(200,2))*20;noise=zero_noise();noise['sigma_log']=.25
        a=Evaluator(points,np.ones(200),np.zeros(200),np.ones(200),synthetic(),noise,True)
        b=Evaluator(points,np.ones(200),np.zeros(200),np.ones(200),synthetic(),noise,False)
        for t in (2,4,8):np.testing.assert_allclose(a.multiplier(t),b.multiplier(t),rtol=1e-7)

    def test_zero_support_cannot_gain_uplift(self):
        a=Evaluator(np.zeros((2,2)),np.array([0.,.001]),np.zeros(2),np.zeros(2),synthetic(),zero_noise())
        self.assertEqual(a.rate(4)[0],0.);self.assertGreater(a.rate(4)[1],0.)

    def test_displacement_units_and_quadrature(self):
        e=synthetic();a=Evaluator(np.zeros((1,2)),np.array([.001]),np.zeros(1),np.zeros(1),e,zero_noise())
        expected=(4*(1-.45/2)+1+5*.35/2)*1000
        self.assertAlmostEqual(a.displacement(0,10,.05)[0],expected,places=5)
        self.assertAlmostEqual((a.displacement(0,3,.05)+a.displacement(3,10,.05))[0],expected,places=5)

if __name__=='__main__':
    init();stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestTime))
    (CHECKS/'tests.txt').write_text(stream.getvalue(),encoding='utf-8');print(stream.getvalue(),flush=True)
    save(CHECKS/'tests.json',dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful()))
    if not result.wasSuccessful():raise SystemExit(1)
