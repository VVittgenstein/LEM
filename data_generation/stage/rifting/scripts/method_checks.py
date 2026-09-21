"""Synthetic numerical checks, not a calibrated geological generator.

2D plane-stress constant-strain triangles test static response bookkeeping.
Three vertical block velocities test the rank and common-motion constraints.
No output is a natural parameter, production rift field or LEM result.
"""
from __future__ import annotations
import json
import math
import time
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import factorized
from scipy.integrate import quad
from workspace import write_json

class PlaneStress:
    def __init__(self,n):
        self.n=n
        # Normalized length, modulus and thickness; deliberately not km/Pa input.
        x,y=np.meshgrid(np.linspace(0,1,n+1),np.linspace(0,1,n+1))
        self.xy=np.column_stack([x.ravel(),y.ravel()])
        triangles=[]
        for j in range(n):
            for i in range(n):
                a=j*(n+1)+i;b=a+1;c=a+n+1;d=c+1
                triangles.extend([(a,b,d),(a,d,c)])
        self.tri=np.array(triangles)
        nu=.25
        self.D=np.array([[1,nu,0],[nu,1,0],[0,0,(1-nu)/2]])/(1-nu**2)
        self.B=[];self.dofs=[];self.area=[];rr=[];cc=[];vv=[]
        for tri in self.tri:
            pts=self.xy[tri];x,y=pts.T
            area=np.linalg.det(np.column_stack([np.ones(3),x,y]))/2
            assert area>0
            b=np.array([y[1]-y[2],y[2]-y[0],y[0]-y[1]])/(2*area)
            c=np.array([x[2]-x[1],x[0]-x[2],x[1]-x[0]])/(2*area)
            B=np.zeros((3,6));B[0,::2]=b;B[1,1::2]=c;B[2,::2]=c;B[2,1::2]=b
            dofs=np.ravel(np.column_stack([2*tri,2*tri+1]));k=area*B.T@self.D@B
            rr.extend(np.repeat(dofs,6));cc.extend(np.tile(dofs,6));vv.extend(k.ravel())
            self.B.append(B);self.dofs.append(dofs);self.area.append(area)
        ndof=len(self.xy)*2
        self.K=coo_matrix((vv,(rr,cc)),shape=(ndof,ndof)).tocsc()
        # Remove only two translations and rotation; balanced loads must give negligible reactions.
        self.fixed=np.array([0,1,2*n+1]);self.free=np.setdiff1d(np.arange(ndof),self.fixed)
        self.solve_free=factorized(self.K[self.free][:,self.free])
        self.centres=self.xy[self.tri].mean(axis=1)

    def uniform_stress_load(self,S):
        f=np.zeros_like(self.xy)
        n=self.n
        for ids,normal in [([j*(n+1) for j in range(n+1)],[-1,0]),
                           ([j*(n+1)+n for j in range(n+1)],[1,0]),
                           (list(range(n+1)),[0,-1]),
                           ([n*(n+1)+i for i in range(n+1)],[0,1])]:
            traction=S@normal
            for a,b in zip(ids[:-1],ids[1:]):
                load=np.linalg.norm(self.xy[a]-self.xy[b])*traction/2
                f[a]+=load;f[b]+=load
        return f.ravel()

    def outside_local_load(self):
        # Two compact horizontal patches outside the central x=0.25..0.75 window.
        f=np.zeros_like(self.xy)
        for x0,sign in [(0.08,-1),(0.18,1)]:
            distance=np.linalg.norm(self.xy-[x0,.5],axis=1)
            w=np.maximum(1-(distance/.045)**2,0)**2
            assert w.sum()>0
            f[:,0]+=sign*.05*w/w.sum()
        return f.ravel()

    def balance(self,f):
        force=f.reshape(-1,2)
        return np.array([*force.sum(axis=0),np.sum(self.xy[:,0]*force[:,1]-self.xy[:,1]*force[:,0])])

    def solve(self,f):
        if np.max(abs(self.balance(f)))>1e-9*max(1,np.linalg.norm(f)):
            raise ValueError('Unbalanced static load: explicit reaction required')
        u=np.zeros(len(f));u[self.free]=self.solve_free(f[self.free])
        stress=np.array([self.D@B@u[dofs] for B,dofs in zip(self.B,self.dofs)])
        reactions=self.K@u-f
        return stress,u,float(np.max(abs(reactions[self.fixed])))

