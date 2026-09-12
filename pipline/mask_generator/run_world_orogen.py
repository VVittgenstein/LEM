"""Run the planar World Orogen adaptation and produce four-stage deliveries."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
    os.environ[name]='1'
os.environ['MPLBACKEND']='Agg'

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import replace
from pathlib import Path
import multiprocessing as mp
import time
import traceback
import unittest

from common.io import read_csv,read_json,utc_now,write_csv,write_json
from common.runtime import configure_process_tree,worker_initializer
from world_orogen.config import COUNTS,DEFAULT_OUTPUT,DISPLAY_SEEDS,ROOT,Settings,run_settings


def generate_job(seed,settings,output):
    from world_orogen.partitions import generate_partitions
    from world_orogen.selection import generate_mask
    from world_orogen.export import export_sample
    partition=generate_partitions(seed,settings)
    result=generate_mask(partition)
    return export_sample(partition,result,Path(output)/f'partitions_{settings.partition_count}'/f'seed{seed}')


def diagnostic_job(seed,settings,counts):
    from world_orogen.partitions import point_graph,generate_partitions
    from world_orogen.selection import generate_mask
    from common.metrics import shape_metrics
    graph=point_graph(seed,settings)
    rows=[]
    for count in counts:
        own=replace(settings,partition_count=count)
        partition=generate_partitions(seed,own,graph)
        result=generate_mask(partition,record_trace=False)
        metrics=shape_metrics(result.mask)
        rows.append({'seed':seed,'partition_count':count,'target_fraction':result.target_fraction,
            **result.statistics,'axis_ratio':metrics['axis_ratio'],'shoreline_development':metrics['shoreline_development'],
            'partition_reassigned_fraction':partition.record['raster_reassigned_fraction']})
    return rows


def run_jobs(jobs,worker,cpus,label):
    if len(cpus)==1:
        results=[]
        for index,args in enumerate(jobs,1):
            results.append(worker(*args));print(f'{label} {index}/{len(jobs)}',flush=True)
        return results
    results=[]
    with ProcessPoolExecutor(max_workers=len(cpus)-1,mp_context=mp.get_context('spawn'),
        initializer=worker_initializer,initargs=(cpus[1:],)) as pool:
        futures=[pool.submit(worker,*args) for args in jobs]
        for index,future in enumerate(as_completed(futures),1):
            results.append(future.result());print(f'{label} {index}/{len(jobs)}',flush=True)
    return results


def run_tests(output):
    code=Path(__file__).resolve().parent
    suite=unittest.defaultTestLoader.discover(str(code/'world_orogen/tests'),top_level_dir=str(code))
    with (output/'tests.log').open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    status={'created_utc':utc_now(),'tests_run':result.testsRun,'passed':result.wasSuccessful(),
            'failures':len(result.failures),'errors':len(result.errors)}
    write_json(output/'tests.json',status)
    print(f"tests: {result.testsRun}, passed={result.wasSuccessful()}",flush=True)
    if not result.wasSuccessful():
        print((output/'tests.log').read_text(encoding='utf-8'),flush=True)
        raise RuntimeError('World Orogen tests failed')


def reference_comparison(output,samples):
    import numpy as np
    path=ROOT/'output/mask_generator/reference/reference_metrics.csv'
    if not path.is_file():
        write_json(output/'reference_comparison.json',{'status':'reference table not available','expected_path':str(path)})
        return
    rows=read_csv(path)
    if len(rows)!=34:raise RuntimeError('expected 34 reference members')
    summary={key:{'p05_p50_p95':np.quantile([float(r[key]) for r in rows],[.05,.5,.95]).tolist()}
             for key in ('area_km2','axis_ratio','shoreline_development')}
    write_json(output/'reference_comparison.json',{'reference_count':34,'source':str(path),'reference_summary':summary,
        'sample_values':[{'seed':s['seed'],'partition_count':s['partition_count'],**{k:s['metrics'][k] for k in summary}} for s in samples],
        'status':'diagnostic only; no fitting or distribution-equality claim',
        'note':'参考成员面积不同，原始分布只用于展示概况；未沿用旧轴比回归截断模型。'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--workers',type=int,choices=range(1,9),default=8)
    parser.add_argument('--stage',choices=('all','test','generate','diagnose','report'),default='all')
    parser.add_argument('--partition-counts',type=int,nargs='+',default=list(COUNTS))
    parser.add_argument('--seeds',type=int,nargs='+',default=list(DISPLAY_SEEDS))
    parser.add_argument('--diagnostic-count',type=int,default=64)
    parser.add_argument('--center-weight',type=float,default=24.)
    parser.add_argument('--connection-weight',type=float,default=8.)
    parser.add_argument('--coarse-side',type=int,default=96)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    marker=output/'.world_orogen.json'
    if marker.exists():
        if read_json(marker).get('owner')!='LEM planar World Orogen':raise RuntimeError('output identity mismatch')
    else:
        if any(output.iterdir()):raise RuntimeError('output contains existing files without an ownership marker')
        write_json(marker,{'owner':'LEM planar World Orogen','created_utc':utc_now()})
    os.environ['MPLCONFIGDIR']=str(output/'cache/matplotlib')
    cpus=configure_process_tree(args.workers)
    settings=Settings(center_weight=args.center_weight,connection_weight=args.connection_weight,coarse_side=args.coarse_side)
    for count in args.partition_counts:replace(settings,partition_count=count).validate()
    if len(set(args.seeds))!=len(args.seeds) or len(set(args.partition_counts))!=len(args.partition_counts):
        raise ValueError('duplicate seeds or partition counts')
    if args.diagnostic_count<0:raise ValueError('diagnostic-count must be nonnegative')
    start=time.perf_counter()
    write_json(output/'run_status.json',{'state':'running','stage':args.stage,'started_utc':utc_now(),
                                      'process_budget_including_coordinator':len(cpus),'one_cpu_per_process':True})
    try:
        if args.stage in ('all','test'):run_tests(output)
        if args.stage=='test':
            write_json(output/'run_status.json',{'state':'tests_passed','finished_utc':utc_now()});return
        from world_orogen.export import read_samples,write_summary,manifest
        from world_orogen.render import comparison,weight_comparison
        from world_orogen.report import write_report
        if args.stage in ('all','generate'):
            if (output/'visual_review.json').exists():
                write_json(output/'previous_visual_review.json',read_json(output/'visual_review.json'))
                write_json(output/'visual_review.json',{'summary':'本批次重新生成，图像观察待更新。'})
            jobs=[(seed,replace(settings,partition_count=count),str(output)) for count in args.partition_counts for seed in args.seeds]
            run_jobs(jobs,generate_job,cpus,'four-stage sample')
        samples=read_samples(output,args.partition_counts,args.seeds)
        if args.stage in ('all','diagnose') and args.diagnostic_count:
            import numpy as np
            batches=run_jobs([(s,settings,args.partition_counts) for s in range(2001,2001+args.diagnostic_count)],diagnostic_job,cpus,'diagnostic seed')
            rows=sorted([r for batch in batches for r in batch],key=lambda r:(r['partition_count'],r['seed']))
            write_csv(output/'distribution.csv',rows)
            groups=[]
            for count in args.partition_counts:
                subset=[r for r in rows if r['partition_count']==count]
                groups.append({'partition_count':count,'n':len(subset),'one_component_count':sum(r['region_component_count']==1 for r in subset),
                    'three_or_more_count':sum(r['region_component_count']>=3 for r in subset),
                    'area_above_60_count':sum(r['fraction']>.6 for r in subset),
                    'median_center_offset_km':float(np.median([r['centroid_offset_km'] for r in subset]))})
            write_json(output/'distribution.json',{'created_utc':utc_now(),'groups':groups,
                'seeds':list(range(2001,2001+args.diagnostic_count)),'settings':run_settings(settings,args.partition_counts),
                'scope':'observed finite-batch counts; no parameter fitting or rare-event probability certification'})
        summary=write_summary(output,samples)
        comparison(output,samples,args.partition_counts,args.seeds)
        weight_comparison(output,args.seeds)
        reference_comparison(output,samples)
        quality={'created_utc':utc_now(),'samples':len(samples),'primary_masks':len(list(output.glob('partitions_*/seed*/mask.npy'))),
            'four_stage_images':len(list(output.glob('partitions_*/seed*/four_stages.png'))),
            'all_sample_checks_passed':all(all(s['status']['checks'].values()) for s in samples),
            'tests':read_json(output/'tests.json') if (output/'tests.json').exists() else {'passed':None},
            'process_budget_including_coordinator':len(cpus),'threads_per_process':1,
            'browser_validation':'not performed; static local artifacts and pixel correspondence checked'}
        if not quality['all_sample_checks_passed']:raise RuntimeError('a sample failed verification')
        write_json(output/'quality.json',quality)
        write_report(output,samples,args.partition_counts)
        manifest(output,settings,args.partition_counts,args.seeds)
        write_json(output/'run_status.json',{'state':'complete','stage':args.stage,'finished_utc':utc_now(),
            'wall_s':time.perf_counter()-start,'samples':len(samples),'visual_acceptance':'awaiting_user_review'})
        print(f"completed {len(samples)} samples in {time.perf_counter()-start:.1f}s: {output}",flush=True)
    except Exception:
        write_json(output/'run_status.json',{'state':'failed','stage':args.stage,'traceback':traceback.format_exc()})
        raise


if __name__=='__main__':main()
