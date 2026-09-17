"""Spatially correlated event clocks and continuous, mean-one time variability."""
import math
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.ndimage import map_coordinates, distance_transform_edt
from timing import envelope
from tcontext import *

def rescale(values):
    a=float(np.min(values));b=float(np.max(values))
    return (values-a)/max(b-a,1e-12)

def static_random(points, random, scale, modes=32):
    omega=random.normal(size=(2,modes))/scale
    aa=random.normal(size=modes);bb=random.normal(size=modes);out=np.empty(len(points))
    for i in range(0,len(points),40000):
        phase=points[i:i+40000]@omega
        out[i:i+40000]=(np.cos(phase)@aa+np.sin(phase)@bb)/np.sqrt(modes)
    return out

def axis_network(axis, step):
    nodes=[];lookup={};links=[]
    for xy in axis['edges']:
        xy=np.asarray(xy);s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
        ss=np.linspace(0,s[-1],max(2,int(np.ceil(s[-1]/step))+1))
        pp=np.column_stack([np.interp(ss,s,xy[:,j]) for j in range(2)]);ids=[]
        for q in pp:
            key=tuple(np.round(q,7))
            if key not in lookup:lookup[key]=len(nodes);nodes.append(q)
            ids.append(lookup[key])
        for a,b in zip(ids[:-1],ids[1:]):
            if a!=b:links.append((a,b))
    return np.array(nodes),links

def make_clocks(seed,event_index,full,axis,design):
    random=rng(seed,100+100*event_index);xx,yy=np.meshgrid(full['x_km'],full['y_km'])
    support=full['support'];points=np.column_stack([xx[support],yy[support]])
    nodes,links=axis_network(axis,design['axis_step_km']);span=axis['target_long_km']
    speed=np.exp(.3*static_random(nodes,random,max(30.,span*.15)))
    ii=[];jj=[];ww=[]
    for a,b in links:
        cost=np.linalg.norm(nodes[a]-nodes[b])/np.sqrt(speed[a]*speed[b])
        ii.extend((a,b));jj.extend((b,a));ww.extend((cost,cost))
    graph=coo_matrix((ww,(ii,jj)),shape=(len(nodes),len(nodes))).tocsr()
    ncomp,labels=connected_components(graph);origins=[]
    for c in range(ncomp):
        ids=np.flatnonzero(labels==c);length=len(ids)*design['axis_step_km']
        count=min(len(ids),1+int(random.poisson(length*design['additional_origins_per_axis_km'])))
        origins.extend(random.choice(ids,count,replace=False).tolist())
    arrival=dijkstra(graph,indices=origins,min_only=True)
    if not np.all(np.isfinite(arrival)):raise ValueError('Unseeded axis component')
    tree=cKDTree(nodes);k=min(8,len(nodes));dd,nn=tree.query(points,k=k,workers=1)
    if k==1:dd=dd[:,None];nn=nn[:,None]
    sigma=5.+.4*dd[:,0];weights=np.exp(-.5*(dd/sigma[:,None])**2);weights/=weights.sum(axis=1)[:,None]
    # Graph travel establishes along-belt growth; transverse distance delays the flanks/caps.
    raw=np.sum(weights*arrival[nn],axis=1)+2.*dd[:,0]
    grid=np.linspace(0,1,1025);knots=np.quantile(raw,grid)
    empirical=np.array(load(MODELS/'onset_delay.json')['normalized_delays'])
    q=np.interp(raw,knots,grid);shape=np.quantile(empirical,q)
    onset=rescale(shape)*design['growth_last_onset_fraction']
    retreat=rescale(.45*rescale(raw)+.55*rescale(static_random(points,random,max(30.,span*.2))))
    # Fill unused cells by nearest support clock so bilinear evaluation has a continuous extension.
    nearest=distance_transform_edt(~support,return_distances=False,return_indices=True)
    fields={}
    for key,value in [('onset',onset),('retreat',retreat)]:
        a=np.zeros(support.shape,dtype=np.float32);a[support]=value.astype(np.float32)
        a[~support]=a[tuple(nearest[:,~support])];fields[key]=a
    center=nodes.mean(axis=0);_,_,vt=np.linalg.svd(nodes-center,full_matrices=False)
    m=int(design['fluctuation_modes']);omega=np.column_stack([
        random.normal(size=m)/design['fluctuation_along_correlation_km'],
        random.normal(size=m)/design['fluctuation_across_correlation_km']])@vt
    omega_t=random.normal(size=m)/design['fluctuation_time_correlation_Myr']
    params=dict(seed=seed,event_index=event_index,origins_km=nodes[origins].tolist(),axis_components=int(ncomp),
        origin_count=len(origins),axis_nodes=len(nodes),axis_sample_step_km=design['axis_step_km'],
        noise=dict(omega_xy=omega.tolist(),omega_t=omega_t.tolist(),a=random.normal(size=m).tolist(),
                   b=random.normal(size=m).tolist(),sigma_log=float(np.sqrt(np.log1p(design['fluctuation_cv']**2))),
                   expected_mean_multiplier=1.,target_cv=design['fluctuation_cv'],rotation=vt.tolist()),
        geometry_method='Shortest paths on the connected auxiliary graph; smoothly weighted nearest graph samples plus transverse-distance delay.',
        component_rule='At least one random origin per disconnected axis component; original zero support never bridged.',
        temporal_randomness='Frozen Gaussian Fourier coefficients and frequencies; no redraw by timestep or geological epoch.')
    return fields,params

