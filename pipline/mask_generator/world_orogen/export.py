"""World Orogen outputs use whole-region soft budgets and exact raster contours."""
from pathlib import Path
import numpy as np
from PIL import Image

from common.config import ROOT
from common.contours import extract_contours,rasterize_contours
from common.io import array_sha256,file_sha256,read_json,utc_now,write_json,write_csv
from common.metrics import full_metrics
from .config import UPSTREAM_COMMIT,run_settings
from .render import decode_mask,render_sample
from .selection import generate_mask


def boundary_capacity(labels,band=10):
    ids=np.unique(np.concatenate([labels[band,band:-band],labels[-band-1,band:-band],
                                  labels[band:-band,band],labels[band:-band,-band-1]]))
    ids=ids[ids>0]
    areas=np.bincount(labels.ravel())
    interior=np.setdiff1d(np.arange(1,len(areas)),ids)
    return {'boundary_region_ids':ids.tolist(),
            'interior_only_available_fraction':float(areas[interior].sum()/labels.size)}


def export_sample(partitions,result,directory:Path):
    directory.mkdir(parents=True,exist_ok=True)
    np.save(directory/"mask.npy",result.mask,allow_pickle=False)
    np.save(directory/"partitions.npy",partitions.labels,allow_pickle=False)
    np.savez_compressed(directory/"coarse_partitions.npz",points_normalized=partitions.coarse_points,
                        labels_zero_based=partitions.coarse_labels)
    np.savez_compressed(directory/"projection.npz",dx_km=partitions.warp_x_km,dy_km=partitions.warp_y_km)
    write_json(directory/"partition_generation.json",partitions.record)
    geometry=result.geometry
    write_json(directory/"regions.json",{"ids":list(range(1,geometry.count+1)),"areas_km2":geometry.areas,
        "centers_xy_km":geometry.centers_xy,"second_moments_about_preferred_center_km4":geometry.second_moments,
        "adjacency_ids":[[j+1 for j in neighbors] for neighbors in geometry.adjacency]})
    write_json(directory/"selection.json",{"initial_region":result.order[0],"order":result.order,
        "stopping":"first complete region addition reaching the soft area target","steps":result.trace})
    contours=extract_contours(result.mask)
    write_json(directory/"contours.json",contours)
    metrics={**full_metrics(result.mask),**result.statistics,**boundary_capacity(partitions.labels)}
    metrics['target_fraction']=result.target_fraction
    metrics['fraction_outside_preference']=not .5 <= float(result.mask.mean()) <= .6
    write_json(directory/"metrics.json",metrics)
    views=render_sample(partitions,result,directory)
    config={"created_utc":utc_now(),"seed":partitions.seed,**partitions.settings.describe(),
        "target_fraction":result.target_fraction,"selected_regions":result.order,
        "selection_rule":"softmax(connection_weight * delta_Q - center_weight * delta_R)",
        "random_streams":{"mesh_points":"Park-Miller(seed+137)","partition_growth":"Park-Miller(seed+0.5)",
             "partition_indices":"Park-Miller(seed)","projection":"Simplex(seed+999)",
             "area":"PCG64(SeedSequence([seed,11]))","selection":"PCG64(SeedSequence([seed,303]))"},
        "mask_array_sha256":array_sha256(result.mask),"partition_array_sha256":array_sha256(partitions.labels),
        "coordinates":"NPY row 0 is bottom; x=column+0.5 km, y=row+0.5 km; PNG rows reversed",
        "views":views,"post_selection_pixel_edits":False,
        "reference_usage":"34 landmasses provide diagnostic comparison only; no parameter fitting in this experiment",
        "upstream_source_url":f"https://github.com/raguilar011095/planet_heightmap_generation/tree/{UPSTREAM_COMMIT}"}
    write_json(directory/"config.json",config)
    band=partitions.settings.band
    allowed=np.zeros((500,500),bool);allowed[band:-band,band:-band]=True
    replay=generate_mask(partitions,result.target_fraction)
    lut=np.zeros(partitions.settings.partition_count+1,bool);lut[result.order]=True
    layout=views['four_stage_layout']
    with Image.open(directory/"four_stages.png") as overview:
        x=layout['margin']+500+layout['gap']
        y=layout['header']+layout['row_height']+layout['tile_y_offset']
        with Image.open(directory/"mask.png") as primary:
            exact_tile=np.array_equal(np.asarray(overview.crop((x,y,x+500,y+500))),np.asarray(primary))
    checks={"shape_dtype":result.mask.shape==(500,500) and result.mask.dtype==np.bool_,
        "ocean_band_empty":not result.mask[~allowed].any(),
        "partitions_cover_allowed_domain":np.array_equal(partitions.labels>0,allowed),
        "whole_partition_union":np.array_equal(lut[partitions.labels],result.mask),
        "target_reached":metrics['area_km2']>=metrics['target_area_km2']-1e-8,
        "previous_step_below_target":metrics['area_before_last_region_km2']<metrics['target_area_km2'],
        "png_roundtrip":np.array_equal(decode_mask(directory/"mask.png"),result.mask),
        "contour_area":contours['area_km2']==int(result.mask.sum()),
        "contour_valid":contours['valid'],
        "contour_roundtrip":np.array_equal(rasterize_contours(contours),result.mask),
        "graph_matches_raster_components":metrics['components_4']==metrics['region_component_count'],
        "graph_matches_raster_largest_area":abs(metrics['largest_component_fraction']-metrics['largest_component_fraction_graph'])<1e-12,
        "selection_replay":np.array_equal(replay.mask,result.mask) and replay.order==result.order,
        "four_stage_mask_tile_exact":exact_tile,
        "all_step_frames_exist":all((directory/"steps"/f"{i:03d}.png").is_file() for i in range(len(result.order)))}
    longest=max(metrics['longest_straight_band_contact_km'].values())
    observations=[]
    if longest>=25: observations.append(f"海洋带内缘最长连续接触 {longest} km。")
    if metrics['fraction_outside_preference']: observations.append("整分区加入后，实际占比超出50%至60%偏好范围，结果保留。")
    status={"execution":"complete" if all(checks.values()) else "failed_checks","checks":checks,
        "observations":observations,"visual_review":{"state":"pending","user_acceptance":"pending"},
        "parameter_status":"engineering experiment; no preset frequency quotas for output forms"}
    write_json(directory/"status.json",status)
    if not all(checks.values()): raise RuntimeError(f"sample verification failed: {directory}: {checks}")
    return {"seed":partitions.seed,"partition_count":partitions.settings.partition_count,
        "relative_path":f"partitions_{partitions.settings.partition_count}/seed{partitions.seed}",
        "metrics":metrics,"config":config,"status":status}


