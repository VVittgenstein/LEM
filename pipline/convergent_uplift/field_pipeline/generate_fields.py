"""Complete physical-scale fields, without a 500-km crop or sample quotas."""
import sys,time
from pathlib import Path
import numpy as np
from scipy import stats, special
from scipy.spatial import cKDTree, ConvexHull
from scipy.ndimage import binary_erosion
import shapely
from shapely.geometry import MultiPoint
from context import *
from stat_models import ppf, compact_profile
sys.path.insert(0,str(AXIS_ROOT))
from axis_generator import generate as generate_axis
from scale_model import sample as sample_scale

DESIGN={'grid_dx_km':1.,'axis_parameter_step_km':1.,'fourier_modes':384,
 'minimum_resolved_length_km':5.,'tail_cutoff_fraction':.25,'center_rounding_fraction':.02,
 'parameter_extension_sigma_km':4.,'parameter_extension_neighbors':96,'off_axis_smoothing_fraction':.3,'side_blend_km':1.,
 'calibration_target_relative_tolerance':.015,'calibration_grid_cells_across':360,
 'calibration_scale_limits':[.08,6.],'final_width_tolerance':.06,
 'overlap_rule':'maximum of component fields; continuous-value envelope, gradient seams permitted',
 'mirror_rule':'one Bernoulli(0.5) mirror for the complete realization, independent of location',
 'spatial_mapping':'stationary isotropic latent fields evaluated on physical axis coordinates; fitted DS5 lags in km',
 'scope':'all parameters fixed before the formal eight seeds; no shape quota or visual selection'}

class RandomFunction:
    def __init__(self,seed,stream,length):
        r=rng(seed,stream);m=DESIGN['fourier_modes'];self.k=r.normal(size=(m,2))/length
        self.a=r.normal(size=m)/np.sqrt(m);self.b=r.normal(size=m)/np.sqrt(m)
    def __call__(self,xy):
        result=[]
        for start in range(0,len(xy),3000):
            theta=xy[start:start+3000]@self.k.T;result.extend(np.cos(theta)@self.a+np.sin(theta)@self.b)
        return np.asarray(result)

def draw_width(seed,L,model):
    r=rng(seed,701);centers=np.array(model['centers']);cov=np.array(model['covariance'])*model['bandwidth']**2
    dx=np.log(L)-centers[:,0];logw=-.5*dx**2/cov[0,0];prob=np.exp(logw-special.logsumexp(logw))
    i=int(r.choice(len(centers),p=prob));mean=centers[i,1]+cov[1,0]/cov[0,0]*dx[i]
    sd=np.sqrt(cov[1,1]-cov[1,0]**2/cov[0,0]);z=float(r.normal());value=float(np.exp(mean+sd*z))
    return value,{'value_km':value,'component':i,'component_probabilities':prob.tolist(),'normal_draw':z,'conditional_log_mean':float(mean),'conditional_log_sd':float(sd)}

def resample(p,step=1.):
    p=np.asarray(p);s=np.r_[0,np.linalg.norm(np.diff(p,axis=0),axis=1).cumsum()]
    at=np.linspace(0,s[-1],max(3,int(np.ceil(s[-1]/step))+1))
    return np.column_stack([np.interp(at,s,p[:,j]) for j in range(2)]),at

def half_location(p,family):
    lo=np.zeros_like(p);hi=np.ones_like(p)
    for _ in range(32):
        mid=(lo+hi)/2;value=compact_profile(mid,p,family,DESIGN['tail_cutoff_fraction'])
        lo=np.where(value>.5,mid,lo);hi=np.where(value>.5,hi,mid)
    return (lo+hi)/2

