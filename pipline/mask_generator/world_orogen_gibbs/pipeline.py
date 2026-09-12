from dataclasses import replace
from pathlib import Path
import time
import numpy as np
from common.io import write_json,read_json,file_sha256
from .config import OUTPUT
from .geometry import generate_partitions,geometry
from .fields import generate_fields
from .sampler import run_sampler
from .model import terms
from .diagnostics import diagnose,spatial_diagnose


def prepare(directory,seed,settings):
    settings.validate()
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    identity=dict(geometry={k:settings.describe()[k] for k in ('size','cell_km','band','partition_count','coarse_side','point_jitter','warp_multiplier')},
                  fields=dict(sigmas=list(settings.field_sigmas_km),weights=list(settings.field_weights)),seed=seed,
                  selection_domain=dict(boundary_layers=settings.boundary_layers))
    identity_file=directory/'input_identity.json'
    if identity_file.exists():
        cached=read_json(identity_file)
        cached.setdefault('selection_domain',dict(boundary_layers=1))
        if cached!=identity:raise ValueError('cached input settings differ; use another output directory')
    labels_file=directory/'partitions.npy'
    if labels_file.is_file():
        labels=np.load(labels_file);xy=np.load(directory/'seeds.npy')
        record=read_json(directory/'partition_generation.json')
    else:
        labels,xy,record,projection=generate_partitions(seed,settings)
        np.save(labels_file,labels);np.save(directory/'seeds.npy',xy)
        write_json(directory/'partition_generation.json',record)
        np.savez_compressed(directory/'projection.npz',**projection)
    file=directory/'fields.npz'
    if file.is_file():
        with np.load(file) as data: fields,combined,average=(data[k] for k in ('fields','combined','average'))
    else:
        fields,combined,average=generate_fields(seed,settings,labels)
        np.savez_compressed(file,fields=fields,combined=combined,average=average)
    write_json(identity_file,identity)
    g=geometry(labels,settings.boundary_layers)
    if g.forbidden.all():raise ValueError(f'boundary_layers={settings.boundary_layers} excludes all partitions; maximum graph layer is {g.region_layer.max()}')
    return g,xy,fields,combined,average


def sample_job(directory,seed,settings,burn=2048,draws=1024,thin=4,chains=4,temperatures=(1.,1.4,2.,2.8,4.,5.6,8.)):
    start=time.perf_counter();directory=Path(directory)
    g,xy,fields,combined,average=prepare(directory,seed,settings)
    result=run_sampler(directory,g,average,settings,seed+810000,burn,draws,thin,chains,temperatures)
    z=result['states'][0,-1];mask=z[g.labels-1]
    np.save(directory/'mask.npy',mask)
    from world_orogen.render import mask_image
    mask_image(mask).save(directory/'mask.png')
    energy=terms(z,g,average,settings)
    diagnostics=diagnose(result['statistics']);diagnostics['spatial']=spatial_diagnose(result['states'],g.forbidden)
    diagnostics['all_passed']=diagnostics['passed'] and diagnostics['spatial']['passed']
    write_json(directory/'diagnostics.json',diagnostics)
    history=result['histories'][0]
    np.savez_compressed(directory/'history.npz',sweeps=np.asarray([h[0] for h in history]),
                        states=np.asarray([h[1] for h in history]),statistics=np.asarray([h[2] for h in history]))
    write_json(directory/'last_sweep.json',result['traces'][0])
    write_json(directory/'config.json',dict(settings.describe(),seed=seed))
    write_json(directory/'energy.json',energy)
    rhats=[r['rhat'] for r in diagnostics['checks']]
    info=dict(seed=seed,partition_count=settings.partition_count,directory=str(directory),
        boundary_layers=settings.boundary_layers,
        fraction=float(mask.mean()),available_fraction=float(g.areas[~g.forbidden].sum()),
        forbidden_count=int(g.forbidden.sum()),selected_count=int(z.sum()),
        center_selected=bool(z[g.center_id]),wall_s=time.perf_counter()-start,
        max_rhat=max(rhats) if all(r is not None for r in rhats) else None,
        min_ess=min(r['bulk_ess'] for r in diagnostics['checks']),
        failed_metrics=[r['metric'] for r in diagnostics['checks'] if not r['passes']],
        spatial_failed_count=len(diagnostics['spatial']['failed_region_ids']),
        components=int(result['statistics'][0,-1,7]),largest_fraction=float(result['statistics'][0,-1,8]),
        second_fraction=float(result['statistics'][0,-1,9]))
    write_json(directory/'run_summary.json',info)
    return info
