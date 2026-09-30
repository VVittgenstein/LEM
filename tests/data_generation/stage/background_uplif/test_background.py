
from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/background_uplif', 'data_generation/stage/mask_generator', 'data_generation/stage/seafloor_generator', 'viewer'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import spatial
import taper
from schedule import BackgroundSchedule


class BackgroundTests(unittest.TestCase):
    def test_partition_ring_weights(self):
        labels=np.arange(1,32*32+1).reshape(32,32)
        mask=np.zeros((32,32),bool);mask[10:22,10:22]=True
        ring,w,info=taper.partition_rings(labels,mask)
        grid=w[labels-1]
        self.assertEqual(grid[15,15],1)
        self.assertEqual(grid[10,15],.75)
        self.assertEqual(grid[9,15],.5)
        self.assertEqual(grid[8,15],.25)
        self.assertEqual(grid[7,15],0)
        self.assertEqual(grid[0,0],0)

    def test_enclosed_hole_is_not_outer_ring(self):
        labels=np.arange(1,31*31+1).reshape(31,31)
        mask=np.zeros((31,31),bool);mask[6:25,6:25]=True;mask[14:17,14:17]=False
        ring,w,info=taper.partition_rings(labels,mask)
        self.assertEqual(w[labels[15,15]-1],1)
        self.assertEqual(ring[labels[15,15]-1],0)
        self.assertEqual(len(info["enclosed_water_regions"]),9)

    def test_partial_partition_is_rejected(self):
        labels=np.repeat(np.repeat(np.arange(1,10).reshape(3,3),3,0),3,1)
        mask=np.zeros_like(labels,bool);mask[4,4]=True
        with self.assertRaises(ValueError):taper.partition_rings(labels,mask)

    def test_taper_is_bounded_and_outer_zero(self):
        labels=np.arange(1,60*60+1).reshape(60,60)
        mask=np.zeros((60,60),bool);mask[15:45,15:45]=True
        weight,hard,ring,info=taper.make_taper(labels,mask)
        self.assertTrue(np.all((weight>=0)&(weight<=1)))
        self.assertTrue(np.all(weight[ring>=3]==0))
        self.assertEqual(weight[30,30],1)
        self.assertTrue(np.any((weight>0)&(weight<.25)))

    def test_random_reproduction_and_independence(self):
        a=spatial.latent_field(spatial.white_spectrum(1001,1,0),100,80)
        b=spatial.latent_field(spatial.white_spectrum(1001,1,0),100,80)
        other=spatial.latent_field(spatial.white_spectrum(1002,1,0),100,80)
        self.assertTrue(np.array_equal(a,b))
        self.assertFalse(np.array_equal(a,other))
        xy=np.arange(500)+.5-250
        z=spatial.normalize(spatial.at_coordinates(a,xy,xy),-4.8,.68)
        self.assertAlmostEqual(z.mean(),-4.8,places=12)
        self.assertAlmostEqual(z.std(),.68,places=12)

    def test_variogram_preserves_signed_rate_units(self):
        y,x=np.mgrid[:9,:11]
        f=.2*x-.5*y+4
        a=spatial.variogram_features(f)
        b=spatial.variogram_features(f/1e6)
        self.assertTrue(np.allclose(a,b))
        self.assertLess(a[0],a[4])

    def test_schedule_boundary_and_integral(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"s.npz"
            rates=np.array([np.full((2,2),2e-6),np.full((2,2),-4e-6)])
            np.savez(path,start_yr=[0.,9e6],end_yr=[9e6,19e6],rate_m_per_yr=rates)
            s=BackgroundSchedule(path)
            self.assertTrue(np.array_equal(s.at_time(9e6),rates[1]))
            self.assertTrue(np.array_equal(s.at_time(19e6),rates[1]))
            self.assertTrue(np.allclose(s.displacement(8e6,11e6),-6))
            self.assertTrue(np.allclose(s.mean_rate(8e6,11e6),-2e-6))
            with self.assertRaises(ValueError):s.at_time(-1)
            with self.assertRaises(ValueError):s.displacement(0,20e6)

    def test_invalid_schedule_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"s.npz"
            for start,end,rates in (([],[],np.empty((0,2,2))),
                                    ([0],[np.inf],np.ones((1,2,2))),
                                    ([0,10],[9,19],np.ones((2,2,2))),
                                    ([0],[9],np.ones((1,2)))):
                np.savez(path,start_yr=start,end_yr=end,rate_m_per_yr=rates)
                with self.assertRaises(ValueError):BackgroundSchedule(path)


if __name__=="__main__":unittest.main()
