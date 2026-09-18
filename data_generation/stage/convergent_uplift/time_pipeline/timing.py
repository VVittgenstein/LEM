"""Continuous-time hazards with epoch embargoes, and complete event lifetimes."""
from scipy.special import ndtr
from fit_models import distribution
from tcontext import *

def increment(wait, dt, epoch, model):
    if dt < 0 or wait < 0:raise ValueError('Negative physical time')
    k=model['shape'];eta=model['reference_median_wait_Myr']/np.log(2)**(1/k)
    c=model['epochs'][epoch]['growth_multiplier']/eta**k
    return float(c*((wait+dt)**k-wait**k))

def step_probability(wait, dt, epoch, model):
    """Conditional probability on a boundary-free eligible interval, dt in Myr."""
    return float(-np.expm1(-increment(wait,dt,epoch,model)))

def lifetime(random, duration_model, design):
    spec=duration_model['selected'];d=distribution(spec['family'],spec['parameters'])
    total=float(d.ppf(random.uniform(np.finfo(float).eps,1-np.finfo(float).eps)))
    hold=float(random.beta(*design['hold_fraction_beta'])) if random.random()<design['hold_probability'] else 0.
    rise=float(random.beta(*design['rise_share_of_nonhold_beta']))
    up=total*(1-hold)*rise;steady=total*hold;down=total-up-steady
    return dict(duration_Myr=total,rise_Myr=up,hold_Myr=steady,fall_Myr=down,hold_present=bool(steady>0))

def simulate(seed, dt_Myr=.025, horizon_Myr=48., trigger_model=None, duration_model=None, design=None):
    """An exponential cumulative-hazard threshold couples identical seeds across dt.

    This is equivalent in law to conditional Bernoulli trials at each step. A
    threshold crossing is located within the step, avoiding dt quantization.
    """
    if dt_Myr<=0:raise ValueError('dt must be positive')
    model=trigger_model or load(MODELS/'trigger.json');dur=duration_model or load(MODELS/'duration.json')
    design=design or load(MODELS/'design.json');random=rng(seed,10)
    phase_random=rng(seed,11);t=0.;wait=0.;threshold=float(random.exponential());hazard=0.
    events=[];decisions=[]
    while t < horizon_Myr-1e-11:
        epoch=epoch_index(t)
        if epoch is None:break
        stop=min(horizon_Myr,48-EPOCHS[epoch][3]);step=min(dt_Myr,stop-t)
        dh=increment(wait,step,epoch,model)
        if hazard+dh < threshold-1e-13:
            hazard+=dh;wait+=step;t+=step
            if abs(t-stop)<1e-10:t=stop
            continue
        k=model['shape'];eta=model['reference_median_wait_Myr']/np.log(2)**(1/k)
        c=model['epochs'][epoch]['growth_multiplier']/eta**k
        delta=((wait**k+(threshold-hazard)/c)**(1/k)-wait)
        start=t+float(np.clip(delta,0,step));life=lifetime(phase_random,dur,design);end=start+life['duration_Myr']
        event=dict(seed=int(seed),world_seed=int(seed),event_index=len(events),event_id=f'convergent-{seed}-{len(events)+1:02d}',activity_type='convergent_uplift',start_sim_Myr=start,start_age_Ma=48-start,
                   natural_end_sim_Myr=end,natural_end_age_Ma=48-end,start_epoch=EPOCHS[epoch][0],
                   executed_until_sim_Myr=min(end,horizon_Myr),ongoing_at_modern=bool(end>horizon_Myr),
                   hazard_threshold=threshold,eligible_wait_Myr=wait+delta,**life)
        event['rise_end_sim_Myr']=start+life['rise_Myr'];event['hold_end_sim_Myr']=event['rise_end_sim_Myr']+life['hold_Myr']
        events.append(event)
        if end>=horizon_Myr:break
        end_epoch=epoch_index(end)
        if end_epoch is None:break
        resume=48-EPOCHS[end_epoch][3]
        decisions.append(dict(event_index=event['event_index'],end_sim_Myr=end,embargo_epoch=EPOCHS[end_epoch][0],resume_sim_Myr=resume))
        t=resume;wait=0.;hazard=0.;threshold=float(random.exponential())
    return dict(seed=int(seed),dt_Myr=dt_Myr,horizon_Myr=horizon_Myr,events=events,embargoes=decisions,
                first_event_rule='First chronological trigger; no end-date, phase, or appearance filtering.',
                epoch_boundaries='Half-open forward intervals; event ending exactly on a new epoch boundary embargoes that new epoch.')

