"""Read back every temporal artifact and verify spatial/time/display invariants."""
import csv, math, time
from PIL import Image
from spacetime import *
from timing import frame_times,simulate,envelope
from spatial_binding import binding,field_directory,window_directory,coordinate_hash,upstream

def audit_event(record):
    seed=record['seed'];index=record['event_index'];p=OUT/f'seed{seed}/event{index:02d}'
    event=load(p/'event.json');frames=load(p/'frames.json');summary=load(p/'summary.json');params=load(p/'spatial_time_parameters.json')
    clocks=dict(np.load(p/'clocks.npz'));native=dict(np.load(p/'native_frames.npz'));crop=dict(np.load(p/'window_frames.npz'));geo=load(p/'E_geometry.json')
    bound=binding(seed,index);full=dict(np.load(field_directory(seed,index)/'field.npz'));wp=window_directory(seed,index)
    old_crop=np.load(wp/'window.npz');sel=load(wp/'selection.json');old_geo=load(wp/'display_geometry.json')
    assert event['event_id']==bound['event_id'] and event['spatial_seed']==bound['spatial_seed']
    assert event['spatial']==bound
    assert field_directory(seed,index).is_relative_to(p.resolve())
    assert frames==frame_times(event)
    assert all(f['sim_Myr']<=48 for f in frames)
    assert len({round(f['sim_Myr'],9) for f in frames})==len(frames)
    assert abs(event['duration_Myr']-event['rise_Myr']-event['hold_Myr']-event['fall_Myr'])<1e-10
    assert bool(event['hold_Myr'])==event['hold_present']
    if event['natural_end_sim_Myr']>48:
        assert frames[-1]['modern'] and frames[-1]['sim_Myr']==48
    else:assert abs(frames[-1]['sim_Myr']-event['natural_end_sim_Myr'])<1e-10
    assert native['u_m_per_yr'].shape==(len(frames),)+full['support'].shape
    assert crop['u_m_per_yr'].shape==(len(frames),500,500)
    assert np.all(native['u_m_per_yr'][0]==0) and np.all(crop['u_m_per_yr'][0]==0)
    if event['natural_end_sim_Myr']<=48:assert np.all(native['u_m_per_yr'][-1]==0)
    assert np.isfinite(native['u_m_per_yr']).all() and np.min(native['u_m_per_yr'])>=0
    assert np.isfinite(crop['u_m_per_yr']).all() and np.min(crop['u_m_per_yr'])>=0
    assert np.all(native['u_m_per_yr'][:,~full['support']]==0)
    assert np.all(crop['u_m_per_yr'][:,old_crop['u_m_per_yr']==0]==0)
    ids=rng(seed,800+index).choice(full['support'].size,min(1200,full['support'].size),replace=False)
    yy,xx=np.unravel_index(ids,full['support'].shape);points=np.column_stack([full['x_km'][xx],full['y_km'][yy]])
    ev=Evaluator(points,full['u_m_per_yr'].ravel()[ids],clocks['onset'].ravel()[ids],clocks['retreat'].ravel()[ids],event,params['noise'],False)
    native_error=max(float(np.max(np.abs(ev.rate(f['sim_Myr'])-native['u_m_per_yr'][i].ravel()[ids]))) for i,f in enumerate(frames))
    assert native_error<1e-8
    cp=crop_points(sel);ii=rng(seed,810+index).choice(250000,1200,replace=False);on,off=clock_values(cp[ii],full,clocks)
    ce=Evaluator(cp[ii],old_crop['u_m_per_yr'].ravel()[ii],on,off,event,params['noise'],False)
    crop_error=max(float(np.max(np.abs(ce.rate(f['sim_Myr'])-crop['u_m_per_yr'][i].ravel()[ii]))) for i,f in enumerate(frames))
    assert crop_error<1e-8
    panels=geo['panels'];sizes=np.array([g['bbox_px'][2:] for g in panels]);assert np.ptp(sizes,axis=0).max()<1e-6
    for g in panels:
        assert g['xlim']==old_geo['common_extent_km'][:2] and g['ylim']==old_geo['common_extent_km'][2:]
        assert g['scale_bar_km']==old_geo['panels'][1]['scale_bar_km']
        assert abs(g['transform'][0][0]-g['transform'][1][1])<1e-10
    assert geo['color_edges_mm_yr']==old_geo['color_edges_mm_yr']
    with Image.open(p/'E.png') as img:assert list(img.size)==geo['canvas_px']
    assert native['u_m_per_yr'].max()*1000<=max(geo['color_edges_mm_yr'])+1e-5
    timeline=geo['timeline'];assert timeline['geological_interval']==[0.,48.]
    assert timeline['activity_interval']==[event['start_sim_Myr'],event['natural_end_sim_Myr']]
    assert timeline['point_times']==[f['sim_Myr'] for f in frames]
    sx=timeline['time_to_pixel'][0][0]
    ratio=((event['natural_end_sim_Myr']-event['start_sim_Myr'])*sx)/(48*sx)
    assert abs(ratio-event['duration_Myr']/48)<1e-12
    probes=np.load(p/'probes.npz');small=Evaluator(probes['points_km'][:48],probes['reference_u_m_yr'][:48],probes['onset'][:48],probes['retreat'][:48],event,params['noise'])
    lo=event['start_sim_Myr'];hi=event['executed_until_sim_Myr'];base=small.displacement(lo,hi,.1);fine=small.displacement(lo,hi,.05)
    integral_error=float(np.max(np.abs(base-fine)));assert integral_error<.1
    expected=probes['cumulative_m'][:48];assert np.max(np.abs(expected-fine))<.1
    sigma=params['noise']['sigma_log'];noise=params['noise'];rot=np.array(noise['rotation']);omega=np.array(noise['omega_xy']);wt=np.array(noise['omega_t'])
    ell=[load(MODELS/'design.json')['fluctuation_along_correlation_km'],load(MODELS/'design.json')['fluctuation_across_correlation_km']]
    covs=dict(along_1ell=float(np.cos(omega@(ell[0]*rot[0])).mean()),across_1ell=float(np.cos(omega@(ell[1]*rot[1])).mean()),time_1ell=float(np.cos(wt).mean()),
              squared_exponential_target_1ell=float(np.exp(-.5)))
    return dict(seed=seed,event_index=index,event_id=bound['event_id'],spatial_seed=bound['spatial_seed'],passed=True,frames=len(frames),native_replay_max_error_m_yr=native_error,
        window_replay_max_error_m_yr=crop_error,quadrature_halving_max_error_m=integral_error,
        natural_lifetime_Myr=event['duration_Myr'],ongoing_at_modern=event['ongoing_at_modern'],
        spectral_correlation_diagnostics=covs,realized_multiplier_cv=summary['actual_noise_multiplier_cv'],
        local_change_diagnostics=summary['local_change_diagnostics'])

