
from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/sea_level', 'data_generation/stage/mask_generator', 'data_generation/stage/seafloor_generator', 'viewer'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import unittest
import numpy as np
from sea_curve import SeaLevelCurve,KEYS,MAX_AGE


class CurveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.curve=SeaLevelCurve.from_files()

    def test_coverage_and_order(self):
        age=np.linspace(MAX_AGE,0,48001);y=self.curve.at_age(age)
        self.assertTrue(np.isfinite(y).all())
        self.assertEqual(float(y[0]),51.6);self.assertEqual(float(y[-1]),8.96)
        self.assertEqual(len(y),48001)

    def test_source_values_retained_outside_transitions(self):
        limits={'miller_smoothed':(1000000,MAX_AGE),'miller_unsmoothed':(798000,980000),'spratt_2016':(0,self.curve.windows['young'][0])}
        for key,(lo,hi) in limits.items():
            s=self.curve.bundle['sources'][key];a=np.array(s['age_yr_bp']);y=np.array(s['sea_level_m'])
            use=(a>=lo)&(a<=hi)
            np.testing.assert_allclose(self.curve.at_age(a[use]),y[use],atol=1e-11,rtol=0)

    def test_join_values_and_rates_are_continuous(self):
        c=self.curve;h=.0001
        for a in sum(self.curve.windows.values(),[]):
            left=c.at_age(a-h)+h*c.derivative_by_age(a-h)
            right=c.at_age(a+h)-h*c.derivative_by_age(a+h)
            self.assertLess(abs(left-right),1e-8)
            self.assertLess(abs(c.derivative_by_age(a-h)-c.derivative_by_age(a+h)),1e-8)

    def test_overlap_is_convex_and_not_component_sum(self):
        for lo,hi in self.curve.windows.values():
            a=np.linspace(lo,hi,2001);w,_=self.curve.weights(a)
            np.testing.assert_allclose(w.sum(axis=1),1.,atol=1e-15)
            self.assertTrue((w>=0).all() and (w<=1).all())
            values=np.column_stack([self.curve.interpolators[k](a) for k in KEYS])
            active=np.where(w>0,values,np.nan);actual=self.curve.at_age(a)
            self.assertTrue((actual>=np.nanmin(active,axis=1)-1e-10).all())
            self.assertTrue((actual<=np.nanmax(active,axis=1)+1e-10).all())

    def test_window_uses_original_time_direction_and_exact_end(self):
        c=self.curve;w=c.window(1100000.,123456.7,1000.)
        self.assertEqual(w['time_yr'][0],0.);self.assertEqual(w['time_yr'][-1],123456.7)
        self.assertEqual(w['sea_level_m'][0],0.)
        self.assertTrue((np.diff(w['age_yr_bp'])<0).all())
        np.testing.assert_allclose(w['sea_level_m'],c.at_age(w['age_yr_bp'])-c.at_age(1100000.),atol=1e-12)

    def test_outside_domain_is_rejected(self):
        for age in (-1.,MAX_AGE+1,np.nan):
            with self.assertRaises(ValueError):self.curve.at_age(age)
        with self.assertRaises(ValueError):self.curve.window(1000000.,2000000.)


if __name__=='__main__':unittest.main()
