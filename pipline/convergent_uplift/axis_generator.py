"""Finite competitive interfaces plus explicit, stochastic graph operations.

The output is an entire geometric axis graph. There is no 500-km crop, U field,
tectonic chronology, category quota or diversity-directed resampling here.
"""
import heapq,math
from collections import defaultdict
import numpy as np
from scipy.spatial import Delaunay,cKDTree
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import LineString,Point,MultiLineString
from common import rng_for
from geometry_metrics import resample,features,long_side,graph_from_edges,validity

DESIGN={
 'mesh_spacing':.015,'initial_domain_halfwidth':2.25,'maximum_domain_expansions':2,
 'smoothing_fraction':[.010,.025],
 'fork_count_lambda':.85,'fork_count_max':3,'loop_count_lambda':.40,'loop_count_max':2,
 'split_count_lambda':.65,'split_count_max':3,
 'fork_length_fraction':[.13,.34],'fork_departure_angle_deg':[28.,76.],
 'split_gap_fraction':[-.035,.045],
 'split_offset_fraction':[.009,.030],'minimum_edge_fraction':.045,
 'minimum_junction_angle_deg':12.,'operation_trials':32,'sample_trials':16,
 'free_tip_clearance_fraction':.018,'nonjunction_clearance_fraction':.008,'junction_exclusion_radius_fraction':.06,
 'sinuosity_excess_margin':3.,'turn_envelope_margin':1.65,
 'basis':'Design distributions and compatibility limits; curvature envelope separately derived from frozen convergent-trace proxies.'}

def make_mesh(seed,halfwidth=2.25):
    h=DESIGN['mesh_spacing'];m=int(np.ceil(halfwidth/h));ii,jj=np.meshgrid(np.arange(-m,m+1),np.arange(-m,m+1))
    # Coordinate-addressed jitter remains identical in an expanded auxiliary domain.
    u=(ii.ravel().astype(np.int64)+100000).astype(np.uint64)*np.uint64(73856093)
    u^=(jj.ravel().astype(np.int64)+100000).astype(np.uint64)*np.uint64(19349663)
    u^=np.uint64(seed)*np.uint64(83492791)
    def hashed(v):
        v=v.copy();v^=v>>np.uint64(30);v*=np.uint64(0xbf58476d1ce4e5b9)
        v^=v>>np.uint64(27);v*=np.uint64(0x94d049bb133111eb);v^=v>>np.uint64(31)
        return (v>>np.uint64(11)).astype(float)/2**53
    xy=np.column_stack([ii.ravel()*h,jj.ravel()*h])
    xy+=(np.column_stack([hashed(u),hashed(u+np.uint64(1234567))])-.5)*.58*h
    triangles=Delaunay(xy).simplices
    es=np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]);es.sort(axis=1);es=np.unique(es,axis=0)
    adj=[[] for _ in xy]
    for a,b in es:
        dx,dy=xy[b]-xy[a];d=float(np.hypot(dx,dy));ux=float(dx/d);uy=float(dy/d)
        adj[a].append((int(b),d,ux,uy));adj[b].append((int(a),d,-ux,-uy))
    boundary=(np.abs(ii.ravel())==m)|(np.abs(jj.ravel())==m)
    return {'xy':xy,'tri':triangles,'adj':adj,'tree':cKDTree(xy),'boundary':boundary,'halfwidth':m*h,'seed':int(seed),'spacing':h}

def field_parameters(r):
    modes=[];group_weights=[float(r.uniform(.05,.85)),float(r.uniform(0,.50)),float(r.uniform(0,.10))]
    # A low-variation draw remains possible; there is no target number of bends.
    if r.uniform()<.15:group_weights=[v*.20 for v in group_weights]
    for (lo,hi,n),weight in zip([(.6,2.6,7),(.18,.65,9),(.07,.18,5)],group_weights):
        for _ in range(n):
            angle=float(r.uniform(-np.pi,np.pi));period=float(np.exp(r.uniform(np.log(lo),np.log(hi))))
            modes.append([2*np.pi*np.cos(angle)/period,2*np.pi*np.sin(angle)/period,float(r.uniform(-np.pi,np.pi)),float(r.normal()*weight/np.sqrt(n))])
    patches=[]
    for _ in range(min(int(r.poisson(1.2)),3)):
        patches.append([float(r.uniform(-.55,.55)),float(r.uniform(-.65,.65)),float(r.uniform(.08,.25)),float(r.normal(0,.45))])
    return {'modes':modes,'patches':patches,'weights':group_weights,'rate':float(r.uniform(.90,1.10)),
      'direction_angle':float(r.uniform(-np.pi,np.pi)),'direction_bias':float(r.uniform(0,.28))}

