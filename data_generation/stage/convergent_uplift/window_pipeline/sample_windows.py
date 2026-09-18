"""Random boundary entry and weighted random placement; no area gate."""
import argparse,time
import numpy as np
from shapely.geometry import Point,MultiLineString
from wcontext import *
from geometry import *

DESIGN={'window_side_km':500.,'minimum_axis_projection_span_km':150.,
 'paths_per_block':160,'depth_proposals_per_path':24,'maximum_blocks':4,'entry_angle_half_range_deg':65.,
 'rotation_range_deg':[0.,360.],'axis_preference_weight':4.,'zero_boundary_preference_weight':1.5,'margin_preference_weight':1.5,
 'fixed_margin_threshold_km':None,'area_gate':None,
 'sampling':'uniform exterior boundary arc; uniform inward-angle perturbation; uniform window angle; stratified random distances on an outside-to-outside traversal; weighted categorical choice among qualified candidates',
 'one_side_definition':'positive-length natural zero-boundary portion inside platform, linked to a platform-interior axis point by an interior transect; exact original continuous field verifies zero',
 'span_definition':'max of X/Y coordinate ranges of all clipped line parts, in the 500 km domain frame; arc length is not used for this gate'}

def candidate(field,platform,center,R):
    pp,sx,sy=clipped_axis(field.axis,center,R)
    result={'span_x_km':sx,'span_y_km':sy}
    if max(sx,sy)<150-1e-8:return None,'span',result
    line=MultiLineString(pp);inside=line.intersection(platform.geometry)
    axis_fraction=float(inside.length/line.length)
    if inside.is_empty:return None,'no_axis_in_platform',result
    natural=local_geometry(field.boundary.intersection(window_polygon(center,R)),center,R)
    natural_inside=natural.intersection(platform.geometry)
    if natural_inside.is_empty:return None,'no_natural_zero_in_platform',result
    witness=preliminary_witness(field,platform,center,R,natural_inside)
    if witness is None:return None,'no_interior_transect',result
    zero_fraction=float(natural_inside.length/natural.length) if natural.length else 0.
    margin_score=min(1.,witness['proposal_margin_km']/platform.maximum_clearance)
    logweight=4*axis_fraction+1.5*zero_fraction+1.5*margin_score
    result.update(axis_inside_fraction=axis_fraction,natural_zero_boundary_inside_fraction=zero_fraction,
        proposal_margin_km=witness['proposal_margin_km'],log_weight=logweight)
    return {'center_source_km':center.tolist(),'rotation_matrix':R.tolist(),'axis_parts_local_km':[p.tolist() for p in pp],
            'witness_proposal':witness,**result},'eligible',result

