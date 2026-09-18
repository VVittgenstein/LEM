"""Rigid 500 km windows and the original continuous uplift function."""
import sys
import numpy as np
import shapely
from shapely.geometry import LineString,MultiLineString,Point,Polygon,box
from wcontext import *
sys.path.insert(0,str(FIELD))
from generate_fields import projected_values,DESIGN as FIELD_DESIGN
from stat_models import compact_profile

LOCAL=box(0,0,500,500)

def mask_geometry(mask,x0=0.,y0=0.):
    padded=np.pad(mask.astype(np.int8),((0,0),(1,1)))
    diff=np.diff(padded,axis=1);yr,left=np.nonzero(diff==1);yr2,right=np.nonzero(diff==-1)
    if not np.array_equal(yr,yr2):raise ValueError('Unpaired row runs')
    rectangles=shapely.box(x0+left,y0+yr,x0+right,y0+yr+1)
    result=shapely.union_all(rectangles)
    if not result.is_valid:raise ValueError('Invalid cell-union support')
    if abs(result.area-mask.sum())>1e-6:raise ValueError('Mask area mismatch')
    return result

def line_parts(g):
    if g.is_empty:return []
    if g.geom_type in ('LineString','LinearRing'):return [g] if g.length>1e-9 else []
    return [p for child in getattr(g,'geoms',[]) for p in line_parts(child)]

def polygons(g):
    if g.geom_type=='Polygon':return [g]
    return [p for child in getattr(g,'geoms',[]) for p in polygons(child)]

def rotation(theta):
    c,s=np.cos(theta),np.sin(theta);return np.array([[c,-s],[s,c]])

def world(local,center,R):return (np.asarray(local)-250)@R.T+center
def local(points,center,R):return (np.asarray(points)-center)@R+250
def world_geometry(g,center,R):return shapely.transform(g,lambda xy:world(xy,center,R))
def local_geometry(g,center,R):return shapely.transform(g,lambda xy:local(xy,center,R))
def window_polygon(center,R):return world_geometry(LOCAL,center,R)

def clipped_axis(axis,center,R):
    parts=line_parts(axis.intersection(window_polygon(center,R)))
    if not parts:return [],0.,0.
    pp=[local(np.asarray(p.coords),center,R) for p in parts];coords=np.vstack(pp)
    return pp,float(np.ptp(coords[:,0])),float(np.ptp(coords[:,1]))

class CompleteField:
    def __init__(self,seed,path=None):
        self.seed=seed;self.path=Path(path) if path is not None else FIELD/f'output/seed{seed}'
        self.axis_record=load(self.path/'axis.json');self.meta=load(self.path/'metadata.json')
        self.axis=MultiLineString(self.axis_record['edges'])
        data=np.load(self.path/'field.npz');self.x=data['x_km'];self.y=data['y_km'];self.u=data['u_m_per_yr'];self.support=data['support']
        self.geometry=mask_geometry(self.support,self.x[0]-.5,self.y[0]-.5);shapely.prepare(self.geometry)
        self.boundary=self.geometry.boundary
        self.exteriors=[shapely.orient_polygons(p).exterior for p in polygons(self.geometry)]
        self.lengths=np.array([p.length for p in self.exteriors]);self.vertices=shapely.get_coordinates(self.geometry)
        self.ds=load(FIELD/'models/DS5_model.json')
        self.edges=[]
        for e in load(self.path/'axis_field_parameters.json')['edges']:
            self.edges.append({k:np.asarray(v,float) if isinstance(v,list) else v for k,v in e.items()})
        g=self.axis_record['graph'];self.tips=np.asarray([p for p,n in zip(g['nodes'],g['node_degrees']) if n==1])

    def values(self,points):
        points=np.asarray(points,float);out=np.zeros(len(points));family=self.ds['decay_family']
        for e in self.edges:
            margin=max(e['left'].max(),e['right'].max(),e['caps'].max())+2
            lower=e['xy'].min(axis=0)-margin;upper=e['xy'].max(axis=0)+margin
            ids=np.flatnonzero(np.all((points>=lower)&(points<=upper),axis=1))
            for start in range(0,len(ids),35000):
                ids0=ids[start:start+35000];r,peak,p,l,t,pcap=projected_values(e,points[ids0])
                shrink=np.sqrt(np.maximum(1-l*l,1e-15))
                val=peak*compact_profile(t/shrink,p,family,FIELD_DESIGN['tail_cutoff_fraction'],FIELD_DESIGN['center_rounding_fraction'])
                val*=compact_profile(l,pcap,family,FIELD_DESIGN['tail_cutoff_fraction'],FIELD_DESIGN['center_rounding_fraction'])
                out[ids0]=np.maximum(out[ids0],val)
        return out/1000

    def boundary_draw(self,random):
        i=int(random.choice(len(self.exteriors),p=self.lengths/self.lengths.sum()));ring=self.exteriors[i]
        t=float(random.uniform(0,ring.length));p=np.array(ring.interpolate(t).coords[0])
        a=np.array(ring.interpolate((t-3)%ring.length).coords[0]);b=np.array(ring.interpolate((t+3)%ring.length).coords[0]);tangent=b-a
        tangent/=np.linalg.norm(tangent);out=np.array([tangent[1],-tangent[0]])
        if self.geometry.covers(Point(p+out)) or not self.geometry.covers(Point(p-out)):
            a=np.array(ring.interpolate((t-.05)%ring.length).coords[0]);b=np.array(ring.interpolate((t+.05)%ring.length).coords[0]);tangent=b-a;tangent/=np.linalg.norm(tangent);out=np.array([tangent[1],-tangent[0]])
        return p,out,{'boundary_component':i,'boundary_distance_km':t,'boundary_point_km':p.tolist(),'outward_normal':out.tolist()}

