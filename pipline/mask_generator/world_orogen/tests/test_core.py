from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy import ndimage as ndi
from scipy.special import softmax

from research.selection_model_check import fixture,all_features
from world_orogen.config import Settings
from world_orogen.noise import SimplexNoise
from world_orogen.partitions import generate_partitions,reconnect_pixels,L4
from world_orogen.selection import RegionGeometry,geometry_from_labels,candidate_probabilities,generate_mask,select_whole_regions
from world_orogen.export import export_sample


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        labels,areas,moments,neighbors,root=fixture()
        adjacency=[[j for j in range(14) if b&(1<<j)] for b in neighbors]
        cls.geometry=RegionGeometry(areas,moments,adjacency,np.zeros((14,2)),1.,(.5,.5))
        cls.features=all_features(areas,moments,neighbors)

    def test_optimized_probabilities_match_full_recomputation(self):
        for state in (1<<6,(1<<6)|(1<<8),(1<<6)|(1<<8)|(1<<0),3456):
            selected=np.array([bool(state&(1<<i)) for i in range(14)])
            result=candidate_probabilities(selected,self.geometry,24,8)
            destinations=state|(1<<result['candidates'])
            energy=24*self.features['radius2']+8*self.features['fragmentation']
            expected=softmax(-(energy[destinations]-energy[state]))
            np.testing.assert_allclose(result['probabilities'],expected,atol=1e-13)
            np.testing.assert_allclose(result['next_q'],1-self.features['fragmentation'][destinations],atol=1e-13)

    def test_nonadjacent_candidates_remain_eligible(self):
        selected=np.zeros(14,bool);selected[6]=True
        result=candidate_probabilities(selected,self.geometry,24,8)
        self.assertEqual(len(result['candidates']),13)
        self.assertTrue((result['probabilities']>0).all())
        self.assertTrue((~result['touches_selected']).any())

    def test_whole_regions_soft_budget_and_repeatability(self):
        args=(self.geometry,6,.55)
        first=select_whole_regions(*args,np.random.default_rng(2026))
        second=select_whole_regions(*args,np.random.default_rng(2026))
        self.assertEqual(first[1],second[1])
        self.assertEqual(first[3],second[3])
        self.assertGreaterEqual(first[3]['area_km2'],.55)
        self.assertLess(first[3]['area_before_last_region_km2'],.55)
        self.assertEqual(len(first[1]),len(set(first[1])))

    def test_final_fraction_may_exceed_sixty_percent(self):
        geometry=RegionGeometry(np.array([.4,.5216]),np.array([.02,.12]),[[1],[0]],np.zeros((2,2)),1.,(.5,.5))
        result=select_whole_regions(geometry,0,.55,np.random.default_rng(1))
        self.assertEqual(result[1],[1,2])
        self.assertAlmostEqual(result[3]['fraction'],.9216)


class PartitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings=Settings(coarse_side=16,partition_count=8,warp_multiplier=0)
        cls.partition=generate_partitions(73,cls.settings)

    def test_full_coverage_band_connectivity_and_seed_ownership(self):
        p=self.partition
        self.assertEqual(int((p.labels>0).sum()),480*480)
        self.assertTrue((p.labels[:10]==0).all())
        self.assertTrue((p.labels[-10:]==0).all())
        self.assertTrue((p.labels[:,:10]==0).all())
        self.assertTrue((p.labels[:,-10:]==0).all())
        for rid,(x,y) in enumerate(p.seeds_xy,1):
            self.assertEqual(p.labels[int(y),int(x)],rid)
            self.assertEqual(ndi.label(p.labels==rid,L4)[1],1)

    def test_partitions_replay(self):
        replay=generate_partitions(73,self.settings)
        np.testing.assert_array_equal(self.partition.labels,replay.labels)
        np.testing.assert_array_equal(self.partition.coarse_labels,replay.coarse_labels)

    def test_geometry_moments_cover_entire_cells(self):
        labels=np.zeros((500,500),np.int16);labels[10:490,10:490]=1
        geometry=geometry_from_labels(labels)
        self.assertEqual(geometry.areas[0],480*480)
        self.assertAlmostEqual(geometry.second_moments[0]/geometry.areas[0],480**2/6,places=6)
        np.testing.assert_allclose(geometry.centers_xy[0],[250,250])

    def test_reconnection_preserves_partitioned_area(self):
        labels=np.zeros((20,20),np.int16)
        labels[2:18,2:10]=1;labels[2:18,10:18]=2
        labels[5,14]=1
        before=labels>0
        record=reconnect_pixels(labels,np.array([[8,6],[8,14]]),2)
        self.assertEqual(record['raster_connectivity_reassigned_cells'],1)
        np.testing.assert_array_equal(before,labels>0)
        self.assertEqual(ndi.label(labels==1,L4)[1],1)

    def test_export_four_stages_and_exact_data(self):
        result=generate_mask(self.partition)
        with tempfile.TemporaryDirectory() as temporary:
            sample=export_sample(self.partition,result,Path(temporary))
            self.assertTrue(all(sample['status']['checks'].values()))
            self.assertTrue((Path(temporary)/'four_stages.png').is_file())

    def test_simplex_matches_fixed_upstream_values(self):
        # Evaluated with original js/simplex-noise.js at the pinned commit, seed 2000.
        points=np.array([[0,0,0],[.1,.2,.3],[2.1,-1.2,3.3],[-1,-2,-3],[.2,.1,0],[8,8,0]])
        expected=[0,.4933029759999997,.05951362133333342,0,-.5822266666666663,-.7600995884773672]
        values=SimplexNoise(2000).noise3d(*points.T)
        np.testing.assert_allclose(values,expected,atol=1e-12)