def axis_parameters(record,ds,gm):
    seed=record['seed'];L=record['target_long_km'];W,draw=draw_width(seed,L,gm['width_scale'])
    peak_noise=RandomFunction(seed,711,max(5.,ds['peak_correlation']['length']))
    width_noise=RandomFunction(seed,712,max(5.,L*gm['relative_width_correlation']['length']))
    joint_length=max(5.,ds['joint_shape_ratio_spatial_correlation']['length'])
    joint_noise=[RandomFunction(seed,720+j,joint_length) for j in range(3)]
    chol=np.linalg.cholesky(np.array(ds['ratio_shape_joint_correlation']));mirror=bool(rng(seed,730).integers(2))
    cap_q=rng(seed,731);edges=[];family=ds['decay_family']
    for i,p in enumerate(record['edges']):
        xy,s=resample(p);z=peak_noise(xy);u=ppf(stats.norm.cdf(z),ds['peak_distribution'])
        relative=ppf(stats.norm.cdf(width_noise(xy)),gm['relative_width_distribution'])
        jz=np.column_stack([f(xy) for f in joint_noise])@chol.T;q=stats.norm.cdf(jz)
        rr=ds['ratio_distribution'];ratio=stats.beta.ppf(np.clip(q[:,0],1e-7,1-1e-7),rr['alpha'],rr['beta'])
        p1=ppf(q[:,1],ds['flank_shape_distributions']['nw']);p2=ppf(q[:,2],ds['flank_shape_distributions']['se'])
        h1=half_location(p1,family);h2=half_location(p2,family)
        # Preserve the DS5 half-height asymmetry when finite support differs by shape.
        support_ratio=(ratio/h1)/(ratio/h1+(1-ratio)/h2)
        if mirror:support_ratio=1-support_ratio;p1,p2=p2,p1;ratio=1-ratio
        total=W*relative
        capratio=ppf(cap_q.random(2),gm['cap_ratio_distribution'])
        caps=capratio*total[[0,-1]]
        a,b=record['graph']['edge_nodes'][i]
        # A shared node's small round closure is an overlap collar, not a free tip.
        for eidx,node in enumerate((a,b)):
            if record['graph']['node_degrees'][node]>1:caps[eidx]=min(total[0 if eidx==0 else -1]*.25,caps[eidx])
        edges.append({'edge_id':i,'xy':xy,'s':s,'peak':u,'left':total*support_ratio,'right':total*(1-support_ratio),
                      'shape_left':p1,'shape_right':p2,'half_ratio':ratio,'caps':caps})
    return edges,{'width_draw':draw,'mirror':mirror,'joint_length_km':joint_length,
                  'width_length_km':max(5.,L*gm['relative_width_correlation']['length']),
                  'peak_length_km':max(5.,ds['peak_correlation']['length'])}

def bounds(edges,scale=1.):
    lo=np.array([np.inf,np.inf]);hi=-lo
    for e in edges:
        margin=scale*max(e['left'].max(),e['right'].max(),e['caps'].max())
        lo=np.minimum(lo,e['xy'].min(axis=0)-margin);hi=np.maximum(hi,e['xy'].max(axis=0)+margin)
    return lo,hi

def projected_values(e,points):
    """Nearest polyline projection with exact adjacent-segment refinement."""
    xy=e['xy'];tree=e.setdefault('_tree',cKDTree(xy));dist,neighbors=tree.query(points,k=min(DESIGN['parameter_extension_neighbors'],len(xy)),workers=1)
    idx=neighbors[:,0]
    best=np.full(len(points),np.inf);best_j=np.zeros(len(points),int);best_t=np.zeros(len(points));best_q=np.zeros_like(points)
    for offset in (-1,0):
        j=np.clip(idx+offset,0,len(xy)-2);a=xy[j];v=xy[j+1]-a
        t=np.clip(np.sum((points-a)*v,axis=1)/np.sum(v*v,axis=1),0,1);q=a+t[:,None]*v
        d2=np.sum((points-q)**2,axis=1);take=d2<best
        best[take]=d2[take];best_j[take]=j[take];best_t[take]=t[take];best_q[take]=q[take]
    j=best_j;t=best_t;v=xy[j+1]-xy[j];v/=np.linalg.norm(v,axis=1)[:,None];delta=points-best_q
    normal=v[:,0]*delta[:,1]-v[:,1]*delta[:,0]
    # Smooth partition of unity over neighboring axis samples avoids abrupt
    # parameter switches at a nearest-projection medial axis. Four km matches
    # the reference's along-profile averaging scale. Arrays remain unchanged.
    dd=dist*dist-dist[:,:1]**2
    variance=DESIGN['parameter_extension_sigma_km']**2+(DESIGN['off_axis_smoothing_fraction']*np.sqrt(best))**2
    compact=np.maximum(1-dd/np.maximum(dd[:,-1:],1e-12),0)**2
    weight=np.exp(-dd/(2*variance[:,None]))*compact;weight/=weight.sum(axis=1)[:,None]
    def interp(key):return (e[key][neighbors]*weight).sum(axis=1)
    tangents=e.setdefault('_tangents',np.gradient(xy,axis=0));tmean=(tangents[neighbors]*weight[:,:,None]).sum(axis=1)
    tmean/=np.maximum(np.linalg.norm(tmean,axis=1)[:,None],1e-12)
    qmean=(xy[neighbors]*weight[:,:,None]).sum(axis=1);delta_mean=points-qmean
    classification_normal=tmean[:,0]*delta_mean[:,1]-tmean[:,1]*delta_mean[:,0]
    left=interp('left');right=interp('right');side=.5*(1+np.tanh(classification_normal/DESIGN['side_blend_km']))
    width=side*left+(1-side)*right
    radial=np.sqrt(best)/width
    start=(j==0)&(t<=1e-12);end=(j==len(xy)-2)&(t>=1-1e-12)
    outward=np.sum(delta*v,axis=1)
    longitudinal=np.abs(np.where(start,np.minimum(outward,0)/max(e['caps'][0],1e-5),np.where(end,np.maximum(outward,0)/max(e['caps'][1],1e-5),0)))
    at_tip=start|end
    transverse=np.where(at_tip,np.abs(normal)/width,radial)
    radial=np.hypot(transverse,longitudinal)
    pl=interp('shape_left');pr=interp('shape_right');p=side*pl+(1-side)*pr
    return radial,interp('peak'),p,longitudinal,transverse,np.sqrt(pl*pr)

