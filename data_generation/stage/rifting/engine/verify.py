"""Verify saved computations, visual contracts, source preservation and scope."""
from __future__ import annotations
import argparse,ast,json,re,struct,subprocess,hashlib
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote
import numpy as np
from PIL import Image
from .common import ROOT,save,load,sha
from .products import Run
from .elastic import sample_plane
from .common import stress_display
from .rendering import band,COLORS,fault_plot_limits

Image.MAX_IMAGE_PIXELS=None

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def png_size(path):
    with path.open('rb') as f:head=f.read(24)
    if head[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Invalid PNG header: '+str(path))
    return list(struct.unpack('>II',head[16:24]))

def verify(seed=1001,check_workspace_scope=False):
    run=Run(seed);dest=run.path/'validation';dest.mkdir(exist_ok=True);checks=[];assets=[]
    def check(name,value,detail=None):checks.append(dict(check=name,passed=bool(value),detail=detail))
    previews=['01_far.png','02_local.png','02_local_detail.png','03_total.png','04_05_window.png','06_faults.png','06_faults_3d.png','06_sections.png','07_U_displacement.png',
        'grid_far.png','grid_local.png','grid_local_detail.png','grid_total.png','grid_window.png','grid_U.png','grid_displacement.png','uniform_mask.png','uniform_overlay.png']
    full=['01_far.png','02_local.png','03_total.png','05_window.png']
    missing=[];shape_errors=[];bad_data=[];metadata_errors=[];local_errors=[];local_zero_frames=0
    for i,frame in enumerate(run.timeline['frames']):
        fid=frame['frame_id'];directory=run.path/'images'/fid;metadata=directory/'image_metadata.json'
        if not metadata.exists():missing.append(str(metadata.relative_to(run.path)))
        else:
            item=load(metadata)
            if item['time_year']!=frame['time_year'] or not item['large_images_written'] or item.get('geometry_revision')!=2:metadata_errors.append(fid)
            if item.get('local_display_revision')!=2 or item.get('local_color_limits_MPa')!=[0,run.scale['stress_local_MPa_max']]:local_errors.append(fid+' scale metadata')
        for parent,names in [('images',previews),('full_resolution',full)]:
            for name in names:
                path=run.path/parent/fid/name
                if not path.exists():missing.append(str(path.relative_to(run.path)));continue
                size=png_size(path);assets.append(dict(path=path.relative_to(run.path).as_posix(),bytes=path.stat().st_size,size=size))
                if parent=='full_resolution':
                    expected=6000 if name=='05_window.png' else int(run.length)*12
                    if size!=[expected,expected]:shape_errors.append(str(path))
        data=dict(np.load(run.path/'frames'/(fid+'.npz')))
        if not all(np.isfinite(v).all() for v in data.values()):bad_data.append(fid)
        if data['U_m_per_year'].shape!=(500,500) or data['displacement_m'].shape!=(500,500):bad_data.append(fid+' shape')
        local_path=directory/'grid_local.png'
        if local_path.exists():
            local_image=np.asarray(Image.open(local_path))
            local_magnitude=stress_display(data['local'])[0]
            if not np.any(local_magnitude):
                local_zero_frames+=1
                if not np.all(local_image==255):local_errors.append(fid+' zero field not white')
            n=int(run.length);node_y,node_x=np.unravel_index(local_magnitude.argmax(),local_magnitude.shape)
            peak=np.clip(np.rint(np.array([node_x,node_y])*(n-1)/(data['local'].shape[0]-1)).astype(int),0,n-1)
            points=np.array([[0,0],[n//2,n//2],[n-1,n-1],peak])
            magnitude,_=stress_display(sample_plane(data['local'],points[:,0]+.5,points[:,1]+.5,run.length))
            expected=COLORS[np.clip(np.floor(magnitude/max(run.scale['stress_local_MPa_max'],1e-20)*12),0,11).astype(int)].copy()
            expected[magnitude==0]=255
            if not np.array_equal(local_image[n-1-points[:,1],points[:,0]],expected):local_errors.append(fid+' positive local scale colors')
        if i in [0,len(run.timeline['frames'])//2,len(run.timeline['frames'])-1]:
            U,displacement,_=run.surface_fields(frame['elapsed_Myr'])
            check('saved_U_matches_response_'+fid,np.allclose(data['U_m_per_year'],U,rtol=3e-7,atol=1e-15))
            check('saved_displacement_matches_history_'+fid,np.allclose(data['displacement_m'],displacement,rtol=3e-7,atol=1e-10))
            global_path=directory/'grid_total.png';window_path=directory/'grid_window.png'
            if global_path.exists() and window_path.exists():
                global_image=np.asarray(Image.open(global_path));local_image=np.asarray(Image.open(window_path));x,y=map(int,run.window['origin_km']);n=int(run.length)
                check('red_window_pixels_match_global_'+fid,np.array_equal(local_image,global_image[n-y-500:n-y,x:x+500]))
    check('all_frame_images_exist',not missing,missing[:30]);check('PNG_dimensions',not shape_errors,shape_errors)
    check('frame_metadata_matches',not metadata_errors,metadata_errors);check('finite_saved_arrays',not bad_data,bad_data)
    check('local_zero_baseline_and_independent_scale',not local_errors,dict(errors=local_errors,zero_frames=local_zero_frames,limits_MPa=[0,run.scale['stress_local_MPa_max']]))
    extra=sorted(set(p.stem for p in (run.path/'frames').glob('*.npz'))-set(f['frame_id'] for f in run.timeline['frames']))
    check('no_stale_frame_arrays',not extra,extra)
    missing_pages=[]
    for kind in ['far','local','total']:
        overview_path=run.path/'nine_panels'/f'{kind}_overview.png'
        if not overview_path.exists():missing_pages.append(overview_path.name)
        else:assets.append(dict(path=overview_path.relative_to(run.path).as_posix(),bytes=overview_path.stat().st_size,size=png_size(overview_path)))
        for page in run.timeline['nine_panel_pages']:
            path=run.path/'nine_panels'/f'{kind}_{page["page"]:03d}.png'
            if not path.exists():missing_pages.append(path.name)
            else:assets.append(dict(path=path.relative_to(run.path).as_posix(),bytes=path.stat().st_size,size=png_size(path)))
    check('all_synchronous_nine_panels',not missing_pages,missing_pages)
    history_files=['all_histories']+[e['id'] for e in run.episodes]+[f['id'] for f in run.faults]
    check('all_lifecycle_figures',all((run.path/'chronology'/(name+'.png')).exists() for name in history_files))
    local_native_zero=run.path/'full_resolution'/run.timeline['frames'][0]['frame_id']/'02_local.png'
    if local_native_zero.exists():
        with Image.open(local_native_zero) as im:
            crop=im.crop((100*12,100*12,116*12,116*12));pixels=np.asarray(crop)
            crop.save(dest/'local_zero_grid_crop.png')
            check('local_native_zero_is_white_without_direction_glyphs',np.all(np.isin(pixels,[250,255])) and np.sum(pixels==255)>256*100)
    check('viewer_palette_frozen_exactly',sha(ROOT/'reporting/viewer_palette.py')==sha(ROOT.parents[2]/'viewer/lem_viewer/colormaps.py'))
    check('all_display_windows_qualify',all(row['window_qualifies'] for row in load(run.path/'frame_metrics.json')))
    # Read real pixels from a complete original, keeping cell edges and direction glyphs.
    index=len(run.timeline['frames'])//2;frame=run.timeline['frames'][index];native=run.path/'full_resolution'/frame['frame_id']/'03_total.png'
    if native.exists():
        with Image.open(native) as im:
            x,y=map(int,run.window['centre_km']);n=int(run.length);box=(12*(x-8),12*(n-y-8),12*(x+8),12*(n-y+8))
            crop=im.crop(box);crop.save(dest/'raw_grid_crop.png')
            palette=np.asarray(im.getpalette(),dtype=np.uint8).reshape(-1,3)
            check('native_palette_matches_viewer',np.array_equal(palette[:12],COLORS))
            data=dict(np.load(run.path/'frames'/(frame['frame_id']+'.npz')))
            mag,angle=run.stress_grid(data['far']+data['local'],origin=(x-8,y-8),size=16)
            pixels=np.array(crop);passed=True
            for row in range(16):
                for col in range(16):
                    cell=pixels[row*12:(row+1)*12,col*12:(col+1)*12]
                    expected=int(band(mag[15-row,col],0,run.scale['stress_MPa_max']))
                    passed &= np.sum(cell==expected)>80 and np.any((cell==251)|(cell==252))
            check('every_inspected_native_cell_has_color_and_direction',passed,dict(frame_id=frame['frame_id'],cells=256,crop_box_pixels=box))
    # The first-round sources and reviewed external code retain their original identity.
    source_errors=[]
    for record in load(ROOT/'output/checks/local_source_manifest.json')['files']:
        if digest(ROOT/record['frozen'])!=record['sha256'] or digest(Path(record['original']))!=record['sha256']:source_errors.append(record['frozen'])
    for receipt in (ROOT/'output/checks').glob('acquisition-*_receipt.json'):
        for record in load(receipt):
            if record['status']=='downloaded' and digest(ROOT/record['path'])!=record['sha256']:source_errors.append(record['path'])
    check('frozen_and_original_sources_preserved',not source_errors,source_errors)
    external_errors=[r['path'] for r in load(ROOT/'output/checks/code_review.json') if digest(ROOT.parents[2]/r['path'])!=r['sha256']]
    check('reviewed_external_code_unchanged',not external_errors,external_errors)
    outside=lambda s:sorted(line for line in s.splitlines() if 'data_generation/stage/rifting' not in line)
    baseline=load(ROOT/'output/checks/worktree_at_start.json')['status'];status=subprocess.check_output(['git','status','--short'],cwd=ROOT.parents[2],text=True)
    workspace_scope_matches=outside(status)==outside(baseline)
    if check_workspace_scope:check('outside_git_status_unchanged',workspace_scope_matches)
    syntax=[];code_manifest=[]
    for folder in ['engine','reporting','checks']:
        for path in (ROOT/folder).glob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'));syntax.append(path.name);code_manifest.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path)))
    for path in [ROOT/'reporting/gallery.html',*ROOT.glob('*.ps1'),*ROOT.glob('*.md')]:
        code_manifest.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path)))
    check('python_syntax',True,syntax)
    links=[]
    for path in ROOT.glob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if re.match(r'^[a-z]+://',target) or target.startswith('#'):continue
            if not (path.parent/unquote(target.split('#')[0])).exists():links.append([path.name,target])
    check('local_document_links',not links,links)
    for name in ['model_run.json','forcing.json','faults.json','window.json','timeline.json','stress_basis.npz','fault_history.npz','response_basis.npy','scales.json']:
        path=run.path/name;code_manifest.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=digest(path)))
    result=dict(created_utc=datetime.now(timezone.utc).isoformat(),passed=all(r['passed'] for r in checks),checks=checks,
        image_assets=len(assets),listed_image_bytes=sum(a['bytes'] for a in assets),
        workspace_scope=dict(enforced=check_workspace_scope,matches_acquisition_snapshot=workspace_scope_matches,current_outside_status=outside(status)),
        scope='Artifact consistency and saved-source identity. Mesh sensitivity and geological acceptance are reported separately.')
    save(dest/'delivery_verification.json',result);save(dest/'artifact_manifest.json',dict(code_and_core_data=code_manifest,images=assets))
    print(f"{sum(r['passed'] for r in checks)}/{len(checks)} artifact checks passed; {len(assets)} image assets listed.",flush=True)
    if not result['passed']:raise RuntimeError([r for r in checks if not r['passed']])
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=1001);ap.add_argument('--check-workspace-scope',action='store_true');args=ap.parse_args();verify(args.seed,args.check_workspace_scope)