def frame_times(event, cutoff=48.):
    """Unchanged full-stage denominators; shared endpoints merged; optional modern frame."""
    start=event['start_sim_Myr'];up=event['rise_Myr'];hold=event['hold_Myr'];down=event['fall_Myr']
    raw=[]
    for name,duration,t0 in [('上升',up,start),('维持',hold,start+up),('下降',down,start+up+hold)]:
        if duration<=0:continue
        for q in (0.,.33,.66,1.):
            t=t0+duration*q
            if name=='下降' and q==1.:t=event['natural_end_sim_Myr']
            if abs(t-cutoff)<1e-10:t=cutoff
            if t<=cutoff+1e-10:raw.append(dict(sim_Myr=t,stage=name,elapsed_fraction=q,stage_duration_Myr=duration,modern=False))
    raw.sort(key=lambda r:r['sim_Myr']);frames=[]
    for item in raw:
        if frames and abs(item['sim_Myr']-frames[-1]['sim_Myr'])<1e-9:
            frames[-1]['labels'].append({k:v for k,v in item.items() if k not in ('sim_Myr','modern')})
        else:frames.append(dict(sim_Myr=item['sim_Myr'],modern=abs(item['sim_Myr']-cutoff)<1e-9,
                                labels=[{k:v for k,v in item.items() if k not in ('sim_Myr','modern')}]))
    if start<cutoff<event['natural_end_sim_Myr'] and not any(abs(f['sim_Myr']-cutoff)<1e-9 for f in frames):
        if cutoff<start+up:stage,t0,length='上升',start,up
        elif cutoff<start+up+hold:stage,t0,length='维持',start+up,hold
        else:stage,t0,length='下降',start+up+hold,down
        frames.append(dict(sim_Myr=cutoff,modern=True,labels=[dict(stage=stage,elapsed_fraction=(cutoff-t0)/length,stage_duration_Myr=length)]))
    for i,f in enumerate(frames,1):f.update(number=i,age_Ma=max(0.,48-f['sim_Myr']),elapsed_Myr=f['sim_Myr']-start)
    return frames

def smoothstep(z):
    z=np.clip(z,0.,1.);return z*z*(3-2*z)

def envelope(t,event,onset,retreat):
    age=t-event['start_sim_Myr'];T=event['duration_Myr']
    if age<=0 or age>=T:return np.zeros_like(onset,dtype=float)
    up=event['rise_Myr'];hold=event['hold_Myr'];down=event['fall_Myr']
    # All local growth completes by the end of the rise phase.
    rise_begin=onset*up
    rise_end=(.45+.55*np.clip(onset/.70,0,1))*up
    rise_length=rise_end-rise_begin
    growth=smoothstep((age-rise_begin)/np.maximum(rise_length,1e-12))
    # A positive-length global mature stage is optional. Individual sites have plateaus.
    fall_begin=up+hold+.65*retreat*down
    fall_length=.35*down
    decay=1-smoothstep((age-fall_begin)/max(fall_length,1e-12))
    return growth*decay

if __name__=='__main__':
    init();records=[simulate(seed) for seed in range(1001,1009)]
    save(OUT/'schedules.json',records)
    csvsave(OUT/'all_events.csv',[e for r in records for e in r['events']])
    for r in records:print(r['seed'],[(round(e['start_sim_Myr'],2),round(e['duration_Myr'],2),e['hold_present']) for e in r['events']],flush=True)