def read_samples(output,counts,seeds):
    samples=[]
    for count in counts:
        for seed in seeds:
            relative=f"partitions_{count}/seed{seed}"
            samples.append({"seed":seed,"partition_count":count,"relative_path":relative,
                **{k:read_json(output/relative/f"{k}.json") for k in ('metrics','config','status')}})
    return samples


def write_summary(output,samples):
    columns=['fraction','target_fraction','area_km2','selected_region_count','components_4','largest_component_fraction',
             'centroid_offset_km','rms_distance_to_preferred_center_km','Q','R','axis_ratio','shoreline_development','closed_water_cells']
    rows=[{'seed':s['seed'],'partition_count':s['partition_count'],**{k:s['metrics'][k] for k in columns},
           'longest_band_contact_km':max(s['metrics']['longest_straight_band_contact_km'].values()),
           'soft_budget_outside_preference':s['metrics']['fraction_outside_preference']} for s in samples]
    write_csv(output/'samples.csv',rows)
    return rows


def manifest(output,settings,counts,seeds):
    import importlib.metadata
    import sys
    code_root=Path(__file__).resolve().parents[1]
    sources=ROOT/f"references/2026-09-10-platform-shape-methods/world-orogen/{UPSTREAM_COMMIT}"
    upstream_files=['js/plates.js','js/coarse-plates.js','js/rng.js','js/simplex-noise.js','js/terrain-config.js','LICENSE']
    files=[p for p in output.rglob('*') if p.is_file() and p.relative_to(output).as_posix() not in ('manifest.json','run_status.json')
           and 'cache' not in p.relative_to(output).parts]
    codes=[p for p in code_root.rglob('*') if p.is_file() and (p.suffix in ('.py','.ps1','.md') or p.name=='LICENSE')]
    write_json(output/'manifest.json',{'created_utc':utc_now(),'settings':run_settings(settings,counts),'partition_counts':list(counts),
        'display_seeds':list(seeds),'interpreter':sys.executable,
        'libraries':{k:importlib.metadata.version(k) for k in ('numpy','scipy','shapely','Pillow')},
        'upstream_commit':UPSTREAM_COMMIT,
        'upstream_files':[{'path':str(sources/p),'sha256':file_sha256(sources/p)} for p in upstream_files],
        'code_files':[{'path':str(p),'sha256':file_sha256(p)} for p in sorted(codes)],
        'output_files':[{'path':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':file_sha256(p)} for p in sorted(files)]})