def cost_field(xy,pars):
    z=np.zeros(len(xy))
    for kx,ky,phase,amp in pars['modes']:z+=amp*np.cos(xy[:,0]*kx+xy[:,1]*ky+phase)
    for x,y,s,amp in pars['patches']:z+=amp*np.exp(-((xy[:,0]-x)**2+(xy[:,1]-y)**2)/(2*s*s))
    return np.exp(.75*np.tanh(z))/pars['rate']

def competitive_labels(mesh,cfg):
    xy=mesh['xy'];labels=np.full(len(xy),-1,dtype=np.int16);best=np.full(len(xy),np.inf);heap=[]
    costs=[cost_field(xy,p) for p in cfg['regions']]
    for j,starts in enumerate(cfg['starts']):
        for i in np.atleast_1d(mesh['tree'].query(starts)[1]):
            i=int(i);best[i]=0.;heapq.heappush(heap,(0.,i,j))
    while heap:
        t,i,j=heapq.heappop(heap)
        if labels[i]>=0 or t>best[i]+1e-10:continue
        if t>cfg['limits'][j]:continue
        labels[i]=j;p=cfg['regions'][j];cx=math.cos(p['direction_angle']);cy=math.sin(p['direction_angle'])
        for nb,d,ux,uy in mesh['adj'][i]:
            if labels[nb]>=0:continue
            factor=math.exp(-p['direction_bias']*(cx*ux+cy*uy))
            nt=t+d*.5*(costs[j][i]+costs[j][nb])*factor
            if nt<=cfg['limits'][j] and nt<best[nb]:
                best[nb]=nt;heapq.heappush(heap,(nt,nb,j))
    return labels

def interface_chains(mesh,labels):
    """Exclude active/exterior outlines; active-active contacts terminate inside the domain."""
    graph=defaultdict(list);positions={}
    for it,vs in enumerate(mesh['tri']):
        labs=labels[vs];active=np.unique(labs[labs>=0])
        if len(active)<2:continue
        ids=[]
        for ia,ib in ((0,1),(1,2),(2,0)):
            a,b=int(vs[ia]),int(vs[ib])
            if labels[a]<0 or labels[b]<0 or labels[a]==labels[b]:continue
            key=('e',min(a,b),max(a,b));positions[key]=(mesh['xy'][a]+mesh['xy'][b])/2;ids.append(key)
        if len(ids)==2:pieces=[ids]
        else:
            center=('j',it,-1);positions[center]=mesh['xy'][vs].mean(axis=0)
            pieces=[(a,center) for a in ids]
        for a,b in pieces:graph[a].append(b);graph[b].append(a)
    seen=set();chains=[]
    def ek(a,b):return tuple(sorted((a,b)))
    def follow(a,b):
        path=[a,b];seen.add(ek(a,b));prev,cur=a,b
        while len(graph[cur])==2:
            nxt=graph[cur][0] if graph[cur][1]==prev else graph[cur][1]
            if ek(cur,nxt) in seen:break
            seen.add(ek(cur,nxt));path.append(nxt);prev,cur=cur,nxt
        return np.array([positions[n] for n in path])
    for a in graph:
        if len(graph[a])==2:continue
        for b in graph[a]:
            if ek(a,b) not in seen:chains.append(follow(a,b))
    # Explicitly retain isolated cycles so exclusion decisions can be logged.
    for a in graph:
        for b in graph[a]:
            if ek(a,b) not in seen:chains.append(follow(a,b))
    return chains

def smooth_curve(p,scale):
    q=resample(p,step=.0025);z=gaussian_filter1d(q,scale/.0025,axis=0,mode='nearest')
    u=np.linspace(0,1,len(z))[:,None];z+=(1-u)*(q[0]-z[0])+u*(q[-1]-z[-1]);z[0]=q[0];z[-1]=q[-1]
    return resample(z,step=.0025)

