
from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/mask_generator',):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import unittest
from dataclasses import replace
import numpy as np
from scipy import ndimage as ndi
from world_orogen_gibbs.config import Settings
from world_orogen_gibbs.geometry import generate_partitions,geometry,L4
from world_orogen_gibbs.fields import generate_fields
from world_orogen_gibbs.diagnostics import diagnose,spatial_diagnose


class GeometryFieldTests(unittest.TestCase):
    def test_full_domain_and_whole_region_exclusion(self):
        s=replace(Settings(),partition_count=64,coarse_side=24)
        labels,xy,record,projection=generate_partitions(333,s)
        self.assertEqual(labels.shape,(500,500));self.assertEqual(labels.min(),1)
        self.assertEqual(np.unique(labels).size,64)
        for i,sl in enumerate(ndi.find_objects(labels),1):self.assertEqual(ndi.label(labels[sl]==i,L4)[1],1)
        g=geometry(labels);allowed=(~g.forbidden)[labels-1]
        self.assertFalse(np.r_[allowed[0],allowed[-1],allowed[:,0],allowed[:,-1]].any())
        # Width follows complete regions, rather than a fixed ten-cell ring.
        self.assertGreater((~allowed).sum(),500*500-480*480)

    def test_field_standardization_and_partition_means(self):
        settings=replace(Settings(),size=32,field_sigmas_km=(1.,3.,7.))
        labels=np.ones((32,32),np.int16);labels[:,16:]=2
        fields,combined,means=generate_fields(871,settings,labels)
        np.testing.assert_allclose(fields.mean(axis=(1,2)),0,atol=1e-12)
        np.testing.assert_allclose(fields.std(axis=(1,2)),1,atol=1e-12)
        np.testing.assert_allclose(means,[combined[:,:16].mean(),combined[:,16:].mean()])
        other=generate_fields(871,settings,labels)
        np.testing.assert_array_equal(fields,other[0])
        # Compare the local increments, averaged over all returned pixels.
        rough=[np.mean(np.diff(a,axis=0)**2)+np.mean(np.diff(a,axis=1)**2) for a in fields]
        self.assertGreater(rough[0],rough[-1])

    def test_diagnostics_detect_separated_chains(self):
        rng=np.random.default_rng(721)
        x=rng.normal(size=(4,1000,11));x[1,:,0]+=5
        self.assertFalse(diagnose(x)['passed'])
        states=np.zeros((4,1000,4),bool);states[1:,:,2]=True
        self.assertFalse(spatial_diagnose(states,np.zeros(4,bool))['passed'])


if __name__=='__main__':unittest.main()