class Evaluator:
    """Rates for one event at fixed physical positions. Units: km, Myr, m/yr."""
    def __init__(self,points,reference,onset,retreat,event,noise,cache_basis=True):
        self.points=np.asarray(points);self.reference=np.asarray(reference);self.onset=np.asarray(onset)
        self.retreat=np.asarray(retreat);self.event=event;self.noise=noise;self.C=None;self.S=None
        self.omega=np.asarray(noise['omega_xy']);self.wt=np.asarray(noise['omega_t'])
        self.aa=np.asarray(noise['a']);self.bb=np.asarray(noise['b']);self.m=len(self.wt)
        if cache_basis:
            self.C=np.empty((len(points),self.m),dtype=np.float32);self.S=np.empty_like(self.C)
            for start in range(0,len(points),30000):
                phase=self.points[start:start+30000]@self.omega.T;c=np.cos(phase);s=np.sin(phase)
                self.C[start:start+30000]=(c*self.aa+s*self.bb)/np.sqrt(self.m)
                self.S[start:start+30000]=(-s*self.aa+c*self.bb)/np.sqrt(self.m)

    def multiplier(self,t,cv=None):
        tau=t-self.event['start_sim_Myr'];ct=np.cos(self.wt*tau);st=np.sin(self.wt*tau)
        if self.C is not None:z=self.C@ct+self.S@st
        else:
            z=np.empty(len(self.points))
            for i in range(0,len(z),30000):
                phase=self.points[i:i+30000]@self.omega.T+tau*self.wt
                z[i:i+30000]=(np.cos(phase)@self.aa+np.sin(phase)@self.bb)/np.sqrt(self.m)
        sigma=self.noise['sigma_log'] if cv is None else np.sqrt(np.log1p(cv**2))
        return np.exp(sigma*z-.5*sigma*sigma)

    def rate(self,t,cv=None):
        a=envelope(t,self.event,self.onset,self.retreat)
        if not np.any(a):return np.zeros_like(self.reference,dtype=float)
        return self.reference*a*self.multiplier(t,cv)

    def displacement(self,start,end,max_step_Myr=.1,cv=None):
        """8-point Gauss quadrature; max_step controls convergence independently of LEM dt."""
        if end<start:raise ValueError('Reversed integration bounds')
        if max_step_Myr<=0:raise ValueError('Integration step must be positive')
        lo=max(start,self.event['start_sim_Myr']);hi=min(end,self.event['natural_end_sim_Myr'])
        out=np.zeros_like(self.reference,dtype=float)
        if hi<=lo:return out
        bounds=sorted(set([lo,hi]+[v for v in (self.event['rise_end_sim_Myr'],self.event['hold_end_sim_Myr']) if lo<v<hi]))
        nodes,weights=np.polynomial.legendre.leggauss(8)
        for a,b in zip(bounds[:-1],bounds[1:]):
            knots=np.linspace(a,b,max(1,int(np.ceil((b-a)/max_step_Myr)))+1)
            for c,d in zip(knots[:-1],knots[1:]):
                for q,w in zip(nodes,weights):out+=self.rate((c+d)/2+(d-c)*q/2,cv)*w*(d-c)/2*1e6
        return out

def clock_values(points,full,clocks):
    x=full['x_km'];y=full['y_km'];coords=np.vstack([(points[:,1]-y[0])/(y[1]-y[0]),(points[:,0]-x[0])/(x[1]-x[0])])
    return [map_coordinates(clocks[k],coords,order=1,mode='nearest',prefilter=False) for k in ('onset','retreat')]

def crop_points(selection):
    x,y=np.meshgrid(np.arange(500)+.5,np.arange(500)+.5);local=np.column_stack([x.ravel(),y.ravel()])
    R=np.asarray(selection['rotation_matrix']);center=np.asarray(selection['center_source_km'])
    return (local-250)@R.T+center
