"""Targeted tests of finite termination, graph topology and scale semantics."""

from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('data_generation/stage/convergent_uplift', 'data_generation/stage/mask_generator', 'data_generation/stage/seafloor_generator', 'viewer', 'data_generation/stage/convergent_uplift'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)

import unittest
import numpy as np
from common import ROOT,rng_for,read_json
from scale_model import training_records,sample
from geometry_metrics import graph_from_edges,validity,long_side
from axis_generator import make_mesh,competitive_labels,interface_chains,is_bridge,screen

class AxisTests(unittest.TestCase):
    def test_source_province_weighting(self):
        rows=training_records();self.assertEqual(len(rows),15);self.assertEqual(sum(r['measurements'] for r in rows),17)
        self.assertEqual(len({r['province_key'] for r in rows}),15)
        self.assertLess(max(r['relative_projection_spread'] for r in rows),.0001)

    def test_seed_stream_independence(self):
        a=sample(1001);rng_for(1001,202).normal(size=10000);b=sample(1001)
        self.assertEqual(a,b);self.assertNotEqual(a[0],sample(1002)[0])

    def test_finite_growth_stops_inside_domain(self):
        mesh=make_mesh(713,1.1)
        plain={'modes':[],'patches':[],'weights':[0,0,0],'rate':1.,'direction_angle':0.,'direction_bias':0.}
        cfg={'starts':[[[-.2,0]],[[.2,0]]],'regions':[plain,plain],'limits':[.65,.65]}
        labels=competitive_labels(mesh,cfg)
        self.assertFalse(np.any(labels[mesh['boundary']]>=0))
        chains=interface_chains(mesh,labels);self.assertGreaterEqual(len(chains),1)
        self.assertTrue(all(np.max(np.abs(p))<.85 for p in chains))
        self.assertTrue(any(np.linalg.norm(p[0]-p[-1])>.9 for p in chains))

    def test_exterior_outlines_not_exported(self):
        mesh={'xy':np.array([[0.,0.],[1.,0.],[0.,1.]]),'tri':np.array([[0,1,2]])}
        self.assertEqual(interface_chains(mesh,np.array([0,-1,-1])),[])
        end=interface_chains(mesh,np.array([0,1,-1]));self.assertEqual(len(end),1)
        np.testing.assert_allclose(end[0][-1],[1/3,1/3])

    def test_three_active_regions_share_junction(self):
        mesh={'xy':np.array([[0.,0.],[1.,0.],[0.,1.]]),'tri':np.array([[0,1,2]])}
        edges=interface_chains(mesh,np.array([0,1,2]));g=graph_from_edges(edges)
        self.assertEqual((len(edges),g['components'],g['junctions'],g['cycles']),(3,1,1,0))
        self.assertEqual(validity(edges),[])

    def test_rejoin_parallel_edges_and_bridge(self):
        edges=[np.array([[-1.,0.],[0.,0.]]),np.array([[0.,0.],[1.,.4],[2.,0.]]),
          np.array([[0.,0.],[1.,-.4],[2.,0.]]),np.array([[2.,0.],[3.,0.]])]
        g=graph_from_edges(edges);self.assertEqual((g['components'],g['junctions'],g['cycles']),(1,2,1))
        self.assertTrue(is_bridge(edges,0));self.assertFalse(is_bridge(edges,1));self.assertEqual(validity(edges),[])

    def test_unmarked_crossing_rejected(self):
        p=[np.array([[0.,0.],[1.,1.]]),np.array([[0.,1.],[1.,0.]])]
        self.assertTrue(any('undeclared_intersection' in r for r in validity(p)))

    def test_arc_and_extent_are_distinct(self):
        p=np.array([[0.,0.],[.8,.7],[2.,0.]])
        L,_=long_side([p]);arc=np.linalg.norm(np.diff(p,axis=0),axis=1).sum();self.assertGreater(arc,L)
        transformed=(p+[19,-7])*17
        self.assertAlmostEqual(long_side([transformed])[0],L*17,places=10)

    def test_visual_false_contact_is_rejected(self):
        reference=read_json(ROOT/'tables/geometry_reference.json')
        edges=[np.array([[0.,0.],[0.,1.]]),np.array([[.5,.5],[.003,.5]])]
        self.assertTrue(any('free_tip_ambiguous_contact' in r for r in screen(edges,reference)))

if __name__=='__main__':unittest.main(verbosity=2)
