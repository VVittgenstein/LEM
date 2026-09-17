import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
from wcontext import *
from geometry import *

def audit(out=OUT):
    out=Path(out);batch=load(out/'batch.json');rows=[]
    for item in batch['samples']:
        seed=item['seed'];p=out/f'seed{seed}';s=load(p/'selection.json');d=np.load(p/'window.npz');display=load(p/'display_geometry.json')
        field=CompleteField(seed);platform=Platform(seed);center=np.array(s['center_source_km']);R=np.array(s['rotation_matrix']);corners=np.array(s['corners_source_km'])
        pp,sx,sy=clipped_axis(field.axis,center,R);w=s['witness'];q=np.array(w['axis_point_local_km']);z=np.array(w['zero_point_local_km'])
        zvalue=float(field.values(world([z],center,R))[0]);margin=platform.boundary.distance(Point(z))
        coords=d['x_km'];sel=np.arange(5,500,31);X,Y=np.meshgrid(coords[sel],coords[sel]);xy=np.column_stack([X.ravel(),Y.ravel()]);values=field.values(world(xy,center,R)).reshape(len(sel),len(sel))
        error=float(abs(values-d['u_m_per_yr'][np.ix_(sel,sel)]).max())
        path_record=load(p/'entry_paths.json')[s['path_id']];start=np.array(path_record['start_center_km'])
        row={'seed':seed,'window_sides_500_km':bool(np.allclose(np.linalg.norm(np.diff(corners,axis=0),axis=1),500,rtol=0,atol=1e-8)),
          'rigid_rotation':bool(np.allclose(R.T@R,np.eye(2),atol=1e-12) and abs(np.linalg.det(R)-1)<1e-12),
          'source_window_local_corners_match':bool(np.allclose(local(corners,center,R),[[0,0],[500,0],[500,500],[0,500],[0,0]],atol=1e-8)),
          'span_x_km':sx,'span_y_km':sy,'span_gate':bool(max(sx,sy)>=150-1e-8),
          'axis_span_record_matches':bool(abs(sx-s['span_x_km'])<1e-8 and abs(sy-s['span_y_km'])<1e-8),
          'initial_window_outside':bool(not field.geometry.intersects(window_polygon(start,R))),
          'axis_point_inside_platform':bool(platform.geometry.contains(Point(q))),
          'zero_point_inside_platform':bool(platform.geometry.contains(Point(z))),
          'decay_path_inside_platform':bool(platform.geometry.covers(LineString([q,z]))),
          'true_zero_m_per_yr':zvalue,'natural_zero_gate':bool(zvalue==0),
          'margin_km':float(margin),'positive_margin':bool(margin>0),'no_fixed_margin_gate':s['design']['fixed_margin_threshold_km'] is None,
          'no_area_gate':s['design']['area_gate'] is None and s['area_used_for_selection'] is False,
          'field_shape':list(d['u_m_per_yr'].shape),'correct_grid':d['u_m_per_yr'].shape==(500,500),
          'finite_nonnegative':bool(np.isfinite(d['u_m_per_yr']).all() and (d['u_m_per_yr']>=0).all()),
          'pink_exact_intersection':bool(np.array_equal(d['pink_overlap'],d['platform_mask']&(d['u_m_per_yr']>0))),
          'base_elevation_unchanged':bool(np.array_equal(d['initial_elevation_m'],platform.data['elevation_m'])),
          'replayed_points':int(values.size),'replay_max_error_m_per_yr':error,
          'positive_pixels_on_window_edge':int(np.r_[d['support'][0],d['support'][-1],d['support'][1:-1,0],d['support'][1:-1,-1]].sum())}
        panels=display['panels'];row['ABC_same_limits']=all(panels[k]['xlim']==panels[0]['xlim'] and panels[k]['ylim']==panels[0]['ylim'] for k in (1,2))
        row['ABC_same_pixel_geometry']=all(panels[k]['axes_bbox_px']==panels[0]['axes_bbox_px'] and panels[k]['transform']==panels[0]['transform'] and panels[k]['scale_bar_px']==panels[0]['scale_bar_px'] for k in (1,2))
        row['D_500km_limits']=panels[3]['xlim']==[0.,500.] and panels[3]['ylim']==[0.,500.]
        paths=[]
        for letter in 'ABC':
            root=ET.parse(p/f'{letter}.svg').getroot();found={}
            for g in root.iter():
                if g.get('id','').startswith(f'full_aux_{seed}_'):found[g.get('id')]=[t.get('d') for t in g.iter() if t.tag.endswith('path')]
            paths.append(found)
        row['ABC_identical_auxiliary_SVG_paths']=bool(paths[0] and paths[0]==paths[1]==paths[2])
        row['all_four_PNG_sizes_match']=len({Image.open(p/f'{k}.png').size for k in 'ABCD'})==1
        row['palette_matches_parent']=display['color_edges_mm_yr']==load(field.path/'pair_geometry.json')['color_edges_mm_yr'] and display['palette_source_sha256']==sha(INPUT/'viewer_colormaps.py')
        b=load(BASE/f'seed{seed}/metadata.json');row['copied_base_sampling_diagnostics']=b['mask_diagnostics_passed']
        row['source_hashes_match']=all(sha(field.path/name)==value for name,value in s['input_hashes'].items()) and sha(BASE/f'seed{seed}/base.npz')==s['base_sha256']
        bools=[v for v in row.values() if isinstance(v,bool)];row['passed']=all(bools) and error<1e-12
        rows.append(row);print('audit ABCD',seed,row['passed'],'span',max(sx,sy),'margin',margin,'U error',error,flush=True)
    manifest=load(INPUT/'manifest.json');checks=[]
    for r in manifest['copied']:checks.append(sha(r['original'])==r['sha256'] and sha(ROOT/r['copy'])==r['sha256'])
    for r in manifest['read_only_complete_fields']:checks.append(sha(r['path'])==r['sha256'])
    result={'passed':len(rows)==8 and all(r['passed'] for r in rows) and all(checks),'samples':rows,
      'input_hashes_checked':len(checks),'inputs_unchanged':all(checks),'DS5_field_values_from_original_continuous_function':True,
      'overlap_area_is_diagnostic_only':True,'acceptance':'numerical and geometry validation; appearance and geological acceptance remain for user review'}
    save(CHECKS/'audit.json',result)
    if not result['passed']:raise RuntimeError('ABCD validation failed; see checks/audit.json')
    return result

if __name__=='__main__':audit()