def finite_curve(r,mesh,reference,trace):
    d=float(r.uniform(.20,.36));starts=[]
    for side in (-1,1):
        n=int(r.integers(1,4));ys=np.sort(r.uniform(-.22,.22,n));xs=side*d/2+r.uniform(-.035,.035,n)
        starts.append(np.column_stack([xs,ys]).tolist())
    cfg={'starts':starts,'regions':[field_parameters(r),field_parameters(r)],
      'limits':[float(r.uniform(.58,.82)),float(r.uniform(.58,.82))],
      'smoothing':float(r.uniform(*DESIGN['smoothing_fraction']))}
    expansions=0
    while True:
        labels=competitive_labels(mesh,cfg)
        if not np.any(labels[mesh['boundary']]>=0):break
        expansions+=1
        if expansions>DESIGN['maximum_domain_expansions']:raise ValueError('finite_domain_exhausted')
        mesh=make_mesh(mesh['seed'],mesh['halfwidth']*1.4)
    candidates=interface_chains(mesh,labels)
    opened=[p for p in candidates if len(p)>=8 and np.linalg.norm(p[-1]-p[0])>.15]
    if not opened:raise ValueError('no_finite_open_interface')
    p=max(opened,key=lambda p:np.linalg.norm(np.diff(p,axis=0),axis=1).sum())
    if p[0,1]>p[-1,1]:p=p[::-1]
    for smoothing_factor in (1.,.7,.4):
        q=smooth_curve(p,cfg['smoothing']*smoothing_factor)
        if not validity([q]):break
    reason=screen([q],reference,check_lengths=False)
    if reason:raise ValueError('base_interface:'+','.join(reason))
    trace.append({'algorithm':'finite_two_region_competition','config':cfg,'mesh_seed':mesh['seed'],
      'auxiliary_halfwidth':mesh['halfwidth'],'domain_expansions':expansions,'active_front_touches_outer_boundary':False,
      'candidate_interface_count':len(candidates),'open_interface_count':len(opened),'selection':'longest finite open connected interface',
      'raw_vertices':len(p),'smoothed_vertices':len(q),'smoothing_factor':smoothing_factor,
      'free_tip_clearance_from_domain':float(mesh['halfwidth']-np.max(np.abs(q)))})
    return q

def screen(edges,reference,check_lengths=True):
    reasons=validity(edges)
    if reasons:return reasons
    L,_=long_side(edges)
    if L<=1e-8:return ['zero_extent']
    q99=reference['groups']['all']
    max_sinu=1+(q99['sinuosity']['p99']-1)*DESIGN['sinuosity_excess_margin']
    for i,p in enumerate(edges):
        f=features(p)
        if check_lengths and f['arc_length']<DESIGN['minimum_edge_fraction']*L:reasons.append(f'edge_below_resolution_design:{i}')
        if f['sinuosity']>max_sinu:reasons.append(f'proxy_sinuosity_envelope:{i}')
        for k in ['turn_08_p95_deg','turn_20_p95_deg']:
            if f[k]>min(175.,q99[k]['p99']*DESIGN['turn_envelope_margin']):reasons.append(f'proxy_turn_envelope:{i}:{k}')
    g=graph_from_edges(edges)
    if any(d>3 for d in g['node_degrees']):reasons.append('junction_degree_above_design')
    # Keep open tips and unconnected passages visibly distinct. These distances
    # are engineering/representation limits, not universal geological thresholds.
    lines=[LineString(p) for p in edges]
    for ni,degree in enumerate(g['node_degrees']):
        if degree!=1:continue
        tip=Point(g['nodes'][ni])
        for ei,ids in enumerate(g['edge_nodes']):
            if ni not in ids and tip.distance(lines[ei])<DESIGN['free_tip_clearance_fraction']*L:
                reasons.append(f'free_tip_ambiguous_contact:{ni}:{ei}')
    for i in range(len(edges)):
        for j in range(i+1,len(edges)):
            shared=set(g['edge_nodes'][i])&set(g['edge_nodes'][j]);a,b=lines[i],lines[j]
            for ni in shared:
                disk=Point(g['nodes'][ni]).buffer(DESIGN['junction_exclusion_radius_fraction']*L)
                a=a.difference(disk);b=b.difference(disk)
            if not a.is_empty and not b.is_empty and a.distance(b)<DESIGN['nonjunction_clearance_fraction']*L:
                reasons.append(f'ambiguous_near_contact:{i}:{j}')
    for ni,degree in enumerate(g['node_degrees']):
        if degree!=3:continue
        vectors=[]
        for p,(a,b) in zip(edges,g['edge_nodes']):
            if ni not in (a,b):continue
            q=p if a==ni else p[::-1];s=np.r_[0,np.linalg.norm(np.diff(q,axis=0),axis=1).cumsum()]
            at=min(.025*L,.25*s[-1]);point=np.array([np.interp(at,s,q[:,j]) for j in range(2)])
            v=point-q[0];vectors.append(v/np.linalg.norm(v))
        for i in range(len(vectors)):
            for j in range(i+1,len(vectors)):
                angle=np.degrees(np.arccos(np.clip(vectors[i]@vectors[j],-1,1)))
                if angle<DESIGN['minimum_junction_angle_deg']:reasons.append(f'unresolved_junction_angle:{ni}')
    return reasons