def main():
    batch=load(OUT/'batch.json');records=[audit_event(e) for e in batch['events']]
    sources=load(SOURCES/'manifest.json')
    for r in sources['copied']:assert sha(SOURCES/r['copy'])==r['sha256']
    for r in sources['spatial_inputs']:assert sha(PARENT/r['path'])==r['sha256']
    saved=load(OUT/'schedules.json')
    for s in saved:
        replay=simulate(s['seed'],s['dt_Myr']);assert replay==s
    before=CHECKS/'before_independent_belts/schedules.json'
    if before.exists():
        previous=load(before);assert len(saved)==len(previous)
        for old,new in zip(previous,saved):
            assert {k:v for k,v in old.items() if k!='events'}=={k:v for k,v in new.items() if k!='events'}
            assert len(old['events'])==len(new['events'])
            for a,b in zip(old['events'],new['events']):assert a=={k:b[k] for k in a},'Event creation changed the original trigger/lifecycle draw'
    assert len(records)==sum(len(s['events']) for s in saved)
    # Every event appears, irrespective of where its natural end falls.
    assert {(r['seed'],r['event_index']) for r in records}=={(s['seed'],e['event_index']) for s in saved for e in s['events']}
    belt_records=audit_belts(saved)
    print('audited',len(records),'complete independent events;',len(belt_records),'unique spatial instances; all historical spatial hashes intact',flush=True)
    save(CHECKS/'audit.json',dict(passed=True,events=records,spatial_inputs_checked=len(sources['spatial_inputs']),
         all_triggers_delivered=True,independent_events=len(belt_records),all_spatial_instances_owned_by_events=True,timing_unchanged=True,source_hashes_passed=True,scope='Numerical, reproduction, independent event ownership, coordinate, lifecycle and display contracts; geological validation remains separate.'))
    csvsave(CHECKS/'correlation_diagnostics.csv',[dict(seed=r['seed'],event_index=r['event_index'],**r['spectral_correlation_diagnostics']) for r in records])

