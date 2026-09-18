"""Read-back checks of deliverables and immutable inputs."""
import numpy as np
from pathlib import Path
from PIL import Image
import bootstrap as b
from coast import load_sample,lengths_on_coast
from render import PALETTE


def audit_outputs(output,seeds):
    from models import FittedFunctions,create_targets
    from allocation import allocate
    functions=FittedFunctions(b.read_json(output/'functions.json'))
    rows=[];replayed=[]
    for seed in seeds:
        sample=load_sample(seed);folder=output/f'seed{seed}'
        types=np.load(folder/'region_types.npy',allow_pickle=False)
        field=np.load(folder/'seafloor_type.npy',allow_pickle=False)
        cfg=b.read_json(folder/'config.json');metrics=b.read_json(folder/'metrics.json')
        with Image.open(folder/'seafloor.png') as pic:im=np.asarray(pic.convert('RGB'))
        actual,segments=lengths_on_coast(sample['coast'],types==2)
        target,info=create_targets(functions,seed,sample['coast'])
        repeated_target,repeated_field,repeated_types,_,_,_,_=allocate(sample,target,info)
        with np.load(folder/'coast_assignment.npz',allow_pickle=False) as saved:
            target_equal=np.array_equal(repeated_target,saved['target_deep'])
        replay=dict(seed=seed,target_equal=target_equal,region_types_equal=np.array_equal(types,repeated_types),
                    field_equal=np.array_equal(field,repeated_field),targets_record_equal=info==b.read_json(folder/'targets.json'))
        replay['passed']=all(v for k,v in replay.items() if k!='seed');replayed.append(replay)
        checks=dict(shape_dtype=field.shape==(500,500) and field.dtype==np.uint8,
             whole_regions=np.array_equal(field,types[sample['labels']-1]),
             platform_unchanged=np.array_equal(field==0,sample['mask']),
             type_domain=bool(np.isin(field,[0,1,2]).all()),
             png_exact=np.array_equal(im,PALETTE[np.flipud(field)]),
             coast_fraction=np.isclose(actual.mean(),metrics['actual_deep_coast_fraction']),
             segment_length_sum=sum(r['length_km'] for r in segments)==len(sample['coast'].xy),
             input_hashes=all(b.file_sha256(sample['path']/name)==h for name,h in cfg['input_sha256'].items()),
             seed_reproducibility=replay['passed'],
             both_types_for_mixed=(metrics['regime']!='mixed' or ((actual==1).any() and (actual==0).any())),
             correct_uniform=(metrics['regime']=='mixed' or np.all(actual==(metrics['regime']=='all_deep'))))
        rows.append(dict(seed=seed,checks=checks,passed=bool(all(checks.values()))))
    quality=b.read_json(output/'reference/quality.json');references=b.read_json(output/'reference/landmasses.json')
    reference_checks=dict(station_counts=sum(quality['class_counts'].values())==sum(r['stations'] for r in references),
         cohort_size=len(references)==len({r['id'] for r in references})==34,
         function_population=b.read_json(output/'functions.json')['environment']['n']==34,
         reference_hashes=all(b.file_sha256(Path(r['path']))==r['sha256'] for r in b.read_json(output/'reference/sources.json')))
    b.write_json(output/'reproducibility.json',dict(results=replayed,passed=all(r['passed'] for r in replayed),
         method='regenerate each seed from fitted functions and frozen input masks; compare targets, all region labels, and all cell labels'))
    return dict(samples=len(rows),results=rows,reference_checks=reference_checks,
                passed=all(r['passed'] for r in rows) and all(reference_checks.values()),
                interpretation='data consistency only; fit residuals remain explicit, no naturalness pass is asserted')
