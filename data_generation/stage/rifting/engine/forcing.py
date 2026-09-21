from __future__ import annotations
import math,time
import numpy as np
from scipy.ndimage import uniform_filter
from .common import OUT,END,rng,save,envelope,stress_display
from .elastic import ElasticBox,sample_plane

def draw_duration(random,model,factor=1):
    for _ in range(100):
        value=float(random.lognormal(model['log_mean'],model['log_std'])*factor)
        if .75<=value<=96:return value
    raise ValueError('Duration sampling failed under declared numerical range')

def create_episodes(seed,model):
    prior=model['design_priors'];L=prior['auxiliary_km'];episodes=[]
    for kind,stream,mean in [('far',11,prior['far_mean_interval_Myr']),('local',12,prior['local_mean_interval_Myr'])]:
        random=rng(seed,stream);start=0. if kind=='far' else float(random.exponential(mean))
        i=0
        while start<END:
            i+=1
            duration=draw_duration(random,model['duration_Myr'],1 if kind=='far' else prior['local_duration_fraction'])
            hold=float(random.beta(*prior['lifecycle_plateau_beta'])) if random.random()<prior['lifecycle_plateau_probability'] else 0.
            rise=float(random.beta(*prior['lifecycle_rise_beta']))*(1-hold);a=start;b=a+duration*rise;c=b+duration*hold;d=a+duration
            theta=float(random.uniform(0,np.pi if kind=='far' else 2*np.pi));tilt=float(random.normal(0,.12))
            if kind=='far':
                side=int(random.integers(4));coordinate=float(random.uniform(.15,.85)*L)
                position=[[0,coordinate,-20],[L,coordinate,-20],[coordinate,0,-20],[coordinate,L,-20]][side]
                outward=np.array([[-1,0],[1,0],[0,-1],[0,1]])[side]
                v=np.array([math.cos(theta),math.sin(theta),tilt])
                if v[:2]@outward<0:v=-v
                radius=float(random.uniform(*prior['far_contact_fraction'])*L)
            else:
                side=-1;position=[*random.uniform(.03,.97,2)*L,-prior['reference_thickness_km']]
                v=np.array([math.cos(theta),math.sin(theta),tilt]);radius=float(random.uniform(*prior['local_radius_fraction'])*L)
            v/=np.linalg.norm(v)
            episodes.append(dict(id=f'{kind[0].upper()}{i:03d}',kind=kind,start_Myr=a,natural_end_Myr=d,knots_Myr=[a,b,c,d],
                position_km=position,side=side,radius_km=radius,direction=v.tolist(),
                amplitude_multiplier=float(random.lognormal(-.5*prior['strength_log_std']**2,prior['strength_log_std'])),
                noise_phases=random.uniform(0,2*np.pi,4).tolist(),noise_periods_Myr=prior['strength_periods_Myr']))
            if i>prior['source_count_max']:raise ValueError('Too many forcing processes')
            start+=float(random.exponential(mean))
    return episodes

def amplitude(episode,t):
    x=np.asarray(t,float)
    wave=sum(np.sin(2*np.pi*x/p+phase) for p,phase in zip(episode['noise_periods_Myr'],episode['noise_phases']))/math.sqrt(2)
    return envelope(episode,x)*np.exp(.12*wave-.5*.12**2)*episode['amplitude_multiplier']

def coefficients(episodes,t,kind=None):
    return np.array([float(amplitude(e,t)) if kind is None or e['kind']==kind else 0. for e in episodes])

def source_load(box,episode):
    """Unit resultant applied over a finite contact, plus the declared side reaction."""
    e=episode;centre=np.array(e['position_km'])*1000;radius=e['radius_km']*1000
    delta=box.face_centres-centre
    if e['kind']=='far':
        side=e['side'];axis=0 if side<2 else 1;sign=-1 if side in (0,2) else 1
        eligible=box.face_normal[:,axis]*sign>.9
        distance=abs(delta[:,1-axis])
    else:
        eligible=box.face_normal[:,2]<-.9;distance=np.linalg.norm(delta[:,:2],axis=1)
    shape=np.exp(-.5*(distance/radius)**2)*eligible;shape[distance>3*radius]=0
    normalization=float(np.sum(shape*box.face_area))
    if normalization<=0:raise ValueError('Source contact is unresolved')
    force=box.traction(shape[:,None]*np.array(e['direction'])[None,:]/normalization)
    return box.balanced(force)

def diagnostic_plane(box,u,depth_km):
    zidx=(box.depth_km-depth_km)/box.depth_km*(box.nz-1)
    z0=int(zidx);alpha=zidx-z0;nodal=box.nodal_stress(u)
    return (1-alpha)*nodal[z0]+alpha*nodal[min(z0+1,box.nz-1)]

