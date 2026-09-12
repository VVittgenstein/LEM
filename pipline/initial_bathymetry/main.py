"""Create the fixed-parameter initial bathymetry and its contour/section deliverables."""
import argparse
from pathlib import Path
import platform
import sys
import time
import context as c
import numpy as np


def output_directory(path):
    path=path.resolve();marker=path/'.initial_bathymetry.json'
    protected=[c.MASK_BATCH,c.SEA_BATCH,c.F_STATIONS,c.MASK_CODE,c.SEA_CODE,c.CODE]
    if any(p.resolve()==path or p.resolve() in path.parents or path in p.resolve().parents for p in protected):
        raise ValueError('Output directory overlaps an input or source-code directory')
    if path.exists() and any(path.iterdir()) and not marker.exists():
        raise ValueError('Existing nonempty output directory is not owned by initial_bathymetry')
    path.mkdir(parents=True,exist_ok=True)
    if marker.exists() and c.read_json(marker).get('generator')!='initial_bathymetry':
        raise ValueError('Output identity mismatch')
    if not marker.exists():c.write_json(marker,dict(generator='initial_bathymetry',version=c.VERSION))
    return path


def generate_batch(output,seeds,params):
    from surface import generate
    from checks import metrics
    from figures import save_sample,save_overview,save_fixed_profiles,save_report
    if not c.check_hashes(c.read_json(output/'reference/sources.json')):
        raise ValueError('Prepared reference inputs changed; rerun prepare')
    rows=[]
    for seed in seeds:
        start=time.perf_counter();sample=c.load_input(seed)
        arrays,normalization=generate(sample,params)
        folder=output/f'seed{seed}';folder.mkdir(parents=True,exist_ok=True)
        for name,value in arrays.items():np.save(folder/(name+'.npy'),value)
        stat=metrics(sample,arrays,params,normalization)
        save_sample(folder,sample,arrays,params,stat)
        stat['wall_seconds']=time.perf_counter()-start
        c.write_json(folder/'metrics.json',stat)
        c.write_json(folder/'config.json',dict(seed=seed,version=c.VERSION,parameters_sha256=c.file_sha256(output/'parameters.json'),
              input_files=sample['source_hashes'],grid_shape=[500,500],grid_spacing_km=1.,
              coordinates='cell centres x,y = 0.5..499.5 km, x right/y up; NPY row zero at bottom',
              vertical_reference='initial sea level 0 m, elevations negative underwater'))
        rows.append(stat)
        print(f'seed {seed}: elevation {arrays["elevation"].min():.2f}..{arrays["elevation"].max():.2f} m; {stat["wall_seconds"]:.2f} s',flush=True)
    c.write_json(output/'samples.json',rows)
    save_fixed_profiles(output,params);save_overview(output,seeds,params);save_report(output,rows,params)
    return rows


def manifest(output):
    import scipy,matplotlib,PIL
    reused=[c.MASK_CODE/'common/io.py',c.MASK_CODE/'common/render.py',c.MASK_CODE/'world_orogen_gibbs/geometry.py',
            c.SEA_CODE/'coast.py',c.SEA_CODE/'bootstrap.py']
    c.write_json(output/'manifest.json',dict(version=c.VERSION,python=sys.version,platform=platform.platform(),
        libraries=dict(numpy=np.__version__,scipy=scipy.__version__,matplotlib=matplotlib.__version__,pillow=PIL.__version__),
        code=[dict(path=str(p),sha256=c.file_sha256(p)) for p in c.CODE.rglob('*') if p.is_file() and '__pycache__' not in p.parts],
        reused_read_only=[dict(path=str(p),sha256=c.file_sha256(p)) for p in reused],
        output=[dict(path=str(p.relative_to(output)),sha256=c.file_sha256(p)) for p in output.rglob('*') if p.is_file() and p.name!='manifest.json']))


def render_existing(output,seeds):
    from figures import save_map,save_overview,save_report
    from scipy.ndimage import map_coordinates
    params=c.read_json(output/'parameters.json')
    protected=list(output.rglob('*.npy'))+[output/'parameters.json']
    for seed in seeds:
        protected.extend(output/f'seed{seed}'/name for name in ('metrics.json','config.json','sections.json','contour_lines.json','profiles.png','roughness.png'))
    before={str(p):c.file_sha256(p) for p in protected}
    rows=[]
    for seed in seeds:
        sample=c.load_input(seed);folder=output/f'seed{seed}'
        arrays={name:np.load(folder/(name+'.npy'),allow_pickle=False) for name in ('elevation','distance_km')}
        boundaries=save_map(folder,sample,arrays,params)
        errors=[];vertices=0
        for item in boundaries:
            for part in item['parts']:
                field={'platform_mask':sample['mask'].astype(float),
                       'deep_type_indicator':(sample['sea_type']==2).astype(float),
                       'distance_km':arrays['distance_km']}[part['field']]
                for line in part['lines']:
                    xy=np.asarray(line);value=map_coordinates(field,[xy[:,1]-.5,xy[:,0]-.5],order=1,mode='nearest')
                    errors.extend(abs(value-part['level']));vertices+=len(xy)
        maximum=float(max(errors,default=0.))
        rows.append(dict(seed=seed,boundary_vertices=vertices,max_level_error=maximum,passed=maximum<1e-7 and vertices>0))
        print(f'render seed {seed}: {vertices} boundary vertices',flush=True)
    save_overview(output,seeds,params)
    save_report(output,c.read_json(output/'samples.json'),params)
    unchanged=all(c.file_sha256(Path(p))==h for p,h in before.items())
    result=dict(style='structural-red-lines-v1',immutable_files=len(before),data_and_profiles_unchanged=unchanged,
                rows=rows,passed=unchanged and all(r['passed'] for r in rows))
    c.write_json(output/'rendering_checks.json',result)
    if not result['passed']:raise RuntimeError('Map-rendering read-back check failed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('all','prepare','generate','audit','test','render'),default='all')
    parser.add_argument('--output',type=Path,default=c.OUTPUT)
    parser.add_argument('--seeds',type=int,nargs='+',default=list(c.SEEDS))
    args=parser.parse_args()
    try:
        import psutil
        proc=psutil.Process();allowed=proc.cpu_affinity();proc.cpu_affinity([allowed[0]])
    except (ImportError,AttributeError):pass
    output=output_directory(args.output)
    if args.stage in ('all','test'):
        import unittest
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(c.CODE/'tests')))
        c.write_json(output/'tests.json',dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful()))
        if not result.wasSuccessful():raise SystemExit(1)
    if args.stage in ('all','prepare'):
        from parameters import prepare
        params=prepare(output)
        print('fixed profiles',params['profiles'],flush=True)
    if args.stage in ('all','generate'):
        params=c.read_json(output/'parameters.json');generate_batch(output,args.seeds,params)
    if args.stage=='render':render_existing(output,args.seeds)
    if args.stage in ('all','generate','audit'):
        from checks import audit
        params=c.read_json(output/'parameters.json');checked=audit(output,args.seeds,params)
        print('audit passed',checked['passed'],flush=True)
        if not checked['passed']:raise RuntimeError('Bathymetry audit failed; see audit.json')
    if args.stage in ('all','prepare','generate','audit','render'):manifest(output)


if __name__=='__main__':main()