class Platform:
    def __init__(self,seed):
        self.seed=seed;self.path=BASE/f'seed{seed}/base.npz';self.data=np.load(self.path)
        self.mask=self.data['mask'];self.geometry=mask_geometry(self.mask);self.boundary=self.geometry.boundary
        shapely.prepare(self.geometry)
        from scipy.ndimage import distance_transform_edt
        self.maximum_clearance=float(distance_transform_edt(self.mask).max())

def preliminary_witness(field,platform,center,R,zero_inside):
    pieces=sorted(line_parts(zero_inside),key=lambda g:g.length,reverse=True)
    # A positive-length natural zero-boundary portion, not an isolated corner.
    for part in pieces[:6]:
        for fraction in (.5,.25,.75):
            b=np.asarray(part.interpolate(fraction,normalized=True).coords[0]);src=world(b,center,R)
            q=np.asarray(shapely.shortest_line(field.axis,Point(src)).coords[0]);ql=local(q,center,R)
            if not platform.geometry.contains(Point(ql)):continue
            path=LineString([ql,b])
            if path.length<1e-6 or not platform.geometry.covers(path):continue
            clearance=float(platform.boundary.distance(Point(b)))
            if clearance<=1e-7:continue
            kind='terminal' if len(field.tips) and np.linalg.norm(field.tips-q,axis=1).min()<1.1 else 'lateral'
            return {'axis_point_source_km':q.tolist(),'zero_proposal_source_km':src.tolist(),
              'axis_point_local_km':ql.tolist(),'zero_proposal_local_km':b.tolist(),
              'proposal_margin_km':clearance,'natural_boundary_portion_km':float(part.length),'kind':kind}
    return None

def verify_witness(field,platform,center,R,proposal):
    q=np.array(proposal['axis_point_local_km']);b=np.array(proposal['zero_proposal_local_km']);v=b-q;length=float(np.linalg.norm(v));v/=length
    end=length+min(8.,proposal['proposal_margin_km']/2)
    distances=np.linspace(0,end,max(3,int(np.ceil(end/.5))+1));positions=q+distances[:,None]*v
    if not platform.geometry.covers(LineString(positions)):return None
    u=field.values(world(positions,center,R))
    if u[0]<=0:return None
    zeros=np.flatnonzero(u==0)
    if not len(zeros):return None
    j=int(zeros[0]);lo=distances[j-1];hi=distances[j]
    for _ in range(17):
        mid=(lo+hi)/2
        if field.values(world([q+mid*v],center,R))[0]>0:lo=mid
        else:hi=mid
    point=q+hi*v;margin=float(platform.boundary.distance(Point(point)))
    if margin<=0 or not platform.geometry.contains(Point(point)):return None
    extra=min(1.,margin/2);after=point+extra*v
    z=field.values(world(np.array([point,after]),center,R))
    if np.any(z!=0):return None
    pp=q+np.linspace(0,hi,129)[:,None]*v;vv=field.values(world(pp,center,R))
    return {**proposal,'zero_point_local_km':point.tolist(),'zero_point_source_km':world(point,center,R).tolist(),
      'margin_km':margin,'decay_path_length_km':float(hi),'zero_value_m_per_yr':float(z[0]),
      'beyond_zero_value_m_per_yr':float(z[1]),'path_within_platform':True,
      'profile_local_xy_km':pp.tolist(),'profile_rate_m_per_yr':vv.tolist(),
      'definition':'one complete ridge-to-natural-zero transect lies inside the platform; adjacent natural zero-boundary portion identified; no whole-belt containment required'}
