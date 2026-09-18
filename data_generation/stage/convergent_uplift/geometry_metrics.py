"""Coordinate-based geometric descriptions used for references and generated axes."""
import numpy as np
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import LineString,MultiLineString

def resample(p,step=None,count=None):
    p=np.asarray(p,float);ds=np.linalg.norm(np.diff(p,axis=0),axis=1)
    p=p[np.r_[True,ds>1e-11]]
    if len(p)<2:raise ValueError('Degenerate line')
    s=np.r_[0,np.linalg.norm(np.diff(p,axis=0),axis=1).cumsum()]
    count=count or max(3,int(np.ceil(s[-1]/step))+1)
    q=np.linspace(0,s[-1],count)
    return np.column_stack([np.interp(q,s,p[:,j]) for j in range(2)])

def features(p):
    p=np.asarray(p,float);q=resample(p,count=257);d=np.diff(q,axis=0)
    angle=np.unwrap(np.arctan2(d[:,1],d[:,0]));angle=gaussian_filter1d(angle,2.,mode='nearest')
    turn=np.diff(angle);length=float(np.linalg.norm(np.diff(p,axis=0),axis=1).sum());chord=float(np.linalg.norm(p[-1]-p[0]))
    absolute=np.abs(turn);blocks=np.array([v.sum() for v in np.array_split(absolute,12)])
    result={'arc_length':length,'chord_length':chord,'sinuosity':length/max(chord,1e-12),
      'net_turn_deg':float(np.degrees(abs(turn.sum()))),'absolute_turn_deg':float(np.degrees(absolute.sum())),
      'turn_concentration':float(blocks.max()/max(blocks.sum(),1e-12)),
      'reversal_fraction':float(1-abs(turn.sum())/max(absolute.sum(),1e-12))}
    for frac in (.03,.08,.20):
        lag=max(1,int(round(256*frac)));a=angle[lag:]-angle[:-lag];a=(a+np.pi)%(2*np.pi)-np.pi
        result[f'turn_{int(frac*100):02d}_p95_deg']=float(np.percentile(np.abs(np.degrees(a)),95))
    return result

def long_side(edges):
    geom=MultiLineString([np.asarray(p).tolist() for p in edges]);rect=geom.minimum_rotated_rectangle
    if rect.geom_type=='Polygon':
        ds=np.linalg.norm(np.diff(np.asarray(rect.exterior.coords),axis=0),axis=1)
        return float(ds.max()),float(ds.min())
    return float(rect.length),0.

def graph_from_edges(edges,tol=1e-7):
    nodes=[];pairs=[]
    for p in edges:
        ids=[]
        for point in [p[0],p[-1]]:
            found=next((i for i,q in enumerate(nodes) if np.linalg.norm(point-q)<tol),None)
            if found is None:found=len(nodes);nodes.append(np.asarray(point).copy())
            ids.append(found)
        pairs.append(ids)
    deg=[0]*len(nodes);adj=[set() for _ in nodes]
    for a,b in pairs:deg[a]+=1;deg[b]+=1;adj[a].add(b);adj[b].add(a)
    seen=set();components=0
    for i in range(len(nodes)):
        if i in seen:continue
        components+=1;stack=[i];seen.add(i)
        while stack:
            for j in adj[stack.pop()]:
                if j not in seen:seen.add(j);stack.append(j)
    return {'nodes':[p.tolist() for p in nodes],'edge_nodes':pairs,'node_degrees':deg,
      'components':components,'junctions':sum(d==3 for d in deg),'cycles':len(edges)-len(nodes)+components}

def validity(edges):
    reasons=[]
    if not edges:return ['empty_geometry']
    if not all(np.isfinite(p).all() for p in edges):return ['nonfinite_coordinates']
    lines=[LineString(p) for p in edges]
    for i,p in enumerate(edges):
        if not lines[i].is_simple:reasons.append(f'self_intersection:{i}')
        if np.any(np.linalg.norm(np.diff(p,axis=0),axis=1)<1e-11):reasons.append(f'zero_step:{i}')
    for i in range(len(edges)):
        for j in range(i+1,len(edges)):
            inter=lines[i].intersection(lines[j])
            if inter.is_empty:continue
            for v in list(inter.geoms) if hasattr(inter,'geoms') else [inter]:
                if v.geom_type!='Point':reasons.append(f'overlap:{i}:{j}');continue
                p=np.asarray(v.coords)[0]
                if min(np.linalg.norm(p-edges[i][0]),np.linalg.norm(p-edges[i][-1]))>1e-7 or min(np.linalg.norm(p-edges[j][0]),np.linalg.norm(p-edges[j][-1]))>1e-7:
                    reasons.append(f'undeclared_intersection:{i}:{j}')
    return reasons
