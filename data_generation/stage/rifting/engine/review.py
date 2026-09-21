"""Derived inspection tables and figures. Does not draw or change process histories."""
from __future__ import annotations
import argparse,csv,math
import numpy as np
from .common import save,load
from .products import Run
from .forcing import amplitude
from .faults import geometry_at
from .rendering import plt,CMAP,norm_for

def table(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        if rows:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def overlap(a,b):
    intervals=[]
    for x in a['active_intervals']:
        for y in b['active_intervals']:
            lo=max(x['start_Myr'],y['start_Myr'],0);hi=min(x['natural_end_Myr'],y['natural_end_Myr'],48)
            if hi>lo:intervals.append([lo,hi])
    return intervals

def cross2(a,b):return a[...,0]*b[...,1]-a[...,1]*b[...,0]

def trace_relation(a,b):
    r=np.diff(a,axis=0)[:,None,:];s=np.diff(b,axis=0)[None,:,:]
    delta=b[None,:-1,:]-a[:-1,None,:];den=cross2(r,s)
    good=abs(den)>1e-12;safe=np.where(good,den,1)
    t=cross2(delta,s)/safe;u=cross2(delta,r)/safe
    meets=good&(t>=0)&(t<=1)&(u>=0)&(u<=1)
    contacts=(a[:-1,None,:]+t[...,None]*r)[meets]
    contacts=np.unique(np.round(contacts,6),axis=0)
    def point_to_segments(points,line):
        start=line[:-1];edge=np.diff(line,axis=0);den=np.sum(edge**2,axis=1)
        delta=points[:,None,:]-start
        fraction=np.clip(np.sum(delta*edge,axis=2)/np.maximum(den,1e-20),0,1)
        return float(np.linalg.norm(delta-fraction[...,None]*edge,axis=2).min())
    distance=0. if len(contacts) else min(point_to_segments(a,b),point_to_segments(b,a))
    return distance,contacts

def review(seed=1001):
    run=Run(seed);dest=run.path/'review';dest.mkdir(exist_ok=True)
    forces=[]
    for e in run.episodes:
        tt=np.linspace(e['start_Myr'],e['natural_end_Myr'],1001)
        forces.append(dict(id=e['id'],kind=e['kind'],x_km=e['position_km'][0],y_km=e['position_km'][1],z_km=e['position_km'][2],
            direction_x=e['direction'][0],direction_y=e['direction'][1],direction_z=e['direction'][2],radius_km=e['radius_km'],
            start_Myr=e['start_Myr'],natural_end_Myr=e['natural_end_Myr'],duration_Myr=e['natural_end_Myr']-e['start_Myr'],
            reference_force_N=e['reference_force_N'],sampled_peak_force_N=float(np.max(amplitude(e,tt)))*e['reference_force_N']))
    table(dest/'forcing_catalog.csv',forces)
    faults=[]
    for f in run.faults:
        faults.append({k:f[k] for k in ['id','birth_Myr','last_slip_Myr','length_km','dip_deg','bottom_depth_km','reference_slip_m_per_year','cumulative_peak_slip_m_at_modern','small_strain_diagnostic']})
    table(dest/'fault_catalog.csv',faults)
    relations=[];matrix=np.zeros((len(faults),len(faults)))
    for i,a in enumerate(run.faults):
        for j in range(i+1,len(faults)):
            b=run.faults[j];periods=overlap(a,b);duration=sum(y-x for x,y in periods);matrix[i,j]=matrix[j,i]=duration
            distance,contacts=trace_relation(geometry_at(a,48),geometry_at(b,48))
            relations.append(dict(first=a['id'],second=b['id'],present_trace_distance_km=distance,present_surface_crossings=len(contacts),
                active_overlap_Myr=duration,active_overlap_intervals_Myr=periods,surface_crossing_global_xy_km=contacts.tolist()))
    save(dest/'fault_relations.json',dict(meaning='Derived geometry and overlapping activity. Surface crossings do not establish underground connection or mechanical linkage.',pairs=relations))
    table(dest/'fault_relations.csv',[{k:v for k,v in r.items() if k not in ['active_overlap_intervals_Myr','surface_crossing_global_xy_km']} for r in relations])
    if len(faults):
        fig,ax=plt.subplots(figsize=(8,7),layout='constrained');im=ax.imshow(matrix,cmap='Blues',vmin=0,vmax=max(float(matrix.max()),1e-6))
        ax.set_xticks(range(len(faults)),[f['id'] for f in run.faults],rotation=90);ax.set_yticks(range(len(faults)),[f['id'] for f in run.faults])
        ax.set_title('断层两两同时活动时长\n统计范围为模拟0至48 Myr；空间连接另行判断');fig.colorbar(im,ax=ax,label='Myr')
        fig.savefig(dest/'fault_activity_overlap.png',dpi=170);plt.close(fig)
    # Point histories use the very same response basis and integrated slip coefficients.
    U,displacement,_=run.surface_fields(48)
    selected=[(50,50),(250,250),(450,450),(50,450),(450,50)]
    selected.extend([(int(i[1]),int(i[0])) for i in [np.unravel_index(displacement.argmin(),displacement.shape),np.unravel_index(displacement.argmax(),displacement.shape)]])
    selected=list(dict.fromkeys(selected));xx=np.array([x for x,y in selected]);yy=np.array([y for x,y in selected])
    coefficients=run.vertical[:,yy,xx];times=run.history['times_Myr'];keep=times<=48
    rates=run.history['slip_rates_m_per_year'][:,keep,:].transpose(1,0,2).reshape(keep.sum(),-1)
    cum=run.history['cumulative_slip_m'][:,keep,:].transpose(1,0,2).reshape(keep.sum(),-1)
    point_U=rates@coefficients*1000;point_disp=cum@coefficients
    np.savez_compressed(dest/'point_history.npz',time_Myr=times[keep],U_mm_per_year=point_U,displacement_m=point_disp,grid_xy=np.asarray(selected))
    save(dest/'point_metadata.json',dict(points=[dict(id=f'P{i+1}',cell_xy=[x,y],local_xy_km=[x+.5,y+.5]) for i,(x,y) in enumerate(selected)],selection='five fixed positions plus present extrema; extrema positions are diagnostic choices'))
    fig=plt.figure(figsize=(14,7),layout='constrained');gs=fig.add_gridspec(2,2,width_ratios=[1,1.5]);ax=fig.add_subplot(gs[:,0])
    im=ax.imshow(displacement,origin='lower',extent=[0,500,0,500],cmap=CMAP,norm=norm_for(run.scale['displacement_m_min'],run.scale['displacement_m_max']))
    for i,(x,y) in enumerate(selected):ax.text(x+.5,y+.5,f'P{i+1}',fontsize=8,bbox=dict(facecolor='white',alpha=.9,pad=1,edgecolor='none'))
    ax.set(title='现代累计位移与固定查询点',xlabel='数据域X / km',ylabel='数据域Y / km');fig.colorbar(im,ax=ax,label='m',shrink=.65)
    for row,values,label in [(0,point_U,'构造U / mm/yr'),(1,point_disp,'累计位移 / m')]:
        bx=fig.add_subplot(gs[row,1]);bx.axhline(0,color='#999999',lw=.7)
        for i in range(len(selected)):bx.plot(times[keep],values[:,i],label=f'P{i+1}',lw=1)
        bx.set(xlim=(0,48),xlabel='模拟时间 / Myr',ylabel=label);bx.legend(ncol=4,fontsize=8)
    fig.savefig(dest/'point_histories.png',dpi=165);plt.close(fig)
    metrics=load(run.path/'frame_metrics.json');diagnostics=load(run.path/'validation/numerical_diagnostics.json')
    summary=dict(seed=seed,auxiliary_km=run.length,window=run.window,far_processes=sum(e['kind']=='far' for e in run.episodes),
        local_processes=sum(e['kind']=='local' for e in run.episodes),faults=len(faults),frames=len(run.timeline['frames']),nine_panel_pages_each=len(run.timeline['nine_panel_pages']),
        stress_solver_spacing_km=run.length/(run.basis.shape[1]-1),response_solver_spacing_km=1000/(run.model['design_priors']['response_nodes']-1),
        display_cells_km=1,raw_full_pixels=int(run.length)*12,scales=run.scale,
        all_frame_windows_qualify=all(r['window_qualifies'] for r in metrics),
        largest_slip_length_ratio=max([f['small_strain_diagnostic'] for f in run.faults]+[0]),
        instantaneous_U_mm_per_year=[min(r['U_min_mm_per_year'] for r in metrics),max(r['U_max_mm_per_year'] for r in metrics)],
        present_displacement_m=[float(displacement.min()),float(displacement.max())],
        numerical_status='mesh sensitivity remains; no converged-accuracy claim',geological_status='explicit regional/proxy/design model; long-term calibration pending',
        LEM_status='standalone input-generation research run; no erosion or sedimentation executed')
    save(dest/'sample_summary.json',summary)
    print('Saved review tables, pair histories and point histories.',flush=True)
    return summary

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=1001);args=ap.parse_args();review(args.seed)
