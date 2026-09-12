"""Standalone seafloor-type pipeline; input masks are always read-only."""
import argparse
import json
import platform
import sys
import time
from pathlib import Path
import bootstrap as b
import numpy as np
from coast import load_sample,measure_width
from reference import prepare_reference
from models import fit_functions,FittedFunctions,create_targets


def prepare(output,seeds):
    rows=[]
    for seed in seeds:
        sample=load_sample(seed);row,arrays=measure_width(sample);rows.append(row)
        row['input_sha256']={name:b.file_sha256(sample['path']/name) for name in ('mask.npy','partitions.npy','contours.json','config.json')}
        folder=output/'distance'/f'seed{seed}';folder.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(folder/'measurement.npz',**arrays)
        print(f'width seed {seed}: mean {row["mean_width_km"]:.3f} km ({row["outer_coast_km"]} edges)',flush=True)
    mean=float(np.mean([r['mean_width_km'] for r in rows]));offset=int(np.floor(mean+.5))
    record=dict(mean_width_km=mean,observation_distance_km=offset,samples=rows,
          averaging='equal weight per selected sample; each sample uses length-weighted outer cell edges',
          measurement='outward chord normal across five edge midpoints (4 km arc span), first platform or domain boundary, 0.5 km ray spacing',
          rounding='nearest integer kilometre to reuse the stored 1 km F profiles',
          internal_holes='excluded from outer-coast width measurements')
    b.write_json(output/'distance.json',record)
    landmasses,segments,quality=prepare_reference(offset,output/'reference')
    functions=fit_functions(landmasses,segments)
    functions.record['inputs']=dict(observation_distance_km=offset,
          landmasses_sha256=b.file_sha256(output/'reference/landmasses.json'),
          segments_sha256=b.file_sha256(output/'reference/segments.json'))
    b.write_json(output/'functions.json',functions.record)
    print('reference',quality['regime_counts'],'known coast fraction',quality['known_coast_fraction_mean'],flush=True)
    print('fitted functions',json.dumps(functions.record,ensure_ascii=False),flush=True)
    return record,functions


