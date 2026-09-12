import itertools
import unittest
import numpy as np
from coast import Coast,known_binary_runs,circular_runs,outer_edges,measure_width
from models import fit_functions,FittedFunctions
from allocation import fit_coast_regions


class Tests(unittest.TestCase):
    def test_outer_perimeter_and_width_use_kilometres(self):
        mask=np.zeros((500,500),bool);mask[200:300,200:300]=True
        labels=np.where(mask,2,1)
        contours={'components':[{'outer':[[200,200],[300,200],[300,300],[200,300],[200,200]]}]}
        coast=outer_edges(contours,labels,mask)
        self.assertEqual(len(coast.xy),400)
        self.assertTrue((coast.sea_regions==0).all())
        row,arrays=measure_width(dict(coast=coast,mask=mask,seed=0))
        # A middle point on each straight side has exactly 200 km of open water.
        for point in ([250.5,200],[300,250.5],[250.5,300],[200,250.5]):
            pos=np.flatnonzero(np.all(coast.xy==point,axis=1))[0]
            self.assertAlmostEqual(arrays['width_km'][pos],200.)
        self.assertEqual(row['stop_at_platform'],0)
        self.assertEqual(row['stop_at_domain_edge'],400)

    def test_unknown_run_boundaries_are_censored_and_not_filled(self):
        x=np.array([0,0,-1,1,1,1,-1,0,0])
        merged,rows,count=known_binary_runs(x,1,lmin=10)
        self.assertTrue(np.array_equal(merged,x));self.assertEqual(count,0)
        self.assertTrue(all(r['censored'] for r in rows))

    def test_circular_runs_merge_across_origin(self):
        rows=circular_runs([0,0,1,1,0])
        self.assertEqual(sorted((r['label'],r['count']) for r in rows),[(0,3),(1,2)])
        self.assertEqual(circular_runs([1]*7),[dict(start=0,count=7,label=1)])

    def test_complete_short_runs_merge_without_losing_length(self):
        result,rows,count=known_binary_runs([0]*12+[1]*2+[0]*12+[1]*20,1,10)
        self.assertEqual(count,1);self.assertEqual(sum(r['count'] for r in rows),46)
        self.assertEqual(sorted(r['count'] for r in rows),[20,26])

    def test_whole_region_conflict_approximates_target(self):
        owners=np.array([0,0,0,1,1,2,2,3,3,3])
        coast=Coast(np.zeros((10,2)),np.zeros((10,2)),owners,np.zeros(10,int),[slice(0,10)],np.arange(10))
        target=np.array([1,1,0,0,0,1,1,0,0,0],bool)
        state,info=fit_coast_regions(coast,target,.4,4)
        self.assertTrue(info['optimal']);self.assertEqual(len(state),4)
        # Four indivisible region weights: brute-force verifies the minimum attainable ratio discrepancy.
        errors=[abs(np.array(s,dtype=bool)[owners].mean()-.4) for s in itertools.product([False,True],repeat=4) if 0<sum(s)<4]
        self.assertAlmostEqual(abs(state[owners].mean()-.4),min(errors))

    def test_fitted_generator_creates_new_values_and_repeats_seed(self):
        lm=[dict(regime='all_shallow',deep_share_known_water=0)]*3+[dict(regime='mixed',deep_share_known_water=q) for q in (.15,.3,.5,.75)]
        seg=[]
        for typ in ('deep','shallow'):
            for i,x in enumerate((12.,19.,28.,44.,75.,110.)):
                seg.append(dict(used_for_fit=True,environment=typ,landmass_id=str(i%3),length_km=x,censored=False))
        f=fit_functions(lm,seg);rng=np.random.default_rng(7);draws=np.array([f.mixed_deep_fraction(rng) for _ in range(100)])
        other=np.random.default_rng(7)
        self.assertTrue(np.array_equal(draws,[f.mixed_deep_fraction(other) for _ in range(100)]))
        self.assertTrue(np.all((draws>0)&(draws<1)))
        self.assertFalse(np.isin(draws,[.15,.3,.5,.75]).any())
        self.assertEqual(f.record['environment']['probabilities'][2],0.)


if __name__=='__main__':unittest.main()
