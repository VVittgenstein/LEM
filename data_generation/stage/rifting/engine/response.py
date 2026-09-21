from __future__ import annotations
import math,time
import numpy as np
from .common import OUT,save
from .elastic import ElasticBox,sample_plane

def tetra_quadrature(order=3):
    nodes,weights=np.polynomial.legendre.leggauss(order);nodes=(nodes+1)/2;weights=weights/2
    barycentric=[];result=[]
    for i,r in enumerate(nodes):
        for j,s in enumerate(nodes):
            for k,t in enumerate(nodes):
                x=r;y=(1-r)*s;z=(1-r)*(1-s)*t
                barycentric.append([1-x-y-z,x,y,z]);result.append(6*weights[i]*weights[j]*weights[k]*(1-r)**2*(1-s))
    return np.asarray(barycentric),np.asarray(result)

def slip_eigenstrain(box,f,patch,origin,regularization_width_km=None,patch_half_length_km=None,quadrature_order=3):
    dip=math.radians(f['dip_deg']);az=f['dip_direction_rad']
    horizontal=np.array([math.cos(az),math.sin(az),0.])
    normal=math.sin(dip)*horizontal+np.array([0,0,math.cos(dip)])
    slip=math.cos(dip)*horizontal-np.array([0,0,math.sin(dip)])
    trace=np.asarray(f['trace_xy_km']);mid=trace[int((patch+.5)*len(trace)/3)]
    centre=np.r_[mid-origin,0.]*1000
    tangent=np.array([-horizontal[1],horizontal[0],0.])
    h=box.length_km/(box.n-1)*1000
    width=1.2*h if regularization_width_km is None else regularization_width_km*1000
    plane_width=f['bottom_depth_km']*1000/math.sin(dip)
    half_length=max(f['length_km']*1000/6,h*.65) if patch_half_length_km is None else patch_half_length_km*1000
    # Integrate the finite source through each element instead of sampling one centroid.
    barycentric,weights=tetra_quadrature(quadrature_order)
    tetra=box.nodes[box.tet];scalar=np.zeros(len(box.tet))
    for point,weight in zip(barycentric,weights):
        delta=np.einsum('i,eic->ec',point,tetra)-centre
        perp=delta@normal;along=delta@tangent;down=delta@slip
        cross=np.where(abs(perp)<width,np.cos(np.pi*np.clip(perp/width,-1,1)/2)**2/width,0)
        lateral=np.where(abs(along)<half_length,np.cos(np.pi*np.clip(along/half_length,-1,1)/2)**2,0)
        vertical=np.where((down>=0)&(down<=plane_width),np.sin(np.pi*np.clip(down/plane_width,0,1))**.5,0)
        scalar+=weight*cross*lateral*vertical
    # Unit imposed slip, with discrete volume integral preserving its moment area.
    target_area=f['length_km']*1000/6*plane_width*.7627597635
    measured=float(np.sum(scalar*box.volume))
    if measured<=0:raise ValueError('Unresolved slip source')
    scalar*=target_area/measured
    tensor=.5*(np.outer(slip,normal)+np.outer(normal,slip))
    vec=np.array([tensor[0,0],tensor[1,1],tensor[2,2],2*tensor[0,1],2*tensor[1,2],2*tensor[0,2]])
    return scalar[:,None]*vec,dict(regularization_width_km=width/1000,patch_half_length_km=half_length/1000,quadrature_order=quadrature_order,
        pre_normalization_moment_area_m2=measured,target_moment_area_m2=target_area)

def build_response(seed,model,faults,window):
    p=model['design_priors'];buffer=p['response_buffer_km'];length=500+2*buffer
    origin=np.array(window['origin_km'])-buffer
    begin=time.perf_counter()
    box=ElasticBox(length,p['response_nodes'],p['response_depth_layers'],p['reference_thickness_km'],p['elastic_young_GPa']*1e9,p['elastic_poisson'],support_bottom=True)
    x=np.arange(500)+.5+buffer;xx,yy=np.meshgrid(x,x)
    basis=[];details=[]
    for f in faults:
        for patch in range(3):
            eps,info=slip_eigenstrain(box,f,patch,origin,regularization_width_km=p['response_regularization_width_km'],patch_half_length_km=max(f['length_km']/6,p['response_minimum_patch_half_length_km']),quadrature_order=p['source_quadrature_order'])
            force=box.eigenstrain_load(eps);u,reaction=box.solve(force)
            # An explicit fixed basal reference supplies the lower-crust support.
            reference=np.zeros(6)
            surface=box.surface(u)
            sampled=sample_plane(surface,xx,yy,length)
            basis.append(sampled.astype(np.float32))
            details.append(dict(fault_id=f['id'],patch=patch,basal_support_reaction_peak_relative=reaction,
                rigid_balance_relative=float(np.max(abs(box.R@force))/max(np.linalg.norm(force),1)),
                exterior_rigid_mode_coefficients=reference.tolist(),**info))
        print('Fault response',f['id'],flush=True)
    result=np.asarray(basis,dtype=np.float32).reshape(len(faults)*3,500,500,3)
    save(OUT/f'seed{seed}'/'response_checks.json',dict(nodes=len(box.nodes),elements=len(box.tet),factor_seconds=box.factor_seconds,
        wall_seconds=time.perf_counter()-begin,patches=details,
        method='linear elastic eigenstrain weak form; one displacement solution per shared mesh; all source contributions summed before interpreting motion',
        boundary='all three velocities fixed at the 40 km basal reference; sides and top traction-free; no hidden rigid translation or rotation subtraction',
        output='unit slip response at the surface, metres per metre of prescribed slip',
        physical_scope='tectonic kinematic research approximation; no sedimentation, erosion, compaction or observed valley-depth input',
        limitation='Regularized fixed reference geometry; long-term geological calibration and finite-deformation advection remain unverified.',
        solver_horizontal_spacing_km=length/(box.n-1),query_spacing_km=1))
    return result

def field_from_coefficients(basis,coefficients):
    # Sources encode distinct relative slip contributions, not complete duplicated basins.
    return np.einsum('p,pyxc->yxc',np.asarray(coefficients).ravel(),basis,optimize=True)
