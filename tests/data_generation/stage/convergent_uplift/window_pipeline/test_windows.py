
from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/convergent_uplift/window_pipeline', 'data_generation/stage/mask_generator', 'data_generation/stage/seafloor_generator', 'viewer', 'data_generation/stage/convergent_uplift'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import io,unittest
from types import SimpleNamespace
import numpy as np
from shapely.geometry import MultiLineString,box
from wcontext import *
from geometry import *
from sample_windows import candidate

class WindowTests(unittest.TestCase):
    def test_rigid_window(self):
        R=rotation(.713);center=np.array([-117.,422.]);q=np.array([[0,0],[500,0],[500,500],[0,500],[0,0]],float)
        p=world(q,center,R);self.assertLess(abs(local(p,center,R)-q).max(),1e-10)
        self.assertTrue(np.allclose(np.linalg.norm(np.diff(p,axis=0),axis=1),500));self.assertAlmostEqual(np.linalg.det(R),1.)
    def test_span_not_arc(self):
        points=np.column_stack([np.tile([200,300],15),np.linspace(220,280,30)])
        axis=MultiLineString([points]);pp,x,y=clipped_axis(axis,np.array([250.,250.]),rotation(0))
        self.assertGreater(axis.length,150);self.assertLess(max(x,y),150)
    def test_span_of_all_clipped_parts(self):
        a=MultiLineString([[(10,50),(20,50)],[(200,50),(210,50)],[(900,900),(1000,1000)]])
        pp,x,y=clipped_axis(a,np.array([250.,250.]),rotation(0))
        self.assertEqual(len(pp),2);self.assertEqual(x,200);self.assertEqual(y,0)
    def test_no_area_gate(self):
        s=box(50,245,450,255);field=SimpleNamespace(axis=MultiLineString([[(50,250),(450,250)]]),boundary=s.boundary,tips=np.array([[50,250],[450,250]]))
        p=SimpleNamespace(geometry=box(0,0,500,500),boundary=box(0,0,500,500).boundary,maximum_clearance=250)
        result,reason,_=candidate(field,p,np.array([250.,250.]),rotation(0))
        self.assertLess(s.area/250000,.02);self.assertEqual(reason,'eligible');self.assertIsNotNone(result)
    def test_crop_edge_is_not_natural_zero(self):
        s=box(-1000,-1000,1000,1000);field=SimpleNamespace(axis=MultiLineString([[(-1000,250),(1000,250)]]),boundary=s.boundary,tips=np.array([[-1000,250],[1000,250]]))
        p=SimpleNamespace(geometry=box(0,0,500,500),boundary=box(0,0,500,500).boundary,maximum_clearance=250)
        result,reason,_=candidate(field,p,np.array([250.,250.]),rotation(0))
        self.assertIsNone(result);self.assertEqual(reason,'no_natural_zero_in_platform')
    def test_mask_geometry_and_overlap(self):
        m=np.zeros((9,11),bool);m[2:8,1:7]=True;m[4:6,3:5]=False
        p=mask_geometry(m);self.assertEqual(p.area,m.sum())
        x,y=np.meshgrid(np.arange(11)+.5,np.arange(9)+.5);self.assertTrue(np.array_equal(shapely.contains_xy(p,x,y),m))
    def test_original_function_on_native_cells(self):
        f=CompleteField(1003);r=rng(72001,1);ix=r.integers(0,len(f.x),256);iy=r.integers(0,len(f.y),256)
        values=f.values(np.column_stack([f.x[ix],f.y[iy]]));self.assertLess(abs(values-f.u[iy,ix]).max(),1e-12)
    def test_random_stream_reproducibility(self):
        self.assertTrue(np.array_equal(rng(1001,10).random(128),rng(1001,10).random(128)))
        self.assertFalse(np.array_equal(rng(1001,10).random(128),rng(1002,10).random(128)))

if __name__=='__main__':
    init();stream=io.StringIO();r=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WindowTests))
    (CHECKS/'tests.txt').write_text(stream.getvalue(),encoding='utf-8');save(CHECKS/'tests.json',{'passed':r.wasSuccessful(),'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors)})
    print(stream.getvalue());raise SystemExit(0 if r.wasSuccessful() else 1)