def mechanics_checks():
    cases=[]
    for n in [8,16,32]:
        solver=PlaneStress(n);S=np.array([[1,.2],[.2,.4]])
        stress,u,reaction=solver.solve(solver.uniform_stress_load(S))
        expected=np.array([1,.4,.2])
        error=float(np.max(abs(stress-expected)))
        cases.append(dict(mesh_intervals=n,elements=len(solver.tri),max_stress_error=error,max_gauge_reaction=reaction))
        assert error<1e-9 and reaction<1e-9
    s=PlaneStress(40);far=s.uniform_stress_load(np.array([[1,0],[0,0]]));local=s.outside_local_load()
    a,_,_=s.solve(far);b,_,_=s.solve(local);c,_,reaction=s.solve(far+local)
    linear_error=float(np.max(abs(c-a-b)));assert linear_error<1e-9
    window=((s.centres>.25)&(s.centres<.75)).all(axis=1)
    influence=float(np.sqrt(np.mean(b[window]**2)));assert influence>1e-6
    load_positions=s.xy[np.linalg.norm(local.reshape(-1,2),axis=1)>0]
    assert np.max(load_positions[:,0])<.25
    rejected=False
    bad=far.copy();bad[-2]+=.1
    try: s.solve(bad)
    except ValueError: rejected=True
    assert rejected
    return dict(scope='Synthetic normalized 2D plane stress; not the proposed 3D basal-traction backend or a natural-force fit.',
                affine_patch_cases=cases,superposition_max_error=linear_error,
                outside_source_window_stress_rms=influence,max_source_x=float(load_positions[:,0].max()),
                window_x=[.25,.75],combined_gauge_reaction=reaction,unbalanced_load_rejected=rejected,
                not_tested=['3D force transfer','natural amplitudes','far-source distance threshold','long-term rheology','domain convergence'])

def block_checks():
    # Vertical velocities [left, centre, right] in mm/yr, one shared centre.
    A=np.array([[-1,1,0],[0,1,-1]],dtype=float);d=np.array([-1,-1.])
    rank=int(np.linalg.matrix_rank(A));assert rank==2
    gauge=np.array([[.5,0,.5]])
    M=np.vstack([A,gauge]);u=np.linalg.solve(M,np.r_[d,0.])
    shifted=np.linalg.solve(M,np.r_[d,.3])
    assert np.allclose(u,[0,-1,0]) and np.allclose(shifted-u,.3)
    # Contradictory third relative condition must be exposed, not smoothed away.
    inconsistent=np.vstack([A,[-1,0,1]]);target_d=np.r_[d,.5]
    proposed=np.linalg.lstsq(np.vstack([inconsistent,gauge]),np.r_[target_d,0],rcond=None)[0]
    residual=float(np.max(abs(inconsistent@proposed-target_d)));assert residual>.1
    duration=10_000_000.
    def U(t):return u*1e-3*math.sin(math.pi*t/duration)**2
    def displacement(a,b):return np.array([quad(lambda t:U(t)[i],a,b,epsabs=1e-8)[0] for i in range(3)])
    full=displacement(0,duration);parts=sum((displacement(a,b) for a,b in zip(np.linspace(0,duration,8)[:-1],np.linspace(0,duration,8)[1:])),np.zeros(3))
    assert np.max(abs(full-parts))<1e-8
    assert abs(full[1]+5000)<1e-8
    # No stochastic operation is used anywhere in this response calculation.
    repeat=np.linalg.solve(M,np.r_[d,0.]);assert np.array_equal(repeat,u)
    return dict(scope='Synthetic scalar block velocities; no geological profile or 3D compatibility validation.',
                constraint_rank=rank,unknowns=3,unfixed_reference_nullity=3-rank,
                solution_mm_per_yr=u.tolist(),reference_shift_mm_per_yr=(shifted-u).tolist(),
                inconsistent_candidate_max_residual_mm_per_yr=residual,
                incompatible_candidate_rejected=bool(residual>.1),
                integrated_displacement_m=full.tolist(),partition_integral_error_m=float(np.max(abs(full-parts))),
                deterministic_repeat_exact=bool(np.array_equal(repeat,u)),shared_central_block_count=1,
                all_numbers_are_test_inputs=True,
                not_tested=['spatial response width','bending basis','fault growth and topology transfer','long-term geological calibration'])

def main():
    t=time.perf_counter()
    result=dict(mechanics=mechanics_checks(),kinematics=block_checks(),production_ready=False)
    result['wall_seconds']=time.perf_counter()-t
    write_json('output/checks/method_checks.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
