"""Whole-region fitting on the exact outer coastline, then graph extension."""
import heapq
import warnings
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy import sparse
from coast import circular_runs, lengths_on_coast
from scipy.stats import wasserstein_distance


def fit_coast_regions(coast, target, share, n_regions, time_limit=30.):
    owners=coast.sea_regions
    ids=np.unique(owners); lookup={int(k):i for i,k in enumerate(ids)}
    local=np.array([lookup[int(i)] for i in owners]); n=len(ids); p=len(owners)
    if share in (0.,1.):
        return np.full(n_regions,bool(share)),dict(status='uniform type',objective=0.,coast_region_ids=ids.tolist())
    if n<2:raise ValueError('Mixed target requires at least two whole coastal regions')
    # Equal-run and length-weighted disagreement prevent short targets being invisible.
    edge_weights=np.zeros(p)
    target_run_count=sum(len(circular_runs(target[sl])) for sl in coast.ring_slices)
    for sl in coast.ring_slices:
        for r in circular_runs(target[sl]):
            positions=sl.start+(np.arange(r['count'])+r['start'])%(sl.stop-sl.start)
            edge_weights[positions]=.5/p+.5/(target_run_count*r['count'])
    mismatch=np.bincount(local,weights=edge_weights*np.where(target,-1.,1.),minlength=n)
    contact=np.bincount(local,minlength=n)/p
    transitions={}
    for sl in coast.ring_slices:
        li=local[sl];ti=target[sl]
        for a,c,u,v in zip(li,np.roll(li,-1),ti,np.roll(ti,-1)):
            if a==c:continue
            key=tuple(sorted((int(a),int(c))))
            transitions[key]=transitions.get(key,0)+(1 if u==v else -1)
    pairs=list(transitions); k=len(pairs)
    objective=np.r_[mismatch,5.,np.array([transitions[t] for t in pairs])*.20/max(1,sum(abs(v) for v in transitions.values()))]
    nv=n+1+k; rr=[];cc=[];vv=[];lower=[];upper=[]
    def constraint(values,lo=-np.inf,hi=np.inf):
        row=len(lower)
        for col,value in values.items():rr.append(row);cc.append(col);vv.append(value)
        lower.append(lo);upper.append(hi)
    constraint({**{i:float(x) for i,x in enumerate(contact)},n:-1.},hi=share)
    constraint({**{i:-float(x) for i,x in enumerate(contact)},n:-1.},hi=-share)
    constraint({i:1. for i in range(n)},lo=1,hi=n-1)
    for j,(a,c) in enumerate(pairs):
        y=n+1+j
        constraint({a:1,c:-1,y:-1},hi=0)
        constraint({a:-1,c:1,y:-1},hi=0)
        constraint({y:1,a:-1,c:-1},hi=0)
        constraint({y:1,a:1,c:1},hi=2)
    matrix=sparse.csc_array((np.array(vv,float),(np.array(rr,np.int32),np.array(cc,np.int32))),shape=(len(lower),nv))
    integrality=np.ones(nv);integrality[n]=0
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message='Unrecognized options detected.*',category=RuntimeWarning)
        result=milp(objective,integrality=integrality,bounds=Bounds(np.zeros(nv),np.ones(nv)),
                    constraints=LinearConstraint(matrix,np.asarray(lower),np.asarray(upper)),
                    options={'time_limit':time_limit,'mip_rel_gap':1e-6,'threads':1,'parallel':False})
    if result.x is None:raise RuntimeError(f'Whole-region optimizer returned no feasible state: {result.message}')
    state=np.zeros(n_regions,bool);state[ids]=result.x[:n]>.5
    actual=state[owners]
    info=dict(status=int(result.status),message=str(result.message),optimal=bool(result.success),
              objective=float(result.fun),mip_gap=float(result.mip_gap),coast_region_ids=ids.tolist(),
              objective_weights=dict(coast_pattern=1.,fraction_absolute_error=5.,transition_disagreement=.20),
              target_fraction=float(share),actual_fraction=float(actual.mean()),
              coast_disagreement_fraction=float(np.mean(actual!=target)),
              maximum_region_coast_fraction=float(contact.max()),
              definition='binary variables choose complete sea partitions; continuous auxiliary measures absolute ratio error')
    return state,info


