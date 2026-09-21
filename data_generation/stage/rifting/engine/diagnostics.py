"""Fixed-source mesh comparisons, separate from physical domain-size trials."""
from __future__ import annotations
import argparse,copy,time
import numpy as np
from .common import save,stress_display
from .products import Run
from .elastic import ElasticBox,sample_plane
from .forcing import source_load,diagnostic_plane,coefficients
from .response import slip_eigenstrain

def relative_l2(a,b):
    return float(np.linalg.norm(a-b)/max(np.linalg.norm(b),1e-30))

def run_diagnostics(seed=1001):
    run=Run(seed);p=run.model['design_priors'];dest=run.path/'validation';dest.mkdir(exist_ok=True)
    origin=np.asarray(run.window['origin_km']);x=origin[0]+np.arange(12.5,500,25);y=origin[1]+np.arange(12.5,500,25)
    xx,yy=np.meshgrid(x,y);times=np.arange(6.,49.,6.)
    reference=np.array([sample_plane(s,xx,yy,run.length) for s in run.basis])
    comparisons=[];stress_samples={};base_stress=p['stress_solver_nodes'];stress_meshes=[base_stress-32,base_stress,base_stress+32]
    for n in stress_meshes:
        begin=time.perf_counter()
        box=ElasticBox(run.length,n,p['stress_depth_layers'],p['reference_thickness_km'],p['elastic_young_GPa']*1e9,p['elastic_poisson'])
        basis=[]
        for episode in run.episodes:
            force,_=source_load(box,episode);u,_=box.solve(force)
            plane=diagnostic_plane(box,u,p['diagnostic_depth_km'])*episode['reference_force_N']/1e6
            basis.append(sample_plane(plane,xx,yy,run.length))
        basis=np.asarray(basis);stress_samples[n]=basis
        comparisons.append(dict(nodes_per_side=n,horizontal_spacing_km=run.length/(n-1),
            window_basis_relative_l2_vs_saved=relative_l2(basis,reference),wall_seconds=time.perf_counter()-begin))
        print('Fixed-force stress mesh',n,flush=True)
        del box
    stress_history=[]
    for t in times:
        cc=coefficients(run.episodes,t);ref=np.einsum('e,eyxc->yxc',cc,reference)
        row=dict(elapsed_Myr=float(t))
        for n in stress_meshes:
            field=np.einsum('e,eyxc->yxc',cc,stress_samples[n]);row[str(n)]=relative_l2(field,ref)
        stress_history.append(row)
    selected=sorted(set(np.argsort([f['length_km'] for f in run.faults])[[0,len(run.faults)//2,-1]].tolist())) if run.faults else []
    response_rows=[];response_samples={};length=500+2*p['response_buffer_km'];response_origin=origin-p['response_buffer_km']
    grid=np.arange(12.5,500,25);rx,ry=np.meshgrid(grid+p['response_buffer_km'],grid+p['response_buffer_km'])
    production_h=length/(p['response_nodes']-1);fixed_width=p['response_regularization_width_km']
    for n in [33,41,49]:
        begin=time.perf_counter();box=ElasticBox(length,n,p['response_depth_layers'],p['reference_thickness_km'],p['elastic_young_GPa']*1e9,p['elastic_poisson'],support_bottom=True)
        fields=[]
        for i in selected:
            f=run.faults[i];half_length=max(f['length_km']/6,p['response_minimum_patch_half_length_km']);total=np.zeros((20,20))
            for patch in range(3):
                eps,_=slip_eigenstrain(box,f,patch,response_origin,fixed_width,half_length)
                u,_=box.solve(box.eigenstrain_load(eps));total+=sample_plane(box.surface(u),rx,ry,length)[...,2]
            fields.append(total)
        response_samples[n]=np.asarray(fields)
        print('Fixed-source response mesh',n,flush=True)
        response_rows.append(dict(nodes_per_side=n,horizontal_spacing_km=length/(n-1),wall_seconds=time.perf_counter()-begin))
        del box
    for row in response_rows:
        n=row['nodes_per_side'];row['per_fault_relative_l2_vs_41']={run.faults[i]['id']:relative_l2(response_samples[n][j],response_samples[41][j]) for j,i in enumerate(selected)}
    result=dict(identity='diagnostic comparison; no acceptance tolerance or asymptotic convergence claim',
        fixed_quantities=['physical box dimensions','source contacts and directions','reference force in N','elastic properties','stress diagnostic depth','fault reference geometry and slip','30 km regularization width and production patch extent','basal reference'],
        stress_meshes=comparisons,stress_history=stress_history,response_meshes=response_rows,
        response_fault_ids=[run.faults[i]['id'] for i in selected],response_regularization_width_km=fixed_width,
        scope='Three selected fault responses and eight stress times in the sampled window; boundary, thickness and rheological uncertainty remain separate.')
    save(dest/'numerical_diagnostics.json',result)
    np.savez_compressed(dest/'numerical_diagnostics_arrays.npz',**{f'stress_{n}':v for n,v in stress_samples.items()},**{f'response_{n}':v for n,v in response_samples.items()})
    from .rendering import plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),layout='constrained')
    for n in [stress_meshes[0],stress_meshes[-1]]:axes[0].plot(times,[r[str(n)]*100 for r in stress_history],'-o',label=f'{run.length/(n-1):g} km')
    axes[0].set(xlabel='模拟时间 / Myr',ylabel=f'相对当前{run.length/(base_stress-1):g} km网格的张量L2差异 / %',title='固定物理作用与力值，比较应力求解网格');axes[0].legend()
    for j,i in enumerate(selected):
        axes[1].plot([length/(n-1) for n in [33,41,49]],[relative_l2(response_samples[n][j],response_samples[41][j])*100 for n in [33,41,49]],'-o',label=run.faults[i]['id'])
    axes[1].set(xlabel='响应求解格距 / km',ylabel='相对当前25 km网格的U响应L2差异 / %',title='保持源宽度30 km，比较三条断层');axes[1].legend()
    fig.savefig(dest/'mesh_comparison.png',dpi=160);plt.close(fig)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=1001);args=ap.parse_args();run_diagnostics(args.seed)
