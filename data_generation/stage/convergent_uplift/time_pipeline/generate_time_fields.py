"""Apply each actual trigger to its own belt within a fixed world domain."""
import argparse, time, gc
from spacetime import *
from timing import simulate, frame_times
from spatial_binding import ensure_binding,field_directory,window_directory

def generate_event(seed,event,full,axis,selection,crop,design):
    tic=time.perf_counter();index=event['event_index'];directory=OUT/f'seed{seed}/event{index:02d}'
    directory.mkdir(parents=True,exist_ok=True)
    bound=load(directory/'binding.json');event={**event,'spatial_seed':bound['spatial_seed'],'spatial':bound,
       'evolution':{'clocks':'clocks.npz','continuous_random_function':'spatial_time_parameters.json','time_origin':'simulation zero = 48 Ma'}}
    clocks,params=make_clocks(seed,index,full,axis,design)
    save(directory/'event.json',event);save(directory/'spatial_time_parameters.json',params)
    np.savez_compressed(directory/'clocks.npz',**clocks)
    support=full['support'];xx,yy=np.meshgrid(full['x_km'],full['y_km']);points=np.column_stack([xx[support],yy[support]])
    reference=full['u_m_per_yr'][support]
    evaluator=Evaluator(points,reference,clocks['onset'][support],clocks['retreat'][support],event,params['noise'])
    frames=frame_times(event);arrays=[];statistics=[]
    for frame in frames:
        u=evaluator.rate(frame['sim_Myr']);array=np.zeros(support.shape,dtype=np.float32);array[support]=u
        arrays.append(array);positive=u[u>0]
        statistics.append(dict(frame=frame['number'],sim_Myr=frame['sim_Myr'],peak_mm_yr=float(u.max()*1000),
                               area_km2=int((u>0).sum()),mean_over_reference_support_mm_yr=float(u.mean()*1000),
                               mean_over_active_support_mm_yr=float(positive.mean()*1000) if len(positive) else 0.))
    native=np.stack(arrays);del arrays
    np.savez_compressed(directory/'native_frames.npz',u_m_per_yr=native,sim_Myr=np.array([f['sim_Myr'] for f in frames]))
    del native,evaluator;gc.collect()
    cp=crop_points(selection);cu=crop['u_m_per_yr'].ravel();active=cu>0
    co,cr=clock_values(cp[active],full,clocks)
    ce=Evaluator(cp[active],cu[active],co,cr,event,params['noise'])
    ca=[]
    for frame in frames:
        arr=np.zeros(250000,dtype=np.float32);arr[active]=ce.rate(frame['sim_Myr']);ca.append(arr.reshape(500,500))
    np.savez_compressed(directory/'window_frames.npz',u_m_per_yr=np.stack(ca),sim_Myr=np.array([f['sim_Myr'] for f in frames]))
    del ce,ca;gc.collect()
    ids=np.sort(rng(seed,150+100*index).choice(len(points),min(2048,len(points)),replace=False))
    probe=Evaluator(points[ids],reference[ids],clocks['onset'][support][ids],clocks['retreat'][support][ids],event,params['noise'])
    stop=event['executed_until_sim_Myr'];tt=np.linspace(event['start_sim_Myr'],stop,401)
    rates=np.stack([probe.rate(t) for t in tt]);mult=np.stack([probe.multiplier(t) for t in tt])
    # Only elapsed simulation time is evaluated for delivered traces and displacement.
    cumulative=probe.displacement(event['start_sim_Myr'],stop,max_step_Myr=min(.1,event['duration_Myr']/100))
    bounds=[event['start_sim_Myr'],event['rise_end_sim_Myr'],event['hold_end_sim_Myr'],event['natural_end_sim_Myr']]
    fluct=[]
    for stage,a,b in zip(('rise','hold','fall'),bounds[:-1],bounds[1:]):
        ii=np.flatnonzero((tt[:-1]>=a)&(tt[1:]<=min(b,stop)))
        if len(ii):
            dr=np.diff(rates,axis=0)[ii];valid=np.maximum(rates[ii],rates[ii+1])>1e-8
            fluct.append(dict(stage=stage,steps=len(ii),fraction_increasing=float(np.sum((dr>0)&valid)/max(1,valid.sum())),
                              fraction_decreasing=float(np.sum((dr<0)&valid)/max(1,valid.sum()))))
    sensitivity=[]
    for cv in (.125,.25,.5):
        sd=probe.displacement(event['start_sim_Myr'],stop,max_step_Myr=min(.2,event['duration_Myr']/60),cv=cv)
        sensitivity.append(dict(cv=cv,cumulative_P10_P50_P90_m=np.quantile(sd,[.1,.5,.9]).tolist()))
    np.savez_compressed(directory/'probes.npz',points_km=points[ids],reference_u_m_yr=reference[ids],
                        onset=probe.onset,retreat=probe.retreat,t_sim_Myr=tt,u_m_per_yr=rates,multiplier=mult,cumulative_m=cumulative)
    on_window=float(event['start_sim_Myr']+co.min()*event['rise_Myr']) if np.any(active) else None
    summary=dict(seed=seed,event_index=index,event_id=event['event_id'],spatial_seed=bound['spatial_seed'],frames=len(frames),frame_statistics=statistics,
        native_shape=list(full['support'].shape),reference_support_cells=int(support.sum()),
        frame_peak_mm_yr=max(s['peak_mm_yr'] for s in statistics),
        probe_peak_mm_yr=float(rates.max()*1000),
        evaluated_until_sim_Myr=stop,frames_after_modern=0,
        crop_first_possible_uplift_sim_Myr=on_window,global_start_sim_Myr=event['start_sim_Myr'],
        actual_noise_multiplier_mean=float(mult.mean()),actual_noise_multiplier_cv=float(mult.std()/mult.mean()),
        cumulative_executed_P10_P50_P90_m=np.quantile(cumulative,[.1,.5,.9]).tolist(),
        cumulative_interval='event start through min(natural end, modern)',
        amplitude_sensitivity=sensitivity,local_change_diagnostics=fluct,
        evidence_scope='Timing proxy fit plus declared phase/variability designs; no full geophysical evolution validation.',
        elapsed_seconds=time.perf_counter()-tic)
    save(directory/'frames.json',frames);save(directory/'summary.json',summary)
    csvsave(directory/'frame_statistics.csv',statistics)
    print(seed,index,'frames',len(frames),'end',round(event['natural_end_sim_Myr'],3),'peak',round(summary['frame_peak_mm_yr'],3),'seconds',round(summary['elapsed_seconds'],1),flush=True)
    return summary

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seeds',nargs='+',type=int,default=list(range(1001,1009)));args=parser.parse_args()
    init();design=load(MODELS/'design.json');schedules=[];summaries=[]
    for seed in args.seeds:
        schedule=simulate(seed);schedules.append(schedule)
        save(OUT/f'seed{seed}/schedule.json',schedule)
        for event in schedule['events']:
            ensure_binding(seed,event)
            parent=field_directory(seed,event['event_index']);wp=window_directory(seed,event['event_index'])
            full=dict(np.load(parent/'field.npz'));axis=load(parent/'axis.json');selection=load(wp/'selection.json');crop=dict(np.load(wp/'window.npz'))
            summaries.append(generate_event(seed,event,full,axis,selection,crop,design))
    save(OUT/'schedules.json',schedules);csvsave(OUT/'all_events.csv',[e for s in schedules for e in s['events']])
    save(OUT/'batch.json',dict(version=VERSION,seeds=args.seeds,event_count=len(summaries),events=summaries,
          untriggered_seeds=[s['seed'] for s in schedules if not s['events']],
          spatial_binding='Every trigger creates a complete independent event with its own freshly sampled geometry, reference field, placement and lifecycle. Only the world platform and 500 km coordinates are shared across events.',
          selection='Every chronological trigger, no rejection based on end time or appearance.'))

if __name__=='__main__':main()
