from __future__ import annotations
import argparse,math,time
import numpy as np
from .common import OUT,save,load,stress_display
from .forcing import coefficients,score_windows
from .elastic import sample_plane
from .faults import rates_at,cumulative_at

class Run:
    def __init__(self,seed=1001):
        self.path=OUT/f'seed{seed}';self.model=load(self.path/'model_run.json');self.episodes=load(self.path/'forcing.json')
        self.window=load(self.path/'window.json');self.faults=load(self.path/'faults.json');self.history=dict(np.load(self.path/'fault_history.npz'))
        self.timeline=load(self.path/'timeline.json');self.basis=np.load(self.path/'stress_basis.npz')['basis_MPa']
        self.response=np.load(self.path/'response_basis.npy',mmap_mode='r') if self.faults else np.zeros((0,500,500,3),dtype=np.float32)
        self.vertical=np.ascontiguousarray(self.response[...,2]);self.length=self.model['design_priors']['auxiliary_km']
        self.scale=load(self.path/'scales.json') if (self.path/'scales.json').exists() else None
    def planes(self,t):
        far=np.einsum('e,eyxc->yxc',coefficients(self.episodes,t,'far'),self.basis)
        local=np.einsum('e,eyxc->yxc',coefficients(self.episodes,t,'local'),self.basis)
        return dict(far=far,local=local,total=far+local)
    def surface_fields(self,t):
        rate=rates_at(self.history,t).ravel();cumulative=cumulative_at(self.history,t).ravel()
        U=np.einsum('p,pyx->yx',rate,self.vertical,optimize=True)
        disp=np.einsum('p,pyx->yx',cumulative,self.vertical,optimize=True)
        return U,disp,rate.reshape(-1,3)
    def stress_grid(self,plane,origin=(0,0),size=None):
        size=int(size or self.length);x=np.arange(size)+.5+origin[0];y=np.arange(size)+.5+origin[1]
        xx,yy=np.meshgrid(x,y)
        # Only the horizontal components are needed for this declared display quantity.
        s=sample_plane(plane[...,[0,1,3]],xx,yy,self.length).astype(np.float32)
        mag=np.sqrt((s[...,0]-s[...,1])**2+4*s[...,2]**2)
        angle=.5*np.arctan2(2*s[...,2],s[...,0]-s[...,1])
        return mag,angle

def mask_coverage(eligible,length):
    length=int(length);difference=np.zeros((length+1,length+1),np.int32)
    for row,col in np.argwhere(eligible):
        x0=max(0,int(col*50-250));x1=min(length,x0+500)
        y0=max(0,int(row*50-250));y1=min(length,y0+500)
        if x1>x0 and y1>y0:
            difference[y0,x0]+=1;difference[y1,x0]-=1;difference[y0,x1]-=1;difference[y1,x1]+=1
    return np.cumsum(np.cumsum(difference,axis=0),axis=1)[:-1,:-1]>0

def prepare(seed=1001):
    run=Run(seed);directory=run.path/'frames';directory.mkdir(exist_ok=True)
    extrema=dict(stress_MPa_max=0.,stress_local_MPa_max=0.,U_mm_per_year_min=0.,U_mm_per_year_max=0.,displacement_m_min=0.,displacement_m_max=0.)
    metrics=[]
    for i,frame in enumerate(run.timeline['frames']):
        t=frame['elapsed_Myr'];planes=run.planes(t);U,displacement,rates=run.surface_fields(t)
        for s in planes.values():extrema['stress_MPa_max']=max(extrema['stress_MPa_max'],float(stress_display(s)[0].max()))
        extrema['stress_local_MPa_max']=max(extrema['stress_local_MPa_max'],float(stress_display(planes['local'])[0].max()))
        extrema['U_mm_per_year_min']=min(extrema['U_mm_per_year_min'],float(U.min())*1000)
        extrema['U_mm_per_year_max']=max(extrema['U_mm_per_year_max'],float(U.max())*1000)
        extrema['displacement_m_min']=min(extrema['displacement_m_min'],float(displacement.min()))
        extrema['displacement_m_max']=max(extrema['displacement_m_max'],float(displacement.max()))
        np.savez_compressed(directory/(frame['frame_id']+'.npz'),far=planes['far'].astype(np.float32),local=planes['local'].astype(np.float32),
            U_m_per_year=U.astype(np.float32),displacement_m=displacement.astype(np.float32),slip_rates_m_per_year=rates)
        score,eligible=score_windows(run.basis,run.episodes,t,run.length,run.window['threshold'],run.window['minimum_distance_from_side_km'])
        row,col=np.rint(np.array(run.window['centre_km'])[::-1]/50).astype(int)
        metrics.append(dict(frame_id=frame['frame_id'],elapsed_Myr=t,age_Ma_BP=48-t,active_faults=int(np.sum(rates.max(axis=1)>1e-10)),
            born_faults=sum(f['birth_Myr']<=t for f in run.faults),far_window_score=float(score[row,col]),window_qualifies=bool(eligible[row,col]),
            U_min_mm_per_year=float(U.min())*1000,U_max_mm_per_year=float(U.max())*1000,
            displacement_min_m=float(displacement.min()),displacement_max_m=float(displacement.max())))
        if i%25==0:print('Snapshot',i+1,'/',len(run.timeline['frames']),flush=True)
    # One signed scale per physical quantity; zero is annotated separately.
    for prefix in ['U_mm_per_year','displacement_m']:
        limit=max(abs(extrema[prefix+'_min']),abs(extrema[prefix+'_max']),1e-12)
        extrema[prefix+'_min']=-limit;extrema[prefix+'_max']=limit
    extrema['stress_MPa_max']=max(extrema['stress_MPa_max'],1e-6)
    save(run.path/'scales.json',extrema);save(run.path/'frame_metrics.json',metrics)
    save(run.path/'display_definition.json',dict(grid_spacing_km=1,full_size_cells=[run.length,run.length],window_cells=[500,500],
        stress_magnitude='horizontal differential stress sqrt((sxx-syy)^2+4*sxy^2), MPa',
        direction='horizontal principal axis with larger algebraic stress; tension positive; angle from +X counterclockwise modulo 180 degrees',
        stress_scope='3D elastic perturbation at 10 km reference depth; lithostatic pressure excluded from these three contribution plots',
        colors='viewer fem, 12 equal positive bands; local contribution has its own fixed range and exact zero is white',
        local_stress_color_limits_MPa=[0,extrema['stress_local_MPa_max']],local_zero_display='white; cells retained without direction glyphs',
        raw_pixels_per_cell=12,full_resolution_mode='indexed PNG with a direction glyph in every cell; degenerate directions use a circle',
        solver_grid_km=run.length/(run.basis.shape[1]-1),interpolation='linear nodal stress interpolation; 1 km is the query grid, not solver accuracy'))
    print('Prepared all snapshots and shared scales.',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=1001);a=ap.parse_args();prepare(a.seed)