def sample(seed,out,paths=None,field=None,platform=None,random_seed=None):
    started=time.perf_counter();field=field if field is not None else CompleteField(seed);platform=platform if platform is not None else Platform(seed)
    draw_seed=seed if random_seed is None else random_seed
    r=rng(draw_seed,10);choose=rng(draw_seed,20);audit=[];eligible=[];path_records=[];counts={};out=Path(out);out.mkdir(parents=True,exist_ok=True)
    npaths=paths or DESIGN['paths_per_block'];selected=None;rejected_exact=[]
    for block in range(DESIGN['maximum_blocks']):
        for j in range(npaths):
            b,outward,entry=field.boundary_draw(r);phi=float(r.uniform(-65,65));direction=rotation(np.radians(phi))@(-outward)
            theta=float(r.uniform(0,2*np.pi));R=rotation(theta)
            radius=250*(abs(direction@R[:,0])+abs(direction@R[:,1]))
            along=(field.vertices-b)@direction
            lo=float(along.min()-radius-2);hi=float(along.max()+radius+2)
            outside=b+lo*direction
            if field.geometry.intersects(window_polygon(outside,R)):raise RuntimeError('Initial window is not outside the complete field')
            depths=lo+(hi-lo)*(np.arange(DESIGN['depth_proposals_per_path'])+r.random(DESIGN['depth_proposals_per_path']))/DESIGN['depth_proposals_per_path']
            path_id=len(path_records);path_records.append({**entry,'path_id':path_id,'entry_direction':direction.tolist(),
               'direction_perturbation_deg':phi,'rotation_deg':float(np.degrees(theta)),'start_center_km':outside.tolist(),
               'initial_window_disjoint':True,'parameter_start_km':lo,'parameter_end_km':hi,'proposed_parameters_km':depths.tolist(),
               'depth_origin':'distance moved from a guaranteed fully external starting window'})
            for t in depths:
                center=b+t*direction;c,reason,metrics=candidate(field,platform,center,R);counts[reason]=counts.get(reason,0)+1
                row={'candidate_id':len(audit),'path_id':path_id,'center_x_km':float(center[0]),'center_y_km':float(center[1]),
                  'rotation_deg':float(np.degrees(theta)),'movement_from_outside_km':float(t-lo),'status':reason,**metrics}
                audit.append(row)
                if c is not None:
                    c.update(candidate_id=row['candidate_id'],path_id=path_id,rotation_deg=row['rotation_deg'],movement_from_outside_km=row['movement_from_outside_km'])
                    eligible.append(c)
        if eligible:
            weights=np.exp(np.array([c['log_weight'] for c in eligible])-max(c['log_weight'] for c in eligible));remaining=list(range(len(eligible)))
            while remaining:
                w=weights[remaining];index=int(choose.choice(remaining,p=w/w.sum()));c=eligible[index]
                verified=verify_witness(field,platform,np.array(c['center_source_km']),np.array(c['rotation_matrix']),c['witness_proposal'])
                if verified is not None:selected={**c,'witness':verified,'selection_probability_within_remaining':float(weights[index]/w.sum())};break
                rejected_exact.append(c['candidate_id']);remaining.remove(index)
        if selected is not None:break
    csvsave(out/'candidates.csv',audit);save(out/'entry_paths.json',path_records)
    if selected is None:
        save(out/'failure.json',{'seed':seed,'counts':counts,'exact_rejections':rejected_exact});raise RuntimeError(f'No valid placement for {seed}; see {out}')
    center=np.array(selected['center_source_km']);R=np.array(selected['rotation_matrix'])
    coords=np.arange(500)+.5;X,Y=np.meshgrid(coords,coords);points=np.column_stack([X.ravel(),Y.ravel()]);source=world(points,center,R)
    u=field.values(source).reshape(500,500);support=u>0;pink=support&platform.mask
    np.savez_compressed(out/'window.npz',x_km=coords,y_km=coords,u_m_per_yr=u,support=support,pink_overlap=pink,
       platform_mask=platform.mask,initial_elevation_m=platform.data['elevation_m'])
    corners=world(np.array([[0,0],[500,0],[500,500],[0,500],[0,0]]),center,R)
    selected.update(seed=seed,version=VERSION,design=DESIGN,corners_source_km=corners.tolist(),
       candidate_count=len(audit),eligible_count=len(eligible),candidate_status_counts=counts,exact_verification_rejections=rejected_exact,
       input_hashes={name:sha(field.path/name) for name in ('axis.json','field.npz','axis_field_parameters.json')},
       base_sha256=sha(platform.path),window_sha256=sha(out/'window.npz'),
       actual_peak_mm_yr=float(u.max()*1000),pink_area_km2=int(pink.sum()),
       overlap_area_km2=int(support.sum()),area_used_for_selection=False,elapsed_seconds=time.perf_counter()-started)
    save(out/'selection.json',selected)
    print(f"window {seed}: candidates={len(audit)} eligible={len(eligible)} span=({selected['span_x_km']:.1f},{selected['span_y_km']:.1f}) angle={selected['rotation_deg']:.1f} margin={selected['witness']['margin_km']:.1f} km time={selected['elapsed_seconds']:.1f}s",flush=True)
    return {k:selected[k] for k in ('seed','candidate_count','eligible_count','span_x_km','span_y_km','rotation_deg','axis_inside_fraction','actual_peak_mm_yr','elapsed_seconds')}

def main():
    p=argparse.ArgumentParser();p.add_argument('--seeds',nargs='+',type=int,default=list(range(1001,1009)));p.add_argument('--output',default='output');p.add_argument('--paths',type=int);a=p.parse_args()
    out=(ROOT/a.output).resolve()
    if not out.is_relative_to(ROOT):raise ValueError('Output outside module')
    out.mkdir(parents=True,exist_ok=True);records=[]
    for seed in a.seeds:
        records.append(sample(seed,out/f'seed{seed}',a.paths));save(out/'batch.json',{'version':VERSION,'samples':records,'design':DESIGN})

if __name__=='__main__':main()