def at_fraction(p,f):
    s=np.r_[0,np.linalg.norm(np.diff(p,axis=0),axis=1).cumsum()];v=f*s[-1]
    return np.array([np.interp(v,s,p[:,i]) for i in range(2)])

def portion(p,a,b):
    s=np.r_[0,np.linalg.norm(np.diff(p,axis=0),axis=1).cumsum()];L=s[-1]
    middle=p[(s>a*L)&(s<b*L)]
    return np.vstack([at_fraction(p,a),middle,at_fraction(p,b)])

def fork_operation(edges,r,mesh,reference):
    L,_=long_side(edges);lengths=np.array([LineString(p).length for p in edges]);eligible=np.flatnonzero(lengths>.28*L)
    if not len(eligible):raise ValueError('no_edge_long_enough_for_fork')
    index=int(r.choice(eligible,p=lengths[eligible]/lengths[eligible].sum()));p=edges[index];f=float(r.uniform(.24,.76));anchor=at_fraction(p,f)
    tangent=at_fraction(p,min(.99,f+.035))-at_fraction(p,max(.01,f-.035));tangent/=np.linalg.norm(tangent)
    logs=[];q=finite_curve(r,mesh,reference,logs)
    if r.uniform()<.5:q=q[::-1]
    initial=at_fraction(q,.07)-q[0];a=np.arctan2(initial[1],initial[0])
    sign=-1 if r.uniform()<.5 else 1;angle=float(r.uniform(*DESIGN['fork_departure_angle_deg']))
    if r.uniform()<.25:tangent=-tangent
    desired=np.arctan2(tangent[1],tangent[0])+sign*np.radians(angle);theta=desired-a
    rot=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
    target=float(r.uniform(*DESIGN['fork_length_fraction']))*L
    q=(q-q[0])@rot.T*(target/LineString(q).length)+anchor;q[0]=anchor
    left=portion(p,0,f);right=portion(p,f,1);left[-1]=anchor;right[0]=anchor
    result=edges[:index]+[left,right,q]+edges[index+1:]
    reasons=screen(result,reference)
    if reasons:raise ValueError(','.join(reasons))
    before=graph_from_edges(edges);after=graph_from_edges(result)
    if after['components']!=before['components'] or after['junctions']!=before['junctions']+1 or after['cycles']!=before['cycles']:
        raise ValueError('fork_topology_mismatch')
    return result,{'operation':'fork','parent_edge':index,'anchor_fraction':f,'departure_angle_design_deg':angle,
       'branch_arc_length_raw':target,'curve_source':logs,'transform':'similarity transform of another finite competitive interface, shared-node attachment'}

