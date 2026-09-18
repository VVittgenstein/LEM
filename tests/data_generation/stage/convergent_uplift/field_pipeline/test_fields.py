
from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/convergent_uplift/field_pipeline', 'data_generation/stage/mask_generator', 'data_generation/stage/seafloor_generator', 'viewer', 'data_generation/stage/convergent_uplift'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import unittest
import numpy as np
from context import *
from stat_models import compact_profile,ppf,cdf
from generate_fields import RandomFunction,evaluate,projected_values

def straight():
    xy=np.column_stack([np.linspace(-50,50,101),np.zeros(101)]);o=np.ones(101)
    return {'xy':xy,'s':np.linspace(0,100,101),'peak':o*6,'left':o*30,'right':o*70,
            'shape_left':o*2,'shape_right':o*.5,'caps':np.array([20.,40.])}

class FieldTests(unittest.TestCase):
    def test_compact_profiles(self):
        r=np.linspace(0,1,4001)
        for p in (.12,.3,.5,1.,2.,5.,10.):
            for fam in ('weibull','loglogistic'):
                y=compact_profile(r,p,fam,.25)
                self.assertEqual(y[0],1.);self.assertEqual(y[-1],0.)
                self.assertTrue((np.diff(y)<=1e-12).all());self.assertTrue((y>=0).all())
                eps=1e-7
                self.assertLess(abs((compact_profile(eps,p,fam,.25)-1)/eps),.02)
                self.assertLess(abs(compact_profile(1-eps,p,fam,.25)/eps),.02)
    def test_quantile_roundtrip(self):
        m=jload(MODELS/'DS5_model.json')['peak_distribution'];q=np.linspace(.001,.999,101)
        self.assertLess(float(abs(cdf(ppf(q,m),m)-q).max()),2e-5)
    def test_random_seed_and_shared_nodes(self):
        xy=np.array([[0,0],[10,20],[10,20],[100,0]],float)
        a=RandomFunction(77,2,12)(xy);b=RandomFunction(77,2,12)(xy)
        self.assertTrue(np.array_equal(a,b));self.assertEqual(a[1],a[2])
        self.assertFalse(np.array_equal(a,RandomFunction(78,2,12)(xy)))
    def test_straight_profile_and_zero_exterior(self):
        e=straight();x=np.array([-.01,0,.01]);y=np.linspace(0,90,361)
        u=evaluate([e],x,y,1.,'weibull')[:,1]
        self.assertAlmostEqual(u[0],6.);self.assertTrue((np.diff(u)<=1e-10).all())
        self.assertTrue((u[y>30]==0).all())
    def test_tip_has_no_cross_side_jump(self):
        e=straight();x=np.array([65.,70.,75.]);y=np.array([-1e-6,1e-6])
        u=evaluate([e],x,y,1.,'weibull')
        self.assertLess(float(abs(u[0]-u[1]).max()),1e-4)
    def test_overlap_does_not_double(self):
        e=straight();x=np.linspace(-60,80,31);y=np.linspace(-80,50,31)
        a=evaluate([e],x,y,1.,'weibull');b=evaluate([e,straight()],x,y,1.,'weibull')
        self.assertTrue(np.array_equal(a,b))
    def test_terminal_extent(self):
        e=straight();x=np.array([-70.1,-70.,-69.9,89.9,90.,90.1]);y=np.array([0.,.01])
        u=evaluate([e],x,y,1.,'weibull')[0]
        self.assertTrue((u[[0,1,4,5]]==0).all());self.assertTrue((u[[2,3]]>0).all())

if __name__=='__main__':
    import io,time
    initialize();stream=io.StringIO();start=time.perf_counter()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FieldTests))
    (CHECKS/'tests.txt').write_text(stream.getvalue(),encoding='utf-8')
    jsave(CHECKS/'tests.json',{'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'seconds':time.perf_counter()-start})
    print(stream.getvalue());raise SystemExit(0 if result.wasSuccessful() else 1)
