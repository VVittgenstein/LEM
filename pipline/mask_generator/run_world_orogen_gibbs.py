"""Entry point for the second World Orogen platform-mask experiment."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import replace
from pathlib import Path
import sys,time
from world_orogen_gibbs.config import COUNTS,DEFAULT_BOUNDARY_LAYERS,default_output_for


def build_parser():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=('all','pilot','test','generate','report','audit','diagnose'),default='all')
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--partition-counts',type=int,nargs='+',default=list(COUNTS),help='partition counts; selected default: 512')
    parser.add_argument('--seeds',type=int,nargs='+',default=list(range(1001,1007)))
    parser.add_argument('--burn',type=int,default=4096)
    parser.add_argument('--draws',type=int,default=2048)
    parser.add_argument('--thin',type=int,default=4)
    parser.add_argument('--boundary-layers',type=int,help='exclude this many whole partition layers; outer touching regions are layer 1')
    return parser


def main():
    parser=build_parser()
    args=parser.parse_args()
    if not 2<=args.workers<=8:parser.error('--workers must be between 2 and 8 including sampler children')
    if args.boundary_layers is not None and args.boundary_layers<1:parser.error('--boundary-layers must be positive')
    from common.runtime import configure_process_tree,worker_initializer
    cpus=configure_process_tree(args.workers)
    from common.io import write_json
    from world_orogen_gibbs.config import Settings,OUTPUT
    from world_orogen_gibbs.sampler import build_kernel
    from world_orogen_gibbs.pipeline import sample_job
    output=args.output or default_output_for(args.partition_counts,args.boundary_layers or DEFAULT_BOUNDARY_LAYERS)
    output.mkdir(parents=True,exist_ok=True)
    if args.stage in ('all','test'):
        import unittest,io,os
        os.environ['LEM_MASK_TEST_OUTPUT']=str(output/'validation')
        build_kernel();stream=io.StringIO()
        suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent/'world_orogen_gibbs/tests'),top_level_dir=str(Path(__file__).parent))
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        (output/'tests.log').write_text(stream.getvalue(),encoding='utf-8')
        write_json(output/'tests.json',dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful()))
        print(stream.getvalue(),flush=True)
        if not result.wasSuccessful():return 1
        if args.stage=='test':return 0
    if args.stage in ('report','audit'):
        from world_orogen_gibbs.delivery import build_delivery,audit_delivery
        (build_delivery if args.stage=='report' else audit_delivery)(output)
        return 0
    build_kernel()
    initial=replace(Settings(),boundary_layers=args.boundary_layers or DEFAULT_BOUNDARY_LAYERS,field_weights=(.20,.55,1.),center_weight=1500.,spread_weight=300.,perimeter_weight=20.,area_weight=40.)
    centered=replace(initial,center_weight=5000.,spread_weight=1800.,perimeter_weight=15.,area_weight=60.)
    multiscale=replace(initial,center_weight=5000.,spread_weight=1600.,perimeter_weight=15.,area_weight=60.,field_weights=(.30,.85,.65))
    jobs=[]
    if args.stage=='pilot':
        for name,setting in [('baseline',initial),('centered',centered),('multiscale',multiscale)]:
            for seed in (7001,7002,7003):
                jobs.append((output/f'pilot/{name}/seed{seed}',seed,setting,1024,512,2,4,(1.,1.4,2.,2.8,4.,5.6,8.)))
    else:
        import json
        config_path=output/'selected_settings.json'
        if not config_path.exists():
            from shutil import copyfile
            copyfile(Path(__file__).parent/'world_orogen_gibbs/experiment.json',config_path)
        record=json.loads(config_path.read_text())
        settings=Settings.from_record(record['settings'])
        if args.boundary_layers is not None:
            for sample_config in output.glob('**/input_identity.json'):
                cached=json.loads(sample_config.read_text())
                if cached.get('selection_domain',{}).get('boundary_layers',1)!=args.boundary_layers:
                    parser.error('output contains another boundary-layer setting; choose a different --output')
            settings=replace(settings,boundary_layers=args.boundary_layers)
            record.update(settings=settings.describe(),boundary_override=dict(layers=args.boundary_layers,source='explicit command line'))
            write_json(config_path,record)
        for count in args.partition_counts:
            for seed in args.seeds:
                root=output/'diagnostic' if args.stage=='diagnose' else output
                jobs.append((root/f'partitions_{count}/seed{seed}',seed,replace(settings,partition_count=count),args.burn,args.draws,args.thin,4,tuple(1.18**i for i in range(14))))
    # Each task owns one Python process and at most one managed sampler child.
    # Coordinator + 3 Python workers + 3 children = 7 processes, each pinned to one CPU.
    if args.workers<3:
        results=[sample_job(*job) for job in jobs]
    else:
        worker_count=min(3,(args.workers-1)//2,len(jobs))
        with ProcessPoolExecutor(max_workers=worker_count,initializer=worker_initializer,initargs=(cpus[1:],)) as pool:
            pending={pool.submit(sample_job,*job):job for job in jobs}
            results=[]
            for future in as_completed(pending):
                result=future.result();results.append(result);print(result,flush=True)
    phase='generate' if args.stage=='all' else args.stage
    write_json(output/f'{phase}_runs.json',results)
    print('completed',len(results),flush=True)
    if args.stage=='all':
        from world_orogen_gibbs.delivery import build_delivery,audit_delivery
        from world_orogen_gibbs.summarize import summarize,seal_manifest
        summarize(output);build_delivery(output);audit_delivery(output);seal_manifest(output)
    return 0


if __name__=='__main__':raise SystemExit(main())