def loop_operation(edges,r,mesh,reference):
    L,_=long_side(edges);lengths=np.array([LineString(p).length for p in edges]);eligible=np.flatnonzero(lengths>.48*L)
    if not len(eligible):raise ValueError('no_edge_long_enough_for_rejoin')
    index=int(r.choice(eligible,p=lengths[eligible]/lengths[eligible].sum()));p=edges[index]
    span=float(r.uniform(.24,.52));a=float(r.uniform(.15,.85-span));b=a+span;start=at_fraction(p,a);end=at_fraction(p,b)
    chord=end-start;distance=float(np.linalg.norm(chord))
    if distance<.12*L:raise ValueError('rejoin_span_too_short')
    logs=[];q=finite_curve(r,mesh,reference,logs)
    if r.uniform()<.5:q=q[::-1]
    source_chord=q[-1]-q[0];theta=np.arctan2(chord[1],chord[0])-np.arctan2(source_chord[1],source_chord[0])
    rot=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
    q=(q-q[0])@rot.T*(distance/np.linalg.norm(source_chord))+start;q[0]=start;q[-1]=end
    # Reflecting a sampled curve is a symmetric design choice; it preserves its geometry.
    if r.uniform()<.5:
        unit=chord/distance;rel=q-start;parallel=np.outer(rel@unit,unit);q=start+2*parallel-rel;q[0]=start;q[-1]=end
    first=portion(p,0,a);middle=portion(p,a,b);last=portion(p,b,1)
    first[-1]=start;middle[0]=start;middle[-1]=end;last[0]=end
    result=edges[:index]+[first,middle,q,last]+edges[index+1:]
    reasons=screen(result,reference)
    if reasons:raise ValueError(','.join(reasons))
    before=graph_from_edges(edges);after=graph_from_edges(result)
    if after['components']!=before['components'] or after['junctions']!=before['junctions']+2 or after['cycles']!=before['cycles']+1:
        raise ValueError('rejoin_topology_mismatch')
    separation=LineString(q).hausdorff_distance(LineString(middle))
    if separation<.014*L or separation>.30*L:raise ValueError('rejoin_separation_design_range')
    return result,{'operation':'split_rejoin','parent_edge':index,'start_fraction':a,'end_fraction':b,
       'separation_raw':separation,'curve_source':logs,'transform':'endpoint-preserving similarity transform of finite competitive interface; shared-node parallel path'}

def is_bridge(edges,index):
    g=graph_from_edges(edges);pairs=g['edge_nodes'];a,b=pairs[index];adj=[set() for _ in g['nodes']]
    for i,(u,v) in enumerate(pairs):
        if i!=index:adj[u].add(v);adj[v].add(u)
    seen={a};stack=[a]
    while stack:
        for v in adj[stack.pop()]:
            if v not in seen:seen.add(v);stack.append(v)
    return b not in seen

def smoothstep(a):
    a=np.clip(a,0,1);return a*a*(3-2*a)

def split_operation(edges,r,mesh,reference):
    L,_=long_side(edges);lengths=np.array([LineString(p).length for p in edges]);g=graph_from_edges(edges)
    eligible=[i for i,v in enumerate(lengths) if v>.32*L and is_bridge(edges,i)]
    if not eligible:raise ValueError('no_bridge_long_enough_for_split')
    index=int(r.choice(eligible));p=edges[index];center=float(r.uniform(.28,.72));gap=float(r.uniform(*DESIGN['split_gap_fraction']))*L
    a=center-gap/(2*lengths[index]);b=center+gap/(2*lengths[index]);first=portion(p,0,a);second=portion(p,b,1)
    off=float(r.uniform(*DESIGN['split_offset_fraction']))*L;sign=-1 if r.uniform()<.5 else 1
    offsets=[-sign*off*float(r.uniform(.4,1.)),sign*off*float(r.uniform(.4,1.))]
    shifted=[]
    for j,(q,amount) in enumerate(zip([first,second],offsets)):
        q=resample(q,step=.0025);d=np.gradient(q,axis=0);d/=np.linalg.norm(d,axis=1)[:,None];normal=np.column_stack([-d[:,1],d[:,0]])
        u=np.linspace(0,1,len(q));weight=np.ones(len(q))
        if j==0 and g['node_degrees'][g['edge_nodes'][index][0]]>1:weight*=smoothstep(u/.35)
        if j==1 and g['node_degrees'][g['edge_nodes'][index][1]]>1:weight*=smoothstep((1-u)/.35)
        drift=float(r.uniform(-.2,.2))*amount*(2*u-1);q=q+normal*((amount+drift)*weight)[:,None]
        if j==0 and weight[0]==0:q[0]=p[0]
        if j==1 and weight[-1]==0:q[-1]=p[-1]
        shifted.append(q)
    result=edges[:index]+shifted+edges[index+1:];reasons=screen(result,reference)
    if reasons:raise ValueError(','.join(reasons))
    after=graph_from_edges(result)
    if after['components']!=g['components']+1 or after['junctions']!=g['junctions'] or after['cycles']!=g['cycles']:
        raise ValueError('split_topology_mismatch')
    return result,{'operation':'offset_split','parent_edge':index,'center_fraction':center,'along_gap_raw':gap,
      'normal_offsets_raw':offsets,'minimum_separation_raw':float(LineString(shifted[0]).distance(LineString(shifted[1])))}