def fit_arrangement(sample, target, target_info):
    """Fit the placement of one generated sequence, without redrawing its values.

Thirty-two equally spaced rotations start from the sampled random phase.
Each candidate uses whole-region optimization. The reported score balances
relative share error, run-length distribution error, and run-count error.
These weights and this finite placement search are engineering choices.
"""
    coast=sample['coast']; q=target_info['deep_fraction_target']; p=len(target)
    count=32 if target_info['regime']=='mixed' else 1
    candidates=[];best=None
    for k in range(count):
        shift=int(k*p/count); wanted=np.roll(target,shift)
        state,info=fit_coast_regions(coast,wanted,q,len(sample['geometry'].areas))
        actual,rows=lengths_on_coast(coast,state)
        wanted_rows=[]
        for sl in coast.ring_slices:wanted_rows.extend(circular_runs(wanted[sl]))
        share_error=abs(float(actual.mean())-q)
        length_errors=[];count_errors=[]
        for typ,code in (('deep',1),('shallow',0)):
            a=[r['count'] for r in wanted_rows if r['label']==code]
            z=[r['length_km'] for r in rows if r['environment']==typ]
            length_errors.append(float(wasserstein_distance(a,z)/np.mean(a)) if a and z else float(bool(a or z)))
            count_errors.append(abs(len(a)-len(z))/max(1,len(a)))
        relative_share=.5*(share_error/q+share_error/(1-q)) if 0<q<1 else share_error
        score=relative_share+.25*sum(length_errors)+.25*sum(count_errors)
        row=dict(candidate=k,shift_km=shift,score=score,ratio_error_pp=100*share_error,
                 relative_share_error=relative_share,relative_length_errors=length_errors,
                 relative_count_errors=count_errors,optimizer_status=info['status'])
        candidates.append(row)
        if best is None or score<best[0]:best=(score,wanted,state,info,row)
    _,wanted,state,info,choice=best
    target_info['placement']=dict(candidate_count=count,selected_candidate=choice['candidate'],
        shift_km=choice['shift_km'],candidates=candidates,
        rule='equally spaced circular rotations of the same generated sequence; no redraw of type, share, or lengths',
        score='mean relative deep/shallow share error + 0.25 * summed relative Wasserstein length errors + 0.25 * summed relative run-count errors',
        status='finite placement search; optimum among evaluated placements, no global optimum claim')
    info['placement_score']=choice['score']
    return wanted,state,info


def extend_by_graph(g,platform,coast,coast_deep):
    """Nearest coastal seed in the sea-region adjacency graph; no pixel edits.

Region-centroid distances are edge costs. Unseeded sea components (e.g. internal
holes) are assigned shallow as an explicit initial classification assumption;
they remain separate from the outer-coast ratio/length fit.
"""
    n=len(g.areas);centers=np.column_stack([g.mx/g.areas,g.my/g.areas])*g.size
    dist=np.full(n,np.inf);source=np.full(n,-1,int);queue=[]
    for i in np.unique(coast.sea_regions):
        dist[i]=0.;source[i]=int(i);heapq.heappush(queue,(0.,int(i),int(i)))
    while queue:
        d,root,i=heapq.heappop(queue)
        if d>dist[i]+1e-10 or root!=source[i]:continue
        for j,_ in g.neighbors[i]:
            if platform[j]:continue
            nd=d+float(np.linalg.norm(centers[i]-centers[j]))
            if nd<dist[j]-1e-10 or (abs(nd-dist[j])<=1e-10 and root<source[j]):
                dist[j]=nd;source[j]=root;heapq.heappush(queue,(nd,root,j))
    labels=np.ones(n,np.uint8);known=source>=0
    labels[known]=np.where(coast_deep[source[known]],2,1)
    labels[platform]=0
    unseeded=(~platform)&(~known)
    return labels,dict(unseeded_shallow_region_ids=np.flatnonzero(unseeded).tolist(),
                       unseeded_shallow_area_km2=float(g.areas[unseeded].sum()*g.size**2),
                       rule='shortest centroid-distance path over unselected shared-edge partitions',
                       internal_assignment='shallow label, engineering assumption; not included in perimeter fitting')


def allocate(sample, target, target_info):
    coast=sample['coast'];g=sample['geometry']
    target,state,optimization=fit_arrangement(sample,target,target_info)
    types,extension=extend_by_graph(g,sample['platform_state'],coast,state)
    field=types[sample['labels']-1]
    actual,segments=lengths_on_coast(coast,types==2)
    metrics=dict(seed=sample['seed'],regime=target_info['regime'],platform_fraction=float(sample['mask'].mean()),
        target_deep_coast_fraction=target_info['deep_fraction_target'],actual_deep_coast_fraction=float(actual.mean()),
        ratio_error_pp=100.*abs(float(actual.mean())-target_info['deep_fraction_target']),
        outer_coast_km=len(target),deep_region_count=int((types==2).sum()),shallow_region_count=int((types==1).sum()),
        deep_seafloor_area_km2=int((field==2).sum()),shallow_seafloor_area_km2=int((field==1).sum()),
        partition_count=len(types),whole_regions_preserved=True,optimization=optimization,extension=extension)
    target_segments=[]
    for rid,sl in enumerate(coast.ring_slices):
        for r in circular_runs(target[sl]):
            target_segments.append(dict(ring_id=rid,start_km=r['start'],length_km=r['count'],environment='deep' if r['label'] else 'shallow'))
    # Run lengths are checked both as paired arc targets and as unordered length distributions.
    for typ in ('deep','shallow'):
        wanted=[r['length_km'] for r in target_segments if r['environment']==typ]
        found=[r['length_km'] for r in segments if r['environment']==typ]
        metrics[typ+'_segments']=dict(target_count=len(wanted),actual_count=len(found),
            target_lengths_km=wanted,actual_lengths_km=found,
            wasserstein_error_km=float(wasserstein_distance(wanted,found)) if wanted and found else None,
            target_mean_km=float(np.mean(wanted)) if wanted else None,actual_mean_km=float(np.mean(found)) if found else None)
    return target,field,types,actual,target_segments,segments,metrics
