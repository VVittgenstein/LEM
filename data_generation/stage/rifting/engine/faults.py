from __future__ import annotations
import math
import numpy as np
from scipy.integrate import cumulative_trapezoid
from .common import END,rng,save,OUT,smooth,stress_display
from .forcing import stress_at

def generate_faults(seed,model,episodes,basis,window):
    p=model['design_priors'];L=p['auxiliary_km'];random=rng(seed,21);origin=np.array(window['origin_km'])
    x=np.linspace(origin[0]+5,origin[0]+495,25);y=np.linspace(origin[1]+5,origin[1]+495,25)
    xx,yy=np.meshgrid(x,y);probes=np.column_stack([xx.ravel(),yy.ravel()])
    clock=np.arange(0,END+p['fault_clock_step_Myr']/2,p['fault_clock_step_Myr'])
    reference=model['stress_gradient_mpa_per_km']['value']*p['diagnostic_depth_km']
    hazard=[]
    for t in clock:
        mag,_=stress_display(stress_at(basis,episodes,t,probes,L))
        hazard.append(p['fault_birth_rate_per_Myr_at_reference_stress']*float(np.mean(mag))/reference)
    risk=cumulative_trapezoid(hazard,clock,initial=0)
    thresholds=[];current=float(random.exponential())
    while current<risk[-1]:thresholds.append(current);current+=float(random.exponential())
    births=np.interp(thresholds,risk,clock)
    records=[];rejections=[]
    for birth in births:
        for attempt in range(128):
            points=origin+random.uniform(0,500,(512,2))
            ss=stress_at(basis,episodes,birth,points,L);mag,angle=stress_display(ss)
            weights=mag.copy()
            # Existing geometry affects the conditional point process, not a material map.
            for old in records:
                distance=np.linalg.norm(points-np.array(old['centre_km']),axis=1)
                weights*=1-np.exp(-.5*(distance/max(10,old['length_km']*.18))**2)
            if weights.sum()<=0:raise ValueError('Zero stress hazard at sampled birth')
            k=int(random.choice(len(points),p=weights/weights.sum()));centre=points[k]
            length=float(random.lognormal(model['length_km']['log_mean'],model['length_km']['log_std']))
            if not 5<=length<=500:
                rejections.append(dict(time_Myr=float(birth),reason='geometry outside this 500 km implementation extent',length_km=length));continue
            perturb=float(random.normal(0,min(model['orientation_scatter_rad']['value'],np.deg2rad(25))))
            ext=float(angle[k]+perturb);dipdir=ext+(np.pi if random.random()<.5 else 0)
            strike=ext+np.pi/2
            dip=float(random.choice(model['dip_deg']['values']))
            depth=float(random.uniform(10,20))
            curve_amplitude=float(random.normal(0,p['fault_curvature_fraction']*length))
            along=np.linspace(-length/2,length/2,max(21,int(length/2)+1))
            tangent=np.array([math.cos(strike),math.sin(strike)]);normal=np.array([math.cos(ext),math.sin(ext)])
            phase=float(random.uniform(0,2*np.pi))
            deviation=curve_amplitude*(np.sin(2*np.pi*along/length+phase)-math.sin(phase))
            trace=centre+along[:,None]*tangent+deviation[:,None]*normal
            rate_model=model['slip_mm_per_year_given_length']
            rate=float(np.exp(rate_model['log_intercept']+rate_model['log_length_slope']*math.log(length)+random.normal(0,rate_model['log_residual_std'])))/1000
            direction=np.array([math.cos(dipdir),math.sin(dipdir)])
            a=ss[k];q0=float((a[0]-a[1])*math.cos(2*dipdir)+2*a[3]*math.sin(2*dipdir))
            if q0<=0:
                rejections.append(dict(time_Myr=float(birth),reason='normal slip direction not favoured by this stress state'));continue
            record=dict(id=f'R{len(records)+1:03d}',birth_Myr=float(birth),centre_km=centre.tolist(),length_km=length,
                trace_xy_km=trace.tolist(),dip_direction_rad=dipdir,strike_rad=strike,dip_deg=dip,
                top_depth_km=0,bottom_depth_km=depth,reference_slip_m_per_year=rate,reference_driving_MPa=q0,
                growth_Myr=float(max(.5,min(5,length/30))),conditional_seed_stream=21,geometry_attempt=attempt)
            records.append(record);break
        else:raise ValueError('Fault candidate attempts exhausted')
    natural_end=max([END]+[e['natural_end_Myr'] for e in episodes])
    # Exact causal breakpoints prevent interpolation from leaking slip before birth.
    times=np.unique(np.r_[np.linspace(0,natural_end,int(np.ceil(natural_end/.0625))+1),
                          [f['birth_Myr'] for f in records],
                          [t for e in episodes for t in e['knots_Myr']],END])
    times=times[(times>=0)&(times<=natural_end)]
    all_rates=[];all_cumulative=[]
    for f in records:
        dipdir=f['dip_direction_rad'];rates=[]
        centre=np.array([f['centre_km']]);growth=f['growth_Myr']
        for t in times:
            s=stress_at(basis,episodes,t,centre,L)[0]
            q=(s[0]-s[1])*math.cos(2*dipdir)+2*s[3]*math.sin(2*dipdir)
            # A continuous, one-sided normal-slip transfer with no material input.
            drive=max(0.,q/f['reference_driving_MPa']-.08)
            gain=drive*drive/(drive+.2) if drive else 0.
            growth_factor=float(smooth((t-f['birth_Myr'])/growth))
            peak=f['reference_slip_m_per_year']*gain*growth_factor
            rates.append(peak)
        centre_rates=np.asarray(rates)
        centre_cumulative=cumulative_trapezoid(centre_rates,times*1e6,initial=0)
        progress=centre_cumulative/max(f['reference_slip_m_per_year']*growth*1e6,1e-12)
        # Growth follows accumulated activity and remains unchanged during dormancy.
        patch=np.column_stack([smooth((progress-.3)/.7),np.ones(len(times)),smooth((progress-.5)/.8)])
        rates=centre_rates[:,None]*patch;cum=cumulative_trapezoid(rates,times*1e6,axis=0,initial=0)
        f['geometry_times_Myr']=times.tolist();f['geometry_fraction']=(.30+.70*smooth(progress/1.3)).tolist()
        active=np.max(rates,axis=1)>1e-10
        changes=np.flatnonzero(np.diff(np.r_[False,active,False].astype(int)))
        intervals=[]
        for start,end in changes.reshape(-1,2):
            aa=float(times[start]);dd=float(times[min(end,len(times)-1)])
            peak_index=start+int(np.argmax(rates[start:end].max(axis=1)))
            bb=float(times[peak_index]);intervals.append(dict(start_Myr=aa,peak_Myr=bb,natural_end_Myr=dd))
        f['active_intervals']=intervals
        f['last_slip_Myr']=max([f['birth_Myr']]+[x['natural_end_Myr'] for x in intervals])
        f['cumulative_peak_slip_m_at_modern']=float(np.max([np.interp(END,times,cum[:,i]) for i in range(3)]))
        f['small_strain_diagnostic']=f['cumulative_peak_slip_m_at_modern']/(f['length_km']*1000)
        all_rates.append(rates);all_cumulative.append(cum)
    data=dict(times_Myr=times,slip_rates_m_per_year=np.asarray(all_rates).reshape(len(records),len(times),3),cumulative_slip_m=np.asarray(all_cumulative).reshape(len(records),len(times),3))
    save(OUT/f'seed{seed}'/'fault_generation_checks.json',dict(hazard_clock_Myr=clock.tolist(),hazard_per_Myr=hazard,risk_integral=float(risk[-1]),
        births_Myr=births.tolist(),rejections=rejections,absolute_birth_rate_identity='design prior',
        dip_depth_identity='regional dip resampling; 10-20 km depth is a design range',
        transfer_identity='positive resolved horizontal differential stress with smooth gain; not a calibrated frictional failure law',
        probability_conditioning='stress history and previously generated fault centres; no material map'))
    return records,data

def rates_at(data,t):
    times=data['times_Myr'];rates=data['slip_rates_m_per_year']
    return np.array([[np.interp(t,times,rates[i,:,j]) for j in range(3)] for i in range(len(rates))]).reshape(len(rates),3)

def cumulative_at(data,t):
    times=data['times_Myr'];rates=data['slip_rates_m_per_year'];cumulative=data['cumulative_slip_m']
    k=int(np.clip(np.searchsorted(times,t,side='right')-1,0,len(times)-1));out=cumulative[:,k,:].copy()
    if k<len(times)-1 and t>times[k]:
        frac=(t-times[k])/(times[k+1]-times[k]);endrate=rates[:,k,:]+frac*(rates[:,k+1,:]-rates[:,k,:])
        out+=(rates[:,k,:]+endrate)*.5*(t-times[k])*1e6
    return out

def geometry_at(f,t):
    if t<f['birth_Myr']:return np.empty((0,2))
    trace=np.asarray(f['trace_xy_km']);fraction=float(np.interp(t,f['geometry_times_Myr'],f['geometry_fraction']))
    count=max(3,int(np.ceil(len(trace)*fraction)));start=(len(trace)-count)//2
    return trace[start:start+count]