def generate(output,seeds):
    from allocation import allocate
    from render import save_sample,save_overview,plot_fits
    functions=FittedFunctions(b.read_json(output/'functions.json'))
    distance=b.read_json(output/'distance.json')
    measured={r['seed']:r for r in distance['samples']}
    if functions.record['inputs']['observation_distance_km']!=distance['observation_distance_km']:
        raise ValueError('Fitted observation distance does not match preparation')
    for name in ('landmasses','segments'):
        if b.file_sha256(output/f'reference/{name}.json')!=functions.record['inputs'][name+'_sha256']:
            raise ValueError('Prepared reference data changed; rerun the prepare stage')
    summaries=[];sources=[]
    for seed in seeds:
        started=time.perf_counter();sample=load_sample(seed)
        if seed not in measured or any(b.file_sha256(sample['path']/name)!=h for name,h in measured[seed]['input_sha256'].items()):
            raise ValueError('Selected mask input differs from the width measurement; rerun prepare')
        target,info=create_targets(functions,seed,sample['coast'])
        target,field,region_types,actual,target_segments,segments,metrics=allocate(sample,target,info)
        folder=output/f'seed{seed}';folder.mkdir(parents=True,exist_ok=True)
        np.save(folder/'seafloor_type.npy',field);np.save(folder/'region_types.npy',region_types)
        np.savez_compressed(folder/'coast_assignment.npz',xy_km=sample['coast'].xy,ring_id=sample['coast'].ring_ids,
              sea_region_id=sample['coast'].sea_regions+1,target_deep=target,actual_deep=actual)
        b.write_json(folder/'targets.json',info);b.write_json(folder/'target_segments.json',target_segments)
        b.write_json(folder/'actual_segments.json',segments)
        metrics['wall_s']=time.perf_counter()-started
        b.write_json(folder/'metrics.json',metrics)
        identities={name:b.file_sha256(sample['path']/name) for name in ('mask.npy','partitions.npy','contours.json','config.json')}
        b.write_json(folder/'config.json',dict(seed=seed,version=b.VERSION,input_directory=str(sample['path']),
              input_sha256=identities,functions_sha256=b.file_sha256(output/'functions.json'),
              type_codes={'0':'platform mask','1':'shallow','2':'deep'},
              observation_distance_km=b.read_json(output/'distance.json')['observation_distance_km'],
              source_partition_count=512,source_boundary_layers=3,
              coordinate_system='x right, y up, km; NPY first row at bottom; PNG first row at top'))
        save_sample(folder,sample,field,region_types,target,actual,metrics)
        summaries.append(metrics);sources.append(dict(seed=seed,directory=str(sample['path']),sha256=identities))
        print(f'seed {seed}: {info["regime"]}; deep coast {metrics["actual_deep_coast_fraction"]:.3f} '
              f'target {info["deep_fraction_target"]:.3f}; ratio error {metrics["ratio_error_pp"]:.3f} pp',flush=True)
    b.write_json(output/'samples.json',summaries);b.write_json(output/'input_masks.json',sources)
    save_overview(output,summaries);plot_fits(output,functions)
    from audit import audit_outputs
    audit=audit_outputs(output,seeds)
    b.write_json(output/'audit.json',audit)
    if not audit['passed']:raise RuntimeError('Output audit failed; see audit.json')
    from render import write_report
    write_report(output,summaries,audit)
    return summaries


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=('all','prepare','generate','audit','test'),default='all')
    ap.add_argument('--output',type=Path,default=b.OUTPUT)
    ap.add_argument('--seeds',nargs='+',type=int,default=list(b.SEEDS))
    a=ap.parse_args()
    try:
        import psutil
        proc=psutil.Process();allowed=proc.cpu_affinity();proc.cpu_affinity([allowed[0]])
    except (ImportError,AttributeError):pass
    output=a.output.resolve()
    protected=[b.MASK_BATCH.resolve(),b.MASK_CODE.resolve(),b.REFERENCE.resolve()]
    if any(p==output or p in output.parents or output in p.parents for p in protected):
        raise ValueError('Output must not overlap source code, reference data, or the mask input batch')
    marker=output/'.seafloor_generator.json'
    if output.exists() and any(output.iterdir()) and not marker.exists():
        # Accept the first development batch only when its own manifest identifies it.
        manifest=output/'manifest.json'
        if not manifest.exists() or b.read_json(manifest).get('version')!=b.VERSION:
            raise ValueError('Refusing an existing nonempty output directory without this generator identity')
    output.mkdir(parents=True,exist_ok=True)
    if marker.exists() and b.read_json(marker).get('generator')!='seafloor_generator':
        raise ValueError('Output directory identity belongs to another generator')
    if not marker.exists():b.write_json(marker,dict(generator='seafloor_generator',version=b.VERSION))
    if a.stage in ('all','test'):
        import unittest
        suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent/'tests'))
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        b.write_json(output/'tests.json',dict(tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),passed=result.wasSuccessful()))
        if not result.wasSuccessful():raise SystemExit(1)
    if a.stage in ('all','prepare'):prepare(output,a.seeds)
    if a.stage in ('all','generate'):generate(output,a.seeds)
    if a.stage=='audit':
        from audit import audit_outputs
        result=audit_outputs(output,a.seeds);b.write_json(output/'audit.json',result)
        if not result['passed']:raise SystemExit(1)
    if a.stage in ('all','generate'):
        import scipy,shapely,PIL,matplotlib
        files=[p for p in Path(__file__).parent.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        reused=[b.MASK_CODE/'common/io.py',b.MASK_CODE/'common/render.py',b.MASK_CODE/'world_orogen_gibbs/geometry.py',b.MASK_CODE/'world_orogen/partitions.py',b.MASK_CODE/'world_orogen/noise.py']
        b.write_json(output/'manifest.json',dict(version=b.VERSION,python=sys.version,platform=platform.platform(),
             libraries=dict(numpy=np.__version__,scipy=scipy.__version__,shapely=shapely.__version__,pillow=PIL.__version__,matplotlib=matplotlib.__version__),
             code=[dict(path=str(p),sha256=b.file_sha256(p)) for p in files],
             reused_read_only=[dict(path=str(p),sha256=b.file_sha256(p)) for p in reused],
             output=[dict(path=str(p.relative_to(output)),sha256=b.file_sha256(p)) for p in output.rglob('*') if p.is_file() and p.name!='manifest.json']))


if __name__=='__main__':main()