def evaluate(edges,x,y,scale,family,geometry_only=False):
    h,w=len(y),len(x);out=np.full((h,w),np.inf) if geometry_only else np.zeros((h,w))
    for e in edges:
        margin=scale*max(e['left'].max(),e['right'].max(),e['caps'].max())+2
        low=e['xy'].min(axis=0)-margin;high=e['xy'].max(axis=0)+margin
        ix=np.flatnonzero((x>=low[0])&(x<=high[0]));iy=np.flatnonzero((y>=low[1])&(y<=high[1]))
        if not len(ix) or not len(iy):continue
        for st in range(0,len(iy),max(1,int(55000/len(ix)))):
            rows=iy[st:st+max(1,int(55000/len(ix)))];X,Y=np.meshgrid(x[ix],y[rows]);pts=np.column_stack([X.ravel(),Y.ravel()])
            radial,peak,p,longitudinal,transverse,pcap=projected_values(e,pts)
            current=out[np.ix_(rows,ix)]
            if geometry_only:out[np.ix_(rows,ix)]=np.minimum(current,radial.reshape(X.shape))
            else:
                lr=longitudinal/scale;shrink=np.sqrt(np.maximum(1-lr*lr,1e-15))
                rr=transverse/(scale*shrink)
                val=peak*compact_profile(rr,p,family,DESIGN['tail_cutoff_fraction'],DESIGN['center_rounding_fraction'])
                val*=compact_profile(lr,pcap,family,DESIGN['tail_cutoff_fraction'],DESIGN['center_rounding_fraction'])
                out[np.ix_(rows,ix)]=np.maximum(current,val.reshape(X.shape))
    return out

def mask_dimensions(mask,x,y):
    dx=float(x[1]-x[0]);dy=float(y[1]-y[0]);area=float(mask.sum()*dx*dy)
    edge=mask&~binary_erosion(mask);yy,xx=np.nonzero(edge)
    if len(xx)<3:raise ValueError('Degenerate support')
    pts=np.column_stack([x[xx],y[yy]]);hull=ConvexHull(pts);v=pts[hull.vertices]
    # Include full pixel squares rather than centers only.
    corners=np.vstack([v+[a*dx/2,b*dy/2] for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]])
    rect=MultiPoint(corners).minimum_rotated_rectangle;length=float(np.linalg.norm(np.diff(np.asarray(rect.exterior.coords),axis=0),axis=1).max())
    return {'area_km2':area,'long_km':length,'equivalent_width_km':area/length,'bbox':[float(x[xx].min()-dx/2),float(x[xx].max()+dx/2),float(y[yy].min()-dy/2),float(y[yy].max()+dy/2)]}

def calibrate(edges,target,family):
    limit=6.;lo,hi=bounds(edges,limit);step=min(max(3.,float(max(hi-lo)/DESIGN['calibration_grid_cells_across'])),target/12)
    x=np.arange(lo[0],hi[0]+step,step);y=np.arange(lo[1],hi[1]+step,step)
    radial=evaluate(edges,x,y,limit,family,True);history=[];a=.08;b=limit
    for _ in range(14):
        scale=(a+b)/2;mask=radial<scale
        if mask.sum()<4:a=scale;continue
        measured=mask_dimensions(mask,x,y);err=measured['equivalent_width_km']/target-1
        history.append({'scale':scale,'equivalent_width_km':measured['equivalent_width_km'],'relative_error':err})
        if abs(err)<.015:break
        if err>0:b=scale
        else:a=scale
    return scale,{'coarse_grid_km':step,'iterations':history,'target_equivalent_width_km':target,
                  'rule':'calibrate support union area / its own minimum-rectangle long side; all physical coordinates retained'}

