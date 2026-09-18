
from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/mask_generator',):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import unittest
import numpy as np
from world_orogen_gibbs.config import Settings
from world_orogen_gibbs.geometry import boundary_reserve,geometry


class BoundaryLayerTests(unittest.TestCase):
    def test_regular_graph_distance_layers(self):
        labels=np.arange(1,50).reshape(7,7)
        forbidden,distance,layers=boundary_reserve(labels,3)
        yy,xx=np.indices(labels.shape)
        expected=np.minimum.reduce([yy,xx,6-yy,6-xx])+1
        np.testing.assert_array_equal(layers[labels-1],expected)
        self.assertEqual(int((~forbidden).sum()),1)
        self.assertEqual(float(distance[~forbidden].min()),3.)

    def test_large_whole_regions_and_contact_adjacency(self):
        labels=np.array([[1,1,1,1,1,1,1],[1,2,2,2,3,3,1],[1,2,4,4,3,3,1],
                         [1,2,4,5,5,3,1],[1,2,4,5,5,3,1],[1,2,2,2,3,3,1],[1,1,1,1,1,1,1]])
        forbidden,distances,layers=boundary_reserve(labels,2)
        np.testing.assert_array_equal(layers,[1,2,2,3,3])
        np.testing.assert_array_equal(np.flatnonzero(~forbidden)+1,[4,5])
        self.assertEqual((~forbidden)[labels-1].sum(),8)

    def test_exhaustion_is_explicit_and_no_layer_reduction(self):
        labels=np.arange(1,50).reshape(7,7)
        forbidden,distance,layers=boundary_reserve(labels,10)
        self.assertTrue(forbidden.all())
        self.assertEqual(int(layers.max()),4)

    def test_legacy_one_layer_and_old_settings(self):
        labels=np.arange(1,50).reshape(7,7)
        expected=np.zeros(49,bool)
        expected[np.unique(np.r_[labels[0],labels[-1],labels[:,0],labels[:,-1]])-1]=True
        np.testing.assert_array_equal(geometry(labels).forbidden,expected)
        self.assertEqual(Settings.from_record({'partition_count':512}).boundary_layers,1)

    def test_sampler_obeys_multiple_excluded_layers(self):
        import os,tempfile
        from pathlib import Path
        from world_orogen_gibbs.config import OUTPUT
        from world_orogen_gibbs.sampler import build_kernel,run_sampler
        root=Path(os.environ.get('LEM_MASK_TEST_OUTPUT',str(OUTPUT)))/'boundary_tests'
        root.mkdir(parents=True,exist_ok=True);build_kernel()
        g=geometry(np.arange(1,50).reshape(7,7),2)
        s=Settings(boundary_layers=2,center_weight=1.,spread_weight=.5,perimeter_weight=.3,field_weight=2.,area_weight=.3)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            result=run_sampler(folder,g,np.linspace(-1,1,49),s,99,burn=32,draws=32,thin=1,chains=2,temperatures=(1.,))
            self.assertFalse(result['states'][:,:,g.region_layer<=2].any())
            self.assertTrue(result['states'].any(axis=2).all())


if __name__=='__main__':unittest.main()