def poisson_truncated(r,lam,maximum):
    # Rejection implements the specified distribution conditioned on the design cap.
    while True:
        n=int(r.poisson(lam))
        if n<=maximum:return n

def generate(seed,target_long_km,reference):
    meshseed=int(rng_for(seed,201).integers(1,100000000));mesh=make_mesh(meshseed)
    failures=[]
    for attempt in range(DESIGN['sample_trials']):
        r=rng_for(seed,202,attempt)
        plan={k:poisson_truncated(r,DESIGN[k+'_count_lambda'],DESIGN[k+'_count_max']) for k in ['fork','loop','split']}
        trace=[];operations=[];op_rejections=[]
        try:
            root=finite_curve(r,mesh,reference,trace);edges=[root]
            # Connection edits precede gaps so declared junctions and loops can be retained.
            order=['loop']*plan['loop']+['fork']*plan['fork'];r.shuffle(order);order+=['split']*plan['split']
            for opname in order:
                success=False
                for trial in range(DESIGN['operation_trials']):
                    try:
                        fn={'fork':fork_operation,'loop':loop_operation,'split':split_operation}[opname]
                        result,record=fn(edges,r,mesh,reference);edges=result;operations.append({**record,'trial':trial});success=True;break
                    except ValueError as e:op_rejections.append({'operation':opname,'trial':trial,'reason':str(e)})
                if not success:raise ValueError('operation_layout_trials_exhausted:'+opname)
            reason=screen(edges,reference)
            if reason:raise ValueError(','.join(reason))
            raw_L,raw_short=long_side(edges);scale=target_long_km/raw_L
            allpts=np.vstack(edges);origin=(allpts.min(axis=0)+allpts.max(axis=0))/2
            # One isotropic conversion establishes the sampled physical long-side scale.
            # Preserve source vertices: further resampling could omit an extremal
            # vertex and subtly alter the sampled minimum-rectangle long side.
            physical=[(p-origin)*scale for p in edges]
            g=graph_from_edges(physical,tol=1e-6);actual_L,short=long_side(physical)
            if abs(actual_L-target_long_km)>max(1e-6,target_long_km*1e-10):raise ValueError('scale_mapping_error')
            return {'seed':int(seed),'attempt':attempt,'target_long_km':float(target_long_km),'actual_long_km':actual_L,
              'rectangle_short_km':short,'total_arc_length_km':float(sum(LineString(p).length for p in physical)),
              'edges':[p.tolist() for p in physical],'graph':g,'structure_plan':plan,'operation_order':order,
              'operations':operations,'competition_sources':trace,'operation_rejections':op_rejections,'prior_attempts':failures,
              'normalization':{'raw_long_side':raw_L,'isotropic_km_per_algorithm_unit':scale,'raw_origin':origin.tolist()},
              'endpoint_kind':['generated_free_tip' if d==1 else 'explicit_junction' for d in g['node_degrees']],
              'complete_geometry':True,'cropped_to_500_km':False,'units':'km','coordinate_system':'local_cartesian',
              'geometry_features':[features(p) for p in physical],'geology_rule_state':'passed versioned proxy and design checks; visual/geological acceptance remains a separate judgement'}
        except ValueError as e:
            failures.append({'attempt':attempt,'structure_plan':plan,'reason':str(e),'operation_rejections':op_rejections,'competition_sources':trace})
    raise RuntimeError(f'No admissible complete axis for seed {seed}; attempts={failures}')