def generate_one(seed,out,ds,gm):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    L,draw=sample_scale(seed);record=generate_axis(seed,L,jload(AXIS_ROOT/'tables/geometry_reference.json'));record['scale_draw']=draw
    jsave(out/'axis.json',record)
    edges,pars=axis_parameters(record,ds,gm);target=pars['width_draw']['value_km'];scale,calibration=calibrate(edges,target,ds['decay_family'])
    # Tight computational extent is established from a coarse support scan, plus margin.
    low,high=bounds(edges,scale);step=max(2.,max(high-low)/600)
    xc=np.arange(low[0],high[0]+step,step);yc=np.arange(low[1],high[1]+step,step)
    rm=evaluate(edges,xc,yc,scale,ds['decay_family'],True);dim=mask_dimensions(rm<scale,xc,yc)
    b=dim['bbox'];padding=max(15.,.03*max(b[1]-b[0],b[3]-b[2]))
    x=np.arange(np.floor(b[0]-padding)+.5,np.ceil(b[1]+padding),1.);y=np.arange(np.floor(b[2]-padding)+.5,np.ceil(b[3]+padding),1.)
    u=evaluate(edges,x,y,scale,ds['decay_family']);mask=u>0
    if mask[0].any() or mask[-1].any() or mask[:,0].any() or mask[:,-1].any():raise RuntimeError('Complete field intersects computational boundary')
    dim=mask_dimensions(mask,x,y);error=dim['equivalent_width_km']/target-1
    np.savez_compressed(out/'field.npz',x_km=x,y_km=y,u_m_per_yr=u/1000,support=mask)
    edge_records=[]
    for e in edges:
        er={k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in e.items() if not k.startswith('_')}
        er['left']=(e['left']*scale).tolist();er['right']=(e['right']*scale).tolist();er['caps']=(e['caps']*scale).tolist();edge_records.append(er)
    jsave(out/'axis_field_parameters.json',{'edges':edge_records,'seed':seed,'unit_peak':'mm/yr','unit_geometry':'km','scale_applied':scale})
    metadata={'seed':seed,'version':VERSION,'axis_extent_km':L,'design':DESIGN,'model_hashes':{p.name:sha(p) for p in MODELS.glob('*model.json')},
      'parameters':pars,'width_calibration':calibration,'width_global_factor':scale,'realized_support':dim,'relative_width_error':float(error),
      'grid_shape':list(u.shape),'dx_km':1.,'peak_mm_yr':float(u.max()),'stored_unit':'m/yr','plot_unit':'mm/yr',
      'array_bounds_km':[float(x[0]-.5),float(x[-1]+.5),float(y[0]-.5),float(y[-1]+.5)],
      'axis_sha256':sha(out/'axis.json'),'field_sha256':sha(out/'field.npz'),'elapsed_seconds':time.perf_counter()-started,
      'validation':{'finite':bool(np.isfinite(u).all()),'nonnegative':bool((u>=0).all()),'zero_boundary':True,'width_relative_tolerance_pass':bool(abs(error)<.06)},
      'overlap_note':'auxiliary line constrains component fields; max-envelope overlap may elevate another component over its local input value'}
    jsave(out/'metadata.json',metadata)
    print(f"seed={seed} L={L:.1f} W={target:.1f} realized={dim['equivalent_width_km']:.1f} maxU={u.max():.3f} grid={u.shape} seconds={metadata['elapsed_seconds']:.1f}",flush=True)
    return metadata

def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--start',type=int,default=1001);ap.add_argument('--count',type=int,default=8);ap.add_argument('--output',default='output');args=ap.parse_args()
    out=(ROOT/args.output).resolve()
    if not out.is_relative_to(ROOT):raise ValueError('Output outside field module')
    ds=jload(MODELS/'DS5_model.json');gm=jload(MODELS/'G_geometry_model.json');records=[]
    if ds['settings']['far_tail_support_fraction']!=DESIGN['tail_cutoff_fraction']:raise ValueError('Model support convention changed; update generator explicitly')
    for seed in range(args.start,args.start+args.count):
        records.append(generate_one(seed,out/f'seed{seed}',ds,gm));jsave(out/'batch.json',{'samples':records,'seed_policy':'consecutive seeds; first draw; no morphology selection','source':'DS5','version':VERSION})

if __name__=='__main__':main()
