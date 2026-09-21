"""Shared visualization times from saved histories; no geological generation."""
from __future__ import annotations
import math

SIMULATION_YEARS = 48_000_000.0

def shared_timeline(intervals=(), transitions=(), simulation_end=SIMULATION_YEARS, context_years=None, fractions=None):
    """Return synchronized frames and nine-panel pages.

    intervals: id, kind, start_year, natural_end_year, optional phases
    phases: name, start_year, end_year, taken from generator records
    transitions: id, kind, time_year, optional detail
    context_years: explicit plotting-only before/after offset, not an event timestep
    """
    end=float(simulation_end)
    if not math.isfinite(end) or end<=0:raise ValueError('Positive finite simulation end required')
    if context_years is not None and (not math.isfinite(context_years) or context_years<=0):
        raise ValueError('Context offset must be positive and finite')
    samples={}
    fractions=tuple(fractions) if fractions is not None else tuple(i/8 for i in range(9))
    if not fractions or any(not 0<=float(v)<=1 for v in fractions):raise ValueError('Fractions must be in [0,1]')
    def add(time,reason):
        value=float(time)
        if not math.isfinite(value):raise ValueError('Time must be finite')
        if 0<=value<=end:
            samples.setdefault(value,set()).add(reason)
    def sample_interval(start,finish,reason):
        a,b=float(start),float(finish)
        if not math.isfinite(a) or not math.isfinite(b) or b<a:
            raise ValueError('Finite ordered interval required')
        for value in fractions:add(a+(b-a)*value,f'{reason}:{value:.6f}')
    overview=[end*i/8 for i in range(9)]
    for t in overview:add(t,'overview')
    ids=set()
    for interval in intervals:
        identity=(interval['kind'],interval['id'])
        if identity in ids:raise ValueError('Duplicate interval identity')
        ids.add(identity)
        a,b=interval['start_year'],interval['natural_end_year']
        sample_interval(a,b,f"{identity[0]}:{identity[1]}:lifecycle")
        for phase in interval.get('phases',[]):
            pa,pb=phase['start_year'],phase['end_year']
            if pa<a or pb>b:raise ValueError('Phase outside its natural lifecycle')
            sample_interval(pa,pb,f"{identity[0]}:{identity[1]}:phase:{phase['name']}")
    ordered=sorted(transitions,key=lambda x:float(x['time_year']))
    transition_times=sorted(set(float(x['time_year']) for x in ordered))
    for change in ordered:
        t=float(change['time_year'])
        reason=f"{change['kind']}:{change['id']}:{change.get('detail','change')}"
        add(t,reason)
        if context_years is not None and 0<=t<=end:
            prior=[v for v in transition_times if v<t]
            following=[v for v in transition_times if v>t]
            before=min(context_years,(t-prior[-1])/3) if prior else context_years
            after=min(context_years,(following[0]-t)/3) if following else context_years
            add(t-before,reason+':before');add(t+after,reason+':after')
    frames=[dict(frame_id=f'frame_{i:05d}',time_year=t,elapsed_Myr=t/1e6,
                 age_Ma_BP=48-t/1e6,reasons=sorted(samples[t]))
            for i,t in enumerate(sorted(samples))]
    lookup={f['time_year']:f['frame_id'] for f in frames}
    pages=[]
    for i in range(0,len(frames),9):
        page=frames[i:i+9]
        pages.append(dict(page=i//9+1,frame_ids=[f['frame_id'] for f in page],empty_panels=9-len(page)))
    return dict(time_origin='elapsed year 0 = 48 Ma BP',simulation_end_year=end,
                context_years=context_years,phase_fractions=fractions,overview_frame_ids=[lookup[t] for t in overview],
                frames=frames,nine_panel_pages=pages)