def build_basis(episodes,model,seed):
    p=model['design_priors'];L=p['auxiliary_km'];begin=time.perf_counter()
    box=ElasticBox(L,p['stress_solver_nodes'],p['stress_depth_layers'],p['reference_thickness_km'],p['elastic_young_GPa']*1e9,p['elastic_poisson'])
    basis=[];records=[]
    depth=p['diagnostic_depth_km']
    for e in episodes:
        balanced,check=source_load(box,e)
        u,reaction=box.solve(balanced)
        plane=diagnostic_plane(box,u,depth)
        mag,_=stress_display(plane)
        if e['kind']=='far':
            lo=box.n//4;hi=box.n-lo;ref=float(np.median(mag[lo:hi,lo:hi]))
        else:ref=float(np.max(mag))
        target=model['stress_gradient_mpa_per_km']['value']*depth*1e6*(1 if e['kind']=='far' else p['local_peak_fraction'])
        scale=target/max(ref,1e-30)
        e['reference_force_N']=scale;e['reference_stress_target_MPa']=target/1e6
        basis.append(plane*scale/1e6)
        records.append(dict(id=e['id'],**check,gauge_reaction_relative=reaction,reference_force_N=scale))
        print('Stress response',e['id'],flush=True)
    basis=np.asarray(basis,dtype=np.float64)
    save(OUT/f'seed{seed}'/'forcing_checks.json',dict(reference_box='homogeneous linear elastic, three dimensional',nodes=len(box.nodes),elements=len(box.tet),
         factor_seconds=box.factor_seconds,wall_seconds=time.perf_counter()-begin,processes=records,stress_depth_km=depth,
         pressure_background='Lithostatic reference is not included in displayed perturbations.'))
    return basis

def stress_at(basis,episodes,t,points,length,kind=None):
    plane=np.einsum('e,eyxc->yxc',coefficients(episodes,t,kind),basis)
    points=np.asarray(points)
    return sample_plane(plane,points[...,0],points[...,1],length)

def score_windows(basis,episodes,t,length,threshold=.30,min_distance=250):
    dx=50.;n=int(round(length/dx));size=10
    points=(np.arange(n)+.5)*dx;xx,yy=np.meshgrid(points,points)
    coarse=np.einsum('e,eyxc->yxc',coefficients(episodes,t,'far'),basis)
    far=sample_plane(coarse,xx,yy,length)[...,[0,1,3]]
    weights=np.array([1,1,2])
    mean=np.stack([uniform_filter(far[...,i],size=size,mode='nearest') for i in range(3)],axis=-1)
    squares=np.sum(far**2*weights,axis=-1)
    variance=np.maximum(uniform_filter(squares,size=size,mode='nearest')-np.sum(mean**2*weights,axis=-1),0)
    denominator=np.sqrt(np.sum(mean**2*weights,axis=-1))
    score=np.sqrt(variance)/np.maximum(denominator,1e-8)
    # A vanishing far contribution is not assigned a fictitious direction.
    if float(np.max(denominator))<1e-6:score[:]=0
    # Even ten-cell filter is centred at i*50 km for cell centres (i+.5)*50 km.
    x=np.arange(n)*dx;xx,yy=np.meshgrid(x,x)
    distance=np.minimum.reduce([xx,yy,length-xx,length-yy])-250
    eligible=(score<=threshold)&(distance>=min_distance)
    return score,eligible

def choose_window(basis,episodes,model,seed):
    p=model['design_priors'];L=p['auxiliary_km'];times=sorted(set([0.,END]+[float(t) for e in episodes if e['kind']=='far' for t in np.linspace(e['start_Myr'],e['natural_end_Myr'],25) if 0<=t<=END]))
    mask=np.ones((int(round(L/50)),)*2,bool);maxscore=np.zeros_like(mask,dtype=float)
    for t in times:
        score,valid=score_windows(basis,episodes,t,L,p['uniformity_limit'],p['minimum_distance_km']);mask&=valid;maxscore=np.maximum(maxscore,score)
    choices=np.argwhere(mask)
    if not len(choices):
        save(OUT/f'seed{seed}'/f'window_failure_{int(L)}.json',dict(length_km=L,minimum_worst_score=float(maxscore[10:-10,10:-10].min()),threshold=p['uniformity_limit']))
        raise ValueError('No fixed window satisfies the declared background criterion; no threshold relaxation.')
    row,col=choices[int(rng(seed,14).integers(len(choices)))];step=50.
    centre=np.array([col,row])*step;origin=centre-250
    result=dict(origin_km=origin.tolist(),centre_km=centre.tolist(),size_km=500,grid_spacing_km=1,
         threshold=p['uniformity_limit'],minimum_distance_from_side_km=p['minimum_distance_km'],
         sampled_check_times_Myr=times,eligible_centres=int(len(choices)),selected_score=float(maxscore[row,col]),
         rule='Frobenius RMS spatial variation of the horizontal far-stress tensor divided by mean tensor norm over a 500 km neighbourhood; side distance checked separately.',
         green_mask_meaning='union of qualifying 500 km windows; qualification uses far contribution only',
         temporal_qualification='finite sampled times; continuous-time guarantee not claimed')
    return result,mask,maxscore
