"""A trigger owns one independent belt; a world owns one fixed 500-km platform."""
import argparse, hashlib, shutil, sys, time
from tcontext import *

def spatial_seed(world_seed,event_index,attempt=0):
    return int(np.random.SeedSequence([20260918,int(world_seed),int(event_index),int(attempt),68013]).generate_state(1)[0])

def event_directory(world_seed,event_index):return OUT/f'seed{world_seed}/event{event_index:02d}'

def binding(world_seed,event_index):
    return load(event_directory(world_seed,event_index)/'binding.json')

def field_directory(world_seed,event_index):
    b=binding(world_seed,event_index)
    return (PARENT/b['field_directory']).resolve()

def window_directory(world_seed,event_index):
    return event_directory(world_seed,event_index)/'spatial/window'

def coordinate_hash(axis):
    payload=json.dumps(axis['edges'],separators=(',',':'),allow_nan=False).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()

def upstream():
    sys.path.insert(0,str(PARENT/'field_pipeline'))
    import generate_fields
    sys.path.insert(0,str(PARENT/'window_pipeline'))
    import sample_windows,geometry,render_windows
    os.environ['MPLCONFIGDIR']=str(CHECKS/'matplotlib_cache')
    return generate_fields,sample_windows,geometry,render_windows

def ensure_binding(world_seed,event,force=False):
    index=event['event_index'];directory=event_directory(world_seed,index);target=directory/'binding.json'
    if target.exists() and not force:
        b=load(target)
        # Reuse only this event's own generated instance. Historical static examples
        # outside its directory cannot serve as newly triggered events.
        if (PARENT/b['field_directory']).resolve().is_relative_to(directory.resolve()):
            for path,value in b['hashes'].items():
                if sha(PARENT/path)!=value:raise ValueError(f'Bound spatial input changed: {path}')
            b.update(version=VERSION,event_id=event['event_id'],activity_type='convergent_uplift')
            b.pop('belt_id',None);save(target,b)
            return b
    directory.mkdir(parents=True,exist_ok=True);wp=directory/'spatial/window';wp.mkdir(parents=True,exist_ok=True)
    base=PARENT/f'window_pipeline/bases/seed{world_seed}/base.npz';attempts=[]
    gen,windows,geo,_=upstream()
    ds=load(PARENT/'field_pipeline/models/DS5_model.json');gm=load(PARENT/'field_pipeline/models/G_geometry_model.json')
    platform=geo.Platform(world_seed);origin='New event: independently sampled axis, scale, reference U field and placement. No pre-existing static belt is assigned.'
    for attempt in range(32):
        draw=spatial_seed(world_seed,index,attempt);fp=directory/f'spatial/attempt{attempt:02d}/field';trial_wp=directory/f'spatial/attempt{attempt:02d}/window'
        started=time.perf_counter()
        print('new event',world_seed,index+1,'spatial_seed',draw,'attempt',attempt,flush=True)
        try:
            if not (fp/'metadata.json').exists():gen.generate_one(draw,fp,ds,gm)
            axis=load(fp/'axis.json');pts=np.vstack(axis['edges'])
            # A bounding-box diagonal below 150 makes the requested projected span impossible.
            if np.linalg.norm(np.ptp(pts,axis=0))<150:raise ValueError('Entire axis extent cannot attain a 150 km projection in any window orientation')
            if not load(fp/'metadata.json')['validation']['width_relative_tolerance_pass']:raise ValueError('Full-field width calibration outside the existing tolerance')
            field=geo.CompleteField(draw,path=fp)
            if not (trial_wp/'selection.json').exists():windows.sample(world_seed,trial_wp,field=field,platform=platform,random_seed=draw)
            for name in ('window.npz','selection.json','entry_paths.json','candidates.csv'):
                shutil.copyfile(trial_wp/name,wp/name)
            attempts.append(dict(attempt=attempt,spatial_seed=draw,status='accepted',seconds=time.perf_counter()-started))
            break
        except (RuntimeError,ValueError) as exc:
            attempts.append(dict(attempt=attempt,spatial_seed=draw,status='rejected_geometry_or_placement',reason=str(exc),seconds=time.perf_counter()-started))
            save(directory/'spatial_attempts.json',attempts)
    else:raise RuntimeError(f'No admissible spatial belt for world {world_seed}, event {index}')
    axis=load(fp/'axis.json');selection=load(wp/'selection.json');meta=load(fp/'metadata.json')
    assert selection['base_sha256']==sha(base)
    hashes={}
    for p in [fp/n for n in ('axis.json','field.npz','axis_field_parameters.json','metadata.json')]+[wp/n for n in ('window.npz','selection.json')]+[base]:
        hashes[p.relative_to(PARENT).as_posix()]=sha(p)
    b=dict(version=VERSION,world_seed=world_seed,event_index=index,event_id=event['event_id'],activity_type='convergent_uplift',spatial_seed=draw,
        field_directory=fp.relative_to(PARENT).as_posix(),window_directory=wp.relative_to(PARENT).as_posix(),
        platform_path=base.relative_to(PARENT).as_posix(),base_seed=world_seed,origin=origin,
        axis_coordinates_sha256=coordinate_hash(axis),axis_extent_km=meta['axis_extent_km'],reference_peak_mm_yr=meta['peak_mm_yr'],
        placement_rotation_deg=selection['rotation_deg'],attempts=attempts,hashes=hashes,
        temporal_rule='Original trigger and lifecycle retained; no resampling of time after spatial rejection.',
        spatial_rule='One unique belt per event. Geometric/placement rejection follows the existing 150-km and natural-zero-side requirements; no morphology quotas.')
    save(target,b);save(directory/'spatial_attempts.json',attempts)
    return b

def render_spatial(world_seed,index,color_edges):
    _,_,_,renderer=upstream();b=binding(world_seed,index)
    renderer.draw_sample(window_directory(world_seed,index),field_directory(world_seed,index),color_edges=color_edges,
                         label=f'样本 {world_seed} · 事件 {index+1}')

def main():
    p=argparse.ArgumentParser();p.add_argument('--seeds',nargs='+',type=int,default=list(range(1001,1009)));args=p.parse_args()
    from timing import simulate
    init();records=[]
    for seed in args.seeds:
        for event in simulate(seed)['events']:
            records.append(ensure_binding(seed,event));save(OUT/'event_instances.json',records)
    if len({r['axis_coordinates_sha256'] for r in records})!=len(records):raise AssertionError('Repeated belt geometry across triggers')
    csvsave(OUT/'event_instances.csv',[{k:r[k] for k in ('world_seed','event_index','event_id','spatial_seed','axis_extent_km','reference_peak_mm_yr','placement_rotation_deg','axis_coordinates_sha256')} for r in records])
    print('independent event instances',len(records),flush=True)

if __name__=='__main__':main()
