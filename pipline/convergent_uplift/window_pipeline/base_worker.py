"""Run the copied, accepted three-stage input pipeline in this module."""
import sys,time
from wcontext import *

def main():
    init();sys.path.insert(0,str(VENDOR/'mask_generator'))
    from world_orogen_gibbs.config import Settings
    from world_orogen_gibbs.pipeline import sample_job
    from world_orogen_gibbs.sampler import build_kernel
    from common.contours import extract_contours
    selected=load(VENDOR/'mask_generator/world_orogen_gibbs/experiment.json');settings=Settings.from_record(selected['settings'])
    sampling=selected['sampling'];build_kernel();rows=[]
    for seed in range(1001,1009):
        p=BASE/'masks'/f'seed{seed}'
        if not (p/'mask.npy').exists():
            summary=sample_job(p,seed,settings,sampling['burn'],sampling['draws'],sampling['thin'],sampling['chains'],tuple(sampling['temperatures']))
            print('mask',seed,summary['fraction'],summary['wall_s'],flush=True)
        m=np.load(p/'mask.npy');save(p/'contours.json',extract_contours(m))
        checks=load(p/'diagnostics.json')
        if not checks['all_passed']:raise RuntimeError(f'Mask sampler diagnostic failed at {seed}; retained for inspection')
    # Each copied stage uses its original functions. Only input/output routing
    # is redirected; no fit parameters or selected sampling settings change.
    sys.path.insert(0,str(VENDOR/'seafloor_generator'))
    import bootstrap as b
    b.MASK_BATCH=BASE/'masks';b.MASK_CODE=VENDOR/'mask_generator';b.OUTPUT=BASE
    from coast import load_sample
    from models import FittedFunctions,create_targets
    from allocation import allocate
    functions=FittedFunctions(load(INPUT/'sea_functions.json'))
    sys.path.insert(0,str(VENDOR/'initial_bathymetry'))
    from surface import generate
    params=load(INPUT/'bathymetry_parameters.json')
    for seed in range(1001,1009):
        p=BASE/f'seed{seed}';p.mkdir(parents=True,exist_ok=True);sample=load_sample(seed);start=time.perf_counter()
        if (p/'base.npz').exists():
            old=load(p/'metadata.json')
            if old['base_sha256']!=sha(p/'base.npz') or old['mask_sha256']!=sha(BASE/f'masks/seed{seed}/mask.npy'):
                raise RuntimeError('Cached base identity changed')
            if old['sea_functions_sha256']!=sha(INPUT/'sea_functions.json') or old['bathymetry_parameters_sha256']!=sha(INPUT/'bathymetry_parameters.json'):
                raise RuntimeError('Cached base parameters changed')
            rows.append(old);continue
        target,info=create_targets(functions,seed,sample['coast'])
        target,field,region_types,actual,target_segments,segments,metrics=allocate(sample,target,info)
        sample['sea_type']=field;sample['region_types']=region_types
        arrays,normalization=generate(sample,params)
        np.savez_compressed(p/'base.npz',mask=sample['mask'],partitions=sample['labels'],sea_type=field,region_types=region_types,
            elevation_m=arrays['elevation'],distance_km=arrays['distance_km'],roughness_m=arrays['roughness'])
        save(p/'sea_targets.json',info);save(p/'sea_metrics.json',metrics)
        config={'seed':seed,'mask_fraction':float(sample['mask'].mean()),'minimum_elevation_m':float(arrays['elevation'].min()),
          'maximum_elevation_m':float(arrays['elevation'].max()),'sea_regime':info['regime'],'seconds':time.perf_counter()-start,
          'mask_diagnostics_passed':load(BASE/f'masks/seed{seed}/diagnostics.json')['all_passed'],
          'mask_sha256':sha(BASE/f'masks/seed{seed}/mask.npy'),'base_sha256':sha(p/'base.npz'),
          'sea_functions_sha256':sha(INPUT/'sea_functions.json'),'bathymetry_parameters_sha256':sha(INPUT/'bathymetry_parameters.json'),
          'grid_km':1.,'shape':[500,500],'coordinates':'cell centers 0.5..499.5, row zero is south',
          'generation':'copied 512-partition / 3 forbidden-layer Gibbs generator, accepted sea-type fit and accepted fixed bathymetry'}
        if seed<=1006:
            old=np.load(REPO/f'output/mask_generator/world_orogen_gibbs_layers_3/partitions_512/seed{seed}/mask.npy')
            config['same_as_earlier_mask']=bool(np.array_equal(old,sample['mask']))
            zold=np.load(REPO/f'output/initial_bathymetry/fixed_profiles_v1/seed{seed}/elevation.npy')
            config['maximum_earlier_elevation_difference_m']=float(np.max(abs(zold-arrays['elevation'])))
        save(p/'metadata.json',config);rows.append(config);print('base',seed,info['regime'],config['seconds'],flush=True)
    save(BASE/'batch.json',{'samples':rows})

if __name__=='__main__':main()
