"""Read-back, geometry, roughness and reproducibility checks of the initial surface."""
import numpy as np
from scipy.ndimage import binary_erosion,map_coordinates
import context as c
from profiles import from_parameters
from roughness import local_std


def summarize(values):
    values=np.asarray(values);values=values[np.isfinite(values)]
    if not len(values):return dict(n=0,min=None,mean=None,median=None,p95=None,max=None)
    return dict(n=len(values),min=float(values.min()),mean=float(values.mean()),median=float(np.median(values)),
                p95=float(np.percentile(values,95)),max=float(values.max()))


def metrics(sample,arrays,params,normalization):
    z=arrays['elevation'];base=arrays['base_elevation'];typ=sample['sea_type'];q=arrays['noise_deep_weight']
    sd=local_std(arrays['roughness']);gy,gx=np.gradient(base,1000.);gradient=np.hypot(gx,gy)
    row=dict(seed=sample['seed'],elevation_m=summarize(z),base_gradient_m_per_m=summarize(gradient),
          initial_submerged=bool((z<0).all()),platform_base_exact=bool((base[sample['mask']]==-53.).all()),
          noise_normalization=normalization,roughness={},space={},fusion={})
    row['distance_regularization_error_km']=summarize(abs(arrays['distance_km']-arrays['raw_distance_km'])[~sample['mask']])
    for code,name in ((0,'platform'),(1,'shallow'),(2,'deep')):
        cells=typ==code;interior=binary_erosion(cells,structure=np.ones((3,3)),border_value=0)
        row['roughness'][name]=dict(all_homogeneous_windows=summarize(sd[interior]),
                    target_3km_std_m=8.3 if code==2 else 2.,
                    interpretation='residual after subtracting the deterministic base profile; boundary/amplitude transition windows included here')
        if code==2:pure=binary_erosion(q>=.995,structure=np.ones((3,3)),border_value=0)
        else:pure=interior&(q<=.005)
        row['roughness'][name]['pure_interior_windows']=summarize(sd[pure])
        if code:
            p=from_parameters(params,name)
            has=(arrays['distance_km']>=p.foot_km)&cells
            row['space'][name]=dict(assigned_cells=int(cells.sum()),fixed_profile_foot_km=p.foot_km,
                cells_before_target_foot=int((cells&~has).sum()),cells_reaching_profile_foot=int(has.sum()),
                fraction_before_target_foot=float((cells&~has).sum()/cells.sum()) if cells.any() else None,
                actual_base_depth_m=summarize(-base[cells]))
    seam_h=(typ[:,1:]!=typ[:,:-1])&(typ[:,1:]>0)&(typ[:,:-1]>0)
    seam_v=(typ[1:]!=typ[:-1])&(typ[1:]>0)&(typ[:-1]>0)
    hard=np.where(typ==2,arrays['deep_profile'],arrays['shallow_profile'])
    before=np.r_[np.abs(np.diff(hard,axis=1))[seam_h],np.abs(np.diff(hard,axis=0))[seam_v]]
    after=np.r_[np.abs(np.diff(base,axis=1))[seam_h],np.abs(np.diff(base,axis=0))[seam_v]]
    row['fusion']=dict(shared_grid_edges=len(after),before_blending_step_m=summarize(before),
               after_blending_step_m=summarize(after),
               meaning='differences across adjacent 1 km cells; nonzero values also include legitimate slope')
    return row


def audit(output,seeds,params,replay=True):
    from surface import generate
    rows=[]
    for seed in seeds:
        sample=c.load_input(seed);folder=output/f'seed{seed}'
        arrays={p.stem:np.load(p,allow_pickle=False) for p in folder.glob('*.npy')}
        config=c.read_json(folder/'config.json');stat=c.read_json(folder/'metrics.json')
        z=arrays['elevation'];base=arrays['base_elevation']
        checks=dict(shape=z.shape==(500,500),dtype=z.dtype==np.float64,finite=bool(np.isfinite(z).all()),
              entirely_submerged=bool((z<0).all()),platform_base_53=bool((base[sample['mask']]==-53.).all()),
              components_add=bool(np.allclose(z,base+arrays['roughness'],atol=1e-10,rtol=0)),
              labels_unchanged=np.array_equal(sample['sea_type'],sample['region_types'][sample['labels']-1]),
              inputs_unchanged=c.check_hashes(config['input_files']),
              fixed_parameters=config['parameters_sha256']==c.file_sha256(output/'parameters.json'))
        # The contour geometry independently reads back against saved elevations.
        data=c.read_json(folder/'contour_lines.json');errors=[];points=0
        for line in data['contours']:
            for coordinates in line['lines']:
                xy=np.asarray(coordinates,float)
                if not len(xy):continue
                observed=map_coordinates(z,[xy[:,1]-.5,xy[:,0]-.5],order=1,mode='nearest')
                errors.extend(abs(observed-line['elevation_m']));points+=len(xy)
        maximum=float(max(errors,default=0.))
        checks['contours_match_saved_elevation']=maximum<1e-6 and points>0
        checks['all_figures_present']=all((folder/name).is_file() for name in ('contours.png','profiles.png','roughness.png'))
        checks['platform_roughness']=abs(stat['roughness']['platform']['pure_interior_windows']['median']/2.-1)<.12
        checks['shallow_roughness']=abs(stat['roughness']['shallow']['pure_interior_windows']['median']/2.-1)<.12
        deep=stat['roughness']['deep']['pure_interior_windows']
        checks['deep_roughness']=(not (sample['sea_type']==2).any()) or (deep['n']>=25 and abs(deep['median']/8.3-1)<.12)
        reproduced={}
        if replay:
            again,_=generate(sample,params)
            reproduced={name:np.array_equal(arrays[name],value) for name,value in again.items()}
            checks['reproducible']=all(reproduced.values())
        rows.append(dict(seed=seed,checks=checks,passed=bool(all(checks.values())),
                       contour_vertex_count=points,contour_max_error_m=maximum,reproduced_arrays=reproduced))
    sources=c.read_json(output/'reference/sources.json')
    result=dict(samples=len(rows),rows=rows,sources_unchanged=c.check_hashes(sources),
                passed=bool(all(row['passed'] for row in rows) and c.check_hashes(sources)),
                interpretation='engineering and data consistency checks, not a completed LEM or geological validation',
                roughness_tolerance='12 percent on median homogeneous-interior 3 km local SD; actual values always reported')
    c.write_json(output/'audit.json',result)
    return result
