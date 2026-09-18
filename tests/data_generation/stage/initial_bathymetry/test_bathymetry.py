
from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/initial_bathymetry', 'data_generation/stage/mask_generator', 'data_generation/stage/seafloor_generator', 'viewer'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import unittest
import numpy as np
from profiles import Profile,smoothstep
from surface import base_surface
from roughness import unit_noise,local_std


class ProfileTests(unittest.TestCase):
    def setUp(self):self.p=Profile(40.,200.,.03,3746.)

    def test_reference_points_and_monotonicity(self):
        p=self.p;x=np.linspace(-10,250,50001);z=p.depth(x)
        self.assertTrue((np.diff(z)>=-1e-10).all())
        np.testing.assert_allclose(p.depth([0,p.width_km,p.foot_km,250]),[53,200,3746,3746],atol=1e-10)
        x0=p.width_km+p.smoothing_km+10
        self.assertAlmostEqual(float(p.depth(x0+1)-p.depth(x0)),30.,places=10)

    def test_profile_derivative_continuity(self):
        p=self.p;h=1e-5
        for x in (0,p.width_km,p.width_km+p.smoothing_km,p.foot_km-p.smoothing_km,p.foot_km):
            left=(p.depth(x)-p.depth(x-h))/h;right=(p.depth(x+h)-p.depth(x))/h
            self.assertLess(abs(left-right),1e-3)

    def test_truncation_retains_original_parameters(self):
        p=self.p
        short=p.depth(np.arange(96.));long=p.depth(np.arange(251.))
        np.testing.assert_array_equal(short,long[:96])
        self.assertLess(short[-1],p.bottom_depth_m)
        # The analytically integrated steepening ramp delays full depth; it
        # retains the measured 30 m/km slope throughout the straight part.
        expected=200+.5*(p.gentle_m_per_km+30)*p.smoothing_km+30*(95-40-p.smoothing_km)
        self.assertAlmostEqual(short[-1],expected)

    def test_lateral_blend_has_flat_end_tangents(self):
        a,b=453.,3746.;slope=153.;width=1.875*(b-a)/slope
        x=np.linspace(-width,width,20001)
        z=a+(b-a)*smoothstep(.5+x/width)
        grad=np.gradient(z,x)
        self.assertTrue((np.diff(z)>=-1e-10).all())
        self.assertLessEqual(grad.max(),slope*1.0001)
        self.assertEqual(z[0],a);self.assertEqual(z[-1],b)
        self.assertAlmostEqual(float(grad[0]),0.,places=8)

    def test_surface_crop_does_not_compress_profile(self):
        params={'platform_depth_m':53.,'profiles':{},'surface':{'distance_regularization_sigma_km':1.,'lateral_min_width_km':3.}}
        for kind,bottom in (('shallow',453.),('deep',3746.)):
            params['profiles'][kind]=dict(width_km=40.,break_depth_m=200.,steep_slope_m_per_m=.03,bottom_depth_m=bottom)
        def scene(n):
            mask=np.indices((120,n))[1]<40;types=np.where(mask,0,1)
            return base_surface(mask,types,params)
        small,large=scene(100),scene(220)
        np.testing.assert_allclose(small['base_elevation'],large['base_elevation'][:,:100],atol=1e-10,rtol=0)
        p=Profile(40,200,.03,453)
        x=np.arange(48,100)
        np.testing.assert_allclose(small['base_elevation'][60,x],-p.depth(x+.5-40),atol=1e-10,rtol=0)

    def test_correlated_noise_normalization_and_reproducibility(self):
        mask=np.ones((180,180),bool)
        a,_=unit_noise(12,0,3.,mask);b,_=unit_noise(12,0,3.,mask);other,_=unit_noise(13,0,3.,mask)
        np.testing.assert_array_equal(a,b);self.assertFalse(np.array_equal(a,other))
        self.assertAlmostEqual(float(np.median(local_std(a)[1:-1,1:-1])),1.,places=10)
        self.assertGreater(np.corrcoef(a[:,:-1].ravel(),a[:,1:].ravel())[0,1],.9)


if __name__=='__main__':unittest.main()
