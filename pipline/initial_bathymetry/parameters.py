"""Source-derived fixed means at the accepted 95 km classification distance."""
import csv
import numpy as np
import context as c
from roughness import fit_filter_scale
from profiles import from_parameters


def prepare(output):
    cohort=[v for v in c.read_json(c.COHORT) if abs(float(v['latitude']))<60]
    if len(cohort)!=34:raise ValueError('Expected the accepted 34-landmass reference cohort')
    offset=c.read_json(c.SEA_BATCH/'distance.json')['observation_distance_km']
    rows=[];sources=[]
    for row in cohort:
        path=c.F_STATIONS/(row['id']+'.npz')
        with np.load(path,allow_pickle=False) as z:
            col=np.flatnonzero(z['profile_distance_km']==offset)
            if len(col)!=1:raise ValueError('Reference observation distance unavailable')
            code=np.where(z['profile_water'][:,col[0]],z['profile_env'][:,col[0]],9)
            data=np.column_stack([z['W_km'],z['zb_m'],z['slope_m_per_m']])
            complete=np.isfinite(data).all(axis=1)&(data>0).all(axis=1)
            for name,codes in (('shallow',[1,3,4]),('deep',[2])):
                eligible=np.isin(code,codes);use=eligible&complete
                means=data[use].mean(axis=0) if use.any() else [None]*3
                rows.append(dict(landmass_id=row['id'],name=row['name'],environment=name,
                     eligible_stations=int(eligible.sum()),valid_stations=int(use.sum()),missing_stations=int((eligible&~complete).sum()),
                     width_mean_km=means[0],break_depth_mean_m=means[1],steep_slope_mean_m_per_m=means[2],
                     complete_20km_window_count=int((z['slope_window_available_km'][use]==20).sum()),
                     mean_valid_gradient_samples=float(z['slope_valid_samples'][use].mean()) if use.any() else None))
        sources.append(dict(path=str(path),sha256=c.file_sha256(path)))
    params=dict(version=c.VERSION,observation_distance_km=int(offset),platform_depth_m=53.,
                profiles={},roughness={},reference_population=34,
                averaging='paired valid W, zb, s within each landmass; arithmetic means within landmass, then equal weight across contributing landmasses',
                binary_groups={'shallow':[1,3,4],'deep':[2],'excluded':[0,5,9]})
    for name,bottom in (('shallow',453.),('deep',3746.)):
        used=[v for v in rows if v['environment']==name and v['valid_stations']>0]
        mean=lambda key:float(np.mean([v[key] for v in used]))
        params['profiles'][name]=dict(width_km=mean('width_mean_km'),break_depth_m=mean('break_depth_mean_m'),
              steep_slope_m_per_m=mean('steep_slope_mean_m_per_m'),bottom_depth_m=bottom,
              landmasses=len(used),valid_stations=sum(v['valid_stations'] for v in used),
              full_20km_windows=sum(v['complete_20km_window_count'] for v in used),
              slope_source='mean 2D gradient magnitude of valid slope cells within 20 km after W; used as fixed profile slope by the approved simplification')
        params['profiles'][name]['derived']=from_parameters(params,name).record()
    c.write_json(output/'reference/profile_means.json',rows);c.write_csv(output/'reference/profile_means.csv',rows)
    ids={v['id'] for v in cohort}
    with c.ROUGHNESS_TABLE.open(encoding='utf-8-sig',newline='') as stream:
        raw=list(csv.DictReader(stream))
    selected=[];white=np.random.default_rng(39185).standard_normal((768,768))
    for name,environment,target in (('shallow','shelf_continental',2.),('deep','oceanic',8.3)):
        by_id={}
        for v in raw:
            if v['reference_id'] in ids and v['quantity']=='roughness' and v['environment']==environment and v['margin']=='all' and int(v['n'])>0:
                w=int(float(v['distance_max_or_window_km']));value=float(v['median'])
                by_id.setdefault(v['reference_id'],{})[w]=value
                selected.append(dict(landmass_id=v['reference_id'],environment=name,window_km=w,
                                     median_local_std_m=value,mean_local_std_m=float(v['mean']),valid_cells=int(v['n'])))
        paired={k:v for k,v in by_id.items() if all(w in v and v[w]>0 for w in (3,5,10))}
        ratios=np.mean([[v[5]/v[3],v[10]/v[3]] for v in paired.values()],axis=0)
        fitted=fit_filter_scale(ratios,white)
        fitted.update(target_3km_local_std_m=target,reference_landmasses=len(paired),reference_ids=sorted(paired),
             distribution='zero-mean Gaussian white noise, Gaussian spatial filter, realization normalization',
             statistic='median of population standard deviations in fully homogeneous 3x3-cell windows',
             reference_aggregation='equal-landmass mean of paired 5/3 and 10/3 local-SD ratios',
             scale_transfer='shelf-derived correlation scale also used on the platform, following the approved first-pass shared roughness design')
        params['roughness'][name]=fitted
        print(f'roughness {name}: filter sigma {fitted["gaussian_filter_sigma_km"]:.3f} km',flush=True)
    c.write_json(output/'reference/roughness_windows.json',selected);c.write_csv(output/'reference/roughness_windows.csv',selected)
    for path in (c.COHORT,c.ROUGHNESS_TABLE,c.SEA_BATCH/'distance.json'):
        sources.append(dict(path=str(path),sha256=c.file_sha256(path)))
    params['surface']=dict(distance_regularization_sigma_km=1.,lateral_min_width_km=3.,
           lateral_width_rule='max(3 km, 1.875 * local profile depth difference / deep post-break slope); quintic C2 blend',
           domain_rule='compute fixed profiles on padded fields; crop to 500 km domain; no width compression or slope inflation',
           noise_coast_rule='deep noise strength gradually increases across its fixed pre-break width; no amplitude jump at the platform edge')
    params['limitations']=[
       'W and zb are observed only when a shelf-to-slope transition occurs before obstruction within 250 km; missing observations are excluded and counted.',
       'Reference width is measured from modern coastlines; mapping it to an initial submerged platform edge is the project construction.',
       'Post-break slope is a 2D gradient-magnitude mean, not the derivative of the coast-normal depth transect.',
       'Gaussian covariance fits short-scale ratios only. Measured GEBCO roughness includes source interpolation and topographic trends.',
       'In narrow bays, holes and narrow deep regions, the fixed target bottom may not be reached.'
    ]
    c.write_json(output/'reference/sources.json',sources)
    c.write_json(output/'parameters.json',params)
    return params