def audit_belts(schedules):
    _,_,geo,_=upstream();from shapely.geometry import Point,LineString
    records=[];seen=set();platforms={}
    for schedule in schedules:
        world=schedule['seed'];platform=platforms.setdefault(world,geo.Platform(world))
        for e in schedule['events']:
            b=binding(world,e['event_index']);fp=field_directory(world,e['event_index']);wp=window_directory(world,e['event_index'])
            for path,value in b['hashes'].items():assert sha(PARENT/path)==value
            assert fp.is_relative_to((OUT/f'seed{world}/event{e["event_index"]:02d}').resolve())
            assert b['event_id']==e['event_id']
            axis=load(fp/'axis.json');h=coordinate_hash(axis);assert h==b['axis_coordinates_sha256'] and h not in seen;seen.add(h)
            field=geo.CompleteField(b['spatial_seed'],path=fp);selection=load(wp/'selection.json');crop=np.load(wp/'window.npz')
            assert field.meta['validation']['width_relative_tolerance_pass']
            assert np.array_equal(crop['platform_mask'],platform.mask)
            assert np.array_equal(crop['initial_elevation_m'],platform.data['elevation_m'])
            center=np.array(selection['center_source_km']);R=np.array(selection['rotation_matrix']);np.testing.assert_allclose(R.T@R,np.eye(2),atol=1e-12)
            _,sx,sy=geo.clipped_axis(field.axis,center,R);assert max(sx,sy)>=150-1e-8
            w=selection['witness'];q=np.array(w['axis_point_local_km']);z=np.array(w['zero_point_local_km'])
            assert platform.geometry.contains(Point(q)) and platform.geometry.contains(Point(z)) and platform.geometry.covers(LineString([q,z]))
            values=field.values(geo.world(np.vstack([q,z]),center,R));assert values[0]>0 and values[1]==0
            ids=rng(world,901+e['event_index']).choice(250000,512,replace=False)
            points=crop_points(selection)[ids];error=float(np.max(np.abs(field.values(points)-crop['u_m_per_yr'].ravel()[ids])));assert error<1e-11
            assert not selection['area_used_for_selection']
            records.append(dict(world_seed=world,event_index=e['event_index'],event_id=b['event_id'],spatial_seed=b['spatial_seed'],
                axis_coordinates_sha256=h,axis_extent_km=b['axis_extent_km'],projection_span_x_km=sx,projection_span_y_km=sy,
                zero_side_margin_km=w['margin_km'],window_replay_error_m_yr=error,platform_unchanged=True))
    save(CHECKS/'independent_events.json',dict(passed=True,events=records,unique_axis_coordinate_hashes=len(seen),
         definition='Hash covers actual axis coordinates only, excluding IDs and metadata; every event has a distinct geometry.'))
    return records

if __name__=='__main__':main()
