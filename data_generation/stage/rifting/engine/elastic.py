"""Homogeneous small-strain 3D linear elasticity with four-node tetrahedra.

External traction and eigenstrain use the same weak form. A slip response is
an imposed shear eigenstrain, not a sediment or observed valley-depth field.
The finite reference box and regularized slip width remain explicit approximations.
"""
from __future__ import annotations
import time
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu
from scipy.ndimage import map_coordinates

class ElasticBox:
    def __init__(self,length_km=2000,n=25,nz=5,depth_km=40,young_pa=30e9,nu=.25,support_bottom=False):
        self.length_km=length_km;self.depth_km=depth_km;self.n=n;self.nz=nz
        self.x=np.linspace(0,length_km,n);self.z=np.linspace(-depth_km,0,nz)
        zz,yy,xx=np.meshgrid(self.z,self.x,self.x,indexing='ij')
        self.nodes=np.column_stack([xx.ravel(),yy.ravel(),zz.ravel()])*1000
        bases=np.arange((n-1)*(n-1)*(nz-1))
        iz=bases//((n-1)**2);rem=bases%((n-1)**2);iy=rem//(n-1);ix=rem%(n-1)
        p=iz*n*n+iy*n+ix
        cube=np.stack([p,p+1,p+n,p+n+1,p+n*n,p+n*n+1,p+n*n+n,p+n*n+n+1],axis=1)
        local=np.array([[0,1,3,7],[0,3,2,7],[0,2,6,7],[0,6,4,7],[0,4,5,7],[0,5,1,7]])
        self.tet=cube[:,local].reshape(-1,4)
        xyz=self.nodes[self.tet]
        mat=np.concatenate([np.ones((*xyz.shape[:2],1)),xyz],axis=2)
        self.volume=abs(np.linalg.det(mat))/6
        gradients=np.linalg.inv(mat)[:,1:,:].transpose(0,2,1)
        B=np.zeros((len(self.tet),6,12))
        for i in range(4):
            gx,gy,gz=gradients[:,i,:].T
            B[:,0,3*i]=gx;B[:,1,3*i+1]=gy;B[:,2,3*i+2]=gz
            B[:,3,3*i]=gy;B[:,3,3*i+1]=gx
            B[:,4,3*i+1]=gz;B[:,4,3*i+2]=gy
            B[:,5,3*i]=gz;B[:,5,3*i+2]=gx
        self.B=B;self.centres=xyz.mean(axis=1)
        mu=young_pa/(2*(1+nu));lam=young_pa*nu/((1+nu)*(1-2*nu))
        D=np.zeros((6,6));D[:3,:3]=lam;np.fill_diagonal(D[:3,:3],lam+2*mu);D[3:,3:]=np.eye(3)*mu
        self.D=D
        self.dofs=(self.tet[...,None]*3+np.arange(3)).reshape(-1,12)
        ke=np.einsum('eai,ab,ebj,e->eij',B,D,B,self.volume,optimize=True)
        ndof=len(self.nodes)*3
        rows=np.broadcast_to(self.dofs[:,:,None],ke.shape).ravel()
        cols=np.broadcast_to(self.dofs[:,None,:],ke.shape).ravel()
        self.K=coo_matrix((ke.ravel(),(rows,cols)),shape=(ndof,ndof)).tocsc()
        del ke,rows,cols
        self.support_bottom=support_bottom
        self.fixed=np.arange(n*n*3) if support_bottom else np.array([0,1,2,3*(n-1)+1,3*(n-1)+2,3*((n-1)*n)+2])
        self.free=np.setdiff1d(np.arange(ndof),self.fixed)
        begin=time.perf_counter();self.lu=splu(self.K[self.free][:,self.free],permc_spec='COLAMD')
        self.factor_seconds=time.perf_counter()-begin
        faces=np.sort(self.tet[:,np.array([[0,1,2],[0,1,3],[0,2,3],[1,2,3]])].reshape(-1,3),axis=1)
        unique,count=np.unique(faces,axis=0,return_counts=True);self.faces=unique[count==1]
        fxyz=self.nodes[self.faces];cross=np.cross(fxyz[:,1]-fxyz[:,0],fxyz[:,2]-fxyz[:,0])
        self.face_area=np.linalg.norm(cross,axis=1)/2;norm=cross/(2*self.face_area[:,None])
        self.face_centres=fxyz.mean(axis=1)
        mid=self.nodes.mean(axis=0);norm*=np.where(np.sum(norm*(self.face_centres-mid),axis=1)>0,1,-1)[:,None]
        self.face_normal=norm
        relative=(self.nodes-mid)/(length_km*1000)
        R=np.zeros((6,len(self.nodes),3));R[0,:,0]=1;R[1,:,1]=1;R[2,:,2]=1
        R[3,:,1]=-relative[:,2];R[3,:,2]=relative[:,1]
        R[4,:,0]=relative[:,2];R[4,:,2]=-relative[:,0]
        R[5,:,0]=-relative[:,1];R[5,:,1]=relative[:,0]
        self.R=R.reshape(6,-1)
        side=abs(norm[:,2])<.5
        weights=np.zeros(len(self.nodes))
        for i in range(3):np.add.at(weights,self.faces[side,i],self.face_area[side]/3)
        W=np.repeat(weights,3);C=W[:,None]*self.R.T
        self.correction=C@np.linalg.inv(self.R@C)
        self.nodal_volume=np.bincount(self.tet.ravel(),weights=np.repeat(self.volume,4),minlength=len(self.nodes))

    def traction(self,values):
        values=np.broadcast_to(values,(len(self.faces),3))
        f=np.zeros((len(self.nodes),3))
        for i in range(3):np.add.at(f,self.faces[:,i],values*self.face_area[:,None]/3)
        return f.ravel()

    def balanced(self,f):
        correction=-(self.correction@(self.R@f))
        result=f+correction
        scale=max(np.linalg.norm(f),1)
        return result,dict(relative_balance=float(np.max(abs(self.R@result))/scale),
                           correction_l2_fraction=float(np.linalg.norm(correction)/scale))

    def solve(self,f):
        f=np.asarray(f,float);one=f.ndim==1
        if one:f=f[:,None]
        u=np.zeros_like(f);u[self.free]=self.lu.solve(f[self.free])
        reaction=self.K@u-f
        rel=np.max(abs(reaction[self.fixed]))/max(np.max(abs(f)),1)
        return (u[:,0] if one else u),float(rel)

    def nodal_stress(self,u):
        strain=np.einsum('eij,ej->ei',self.B,u[self.dofs]);stress=strain@self.D.T
        out=np.zeros((len(self.nodes),6))
        for i in range(4):np.add.at(out,self.tet[:,i],stress*self.volume[:,None])
        out/=self.nodal_volume[:,None]
        return out.reshape(self.nz,self.n,self.n,6)

    def eigenstrain_load(self,eps):
        stress=eps@self.D.T
        values=np.einsum('eij,ei,e->ej',self.B,stress,self.volume)
        return np.bincount(self.dofs.ravel(),weights=values.ravel(),minlength=len(self.nodes)*3)

    def surface(self,u):return u.reshape(self.nz,self.n,self.n,3)[-1]

def sample_plane(plane,x_km,y_km,length_km):
    plane=np.asarray(plane)
    shape=np.broadcast_shapes(np.shape(x_km),np.shape(y_km));x=np.broadcast_to(x_km,shape);y=np.broadcast_to(y_km,shape)
    coords=np.stack([y.ravel(),x.ravel()])*(plane.shape[0]-1)/length_km
    out=np.stack([map_coordinates(plane[...,i],coords,order=1,mode='nearest') for i in range(plane.shape[-1])],axis=-1)
    return out.reshape(*shape,plane.shape[-1])
