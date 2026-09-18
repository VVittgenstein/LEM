
from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/mask_generator',):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import tempfile
import os
import unittest
from dataclasses import replace,asdict
from pathlib import Path
import numpy as np
from scipy.special import expit
from world_orogen_gibbs.config import Settings,OUTPUT as DEFAULT_OUTPUT
from world_orogen_gibbs.geometry import geometry,reconnect
from world_orogen_gibbs.model import terms,conditional,enumerate_distribution
from world_orogen_gibbs.sampler import run_sampler,build_kernel
from world_orogen_gibbs.diagnostics import diagnose

OUTPUT=Path(os.environ.get('LEM_MASK_TEST_OUTPUT',str(DEFAULT_OUTPUT)))


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_kernel();OUTPUT.mkdir(parents=True,exist_ok=True)
        cls.g=geometry(np.arange(1,26,dtype=np.int16).reshape(5,5))
        cls.field=np.linspace(-1,1,25)
        cls.settings=Settings(center_weight=1.,spread_weight=.5,perimeter_weight=.3,field_weight=2.,area_weight=.3)

    def test_area_flat_and_two_sided(self):
        s=self.settings
        def penalty(f):return s.area_weight*.5*(max(s.area_low-f,0,f-s.area_high)/s.area_softness)**2
        self.assertEqual(penalty(.50),penalty(.55));self.assertEqual(penalty(.55),penalty(.60))
        self.assertTrue(np.isfinite(penalty(.36)));self.assertAlmostEqual(penalty(.40),penalty(.70))

    def test_boundary_entire_region(self):
        g=self.g
        self.assertEqual(int(g.forbidden.sum()),16)
        self.assertFalse(g.forbidden[g.center_id])
        self.assertAlmostEqual(g.areas[~g.forbidden].sum(),.36)

    def test_conditional_matches_full_enumeration(self):
        g=self.g;s=self.settings
        states,probs=enumerate_distribution(g,self.field,s)
        index=g.center_id
        other=states[123].copy();other[index]=False
        same=np.all(states[:,np.arange(25)!=index]==other[np.arange(25)!=index],axis=1)
        expected=probs[same & states[:,index]].sum()/probs[same].sum()
        self.assertAlmostEqual(conditional(other,index,g,self.field,s),expected)

    def test_grid_perimeter(self):
        z=np.zeros(25,bool);z[[11,12]]=True
        t=terms(z,self.g,self.field,self.settings)
        self.assertAlmostEqual(t['P'],6/5)

    def test_increment_and_sampler_distribution(self):
        g=self.g;s=self.settings
        with tempfile.TemporaryDirectory(dir=OUTPUT) as folder:
            result=run_sampler(folder,g,self.field,s,7031,burn=512,draws=10000,thin=1,chains=4,temperatures=(1.,1.7,3.))
            self.assertGreater(result['adds'],0);self.assertGreater(result['removes'],0)
            self.assertFalse(result['states'][:,:,g.forbidden].any())
            self.assertTrue(result['states'].any(axis=2).all())
            self.assertGreater(result['states'][:,:,g.center_id].mean(),.05)
            self.assertLess(result['states'][:,:,g.center_id].mean(),.95)
            for chain,trace in enumerate(result['traces']):
                z=trace['initial_state'].copy()
                for update in trace['updates']:
                    i=update['region_id']-1
                    self.assertEqual(bool(z[i]),update['old'])
                    self.assertAlmostEqual(conditional(z,i,g,self.field,s),update['probability'],places=11)
                    z[i]=update['new']
                np.testing.assert_array_equal(z,result['states'][chain,-1])
                self.assertAlmostEqual(terms(z,g,self.field,s)['total'],result['statistics'][chain,-1,0],places=10)
            states,expected=enumerate_distribution(g,self.field,s)
            ids=np.flatnonzero(~g.forbidden)
            integer=(result['states'][:,:,ids]*(2**np.arange(len(ids)))).sum(axis=2)
            observed=np.bincount(integer.ravel(),minlength=2**len(ids))[1:]/integer.size
            tv=.5*abs(observed-expected).sum()
            from common.io import write_json
            write_json(OUTPUT/'validation/exact_distribution.json',dict(
                states_enumerated=len(expected),retained_draws=integer.size,total_variation=float(tv),
                total_variation_limit=.075,probability_sum=float(expected.sum()),
                state_integer_ids=list(range(1,len(expected)+1)),exact_probabilities=expected,
                observed_probabilities=observed,settings=asdict(s),
                center_selected_fraction=float(result['states'][:,:,g.center_id].mean()),
                temperatures=[1.,1.7,3.],source='5x5 partition fixture; 9 eligible interior bits; nonempty subsets'))
            self.assertLess(tv,.075)
            self.assertTrue(diagnose(result['statistics'])['passed'])

    def test_sampler_reproducibility(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as folder:
            args=(folder,self.g,self.field,self.settings,90210)
            a=run_sampler(*args,burn=16,draws=16,thin=1,chains=2,temperatures=(1.,2.))
            b=run_sampler(*args,burn=16,draws=16,thin=1,chains=2,temperatures=(1.,2.))
            np.testing.assert_array_equal(a['states'],b['states'])
            np.testing.assert_array_equal(a['statistics'],b['statistics'])


if __name__=='__main__':unittest.main()
