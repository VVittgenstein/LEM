import numpy as np
from pyproj import Transformer
from scipy.ndimage import gaussian_filter
from context import *

def load_ds5():
    a=np.loadtxt(RAW/'DS5_ENU_velocity.txt', skiprows=1)
    xy=np.column_stack(Transformer.from_crs(4326,2193,always_xy=True).transform(a[:,0],a[:,1]))/1000
    origin=xy.mean(axis=0);xy-=origin
    return a,xy,origin

def inspect():
    freeze(); a,xy,origin=load_ds5()
    report={'rows':len(a),'columns':10,'nan_by_column':np.isnan(a).sum(axis=0).tolist(),
      'duplicate_coordinates':len(a)-len(np.unique(a[:,:2],axis=0)),
      'referenced_up_quantiles_mm_yr':np.quantile(a[:,7],[0,.05,.25,.5,.75,.95,1]).tolist(),
      'up_error_quantiles_mm_yr':np.quantile(a[:,8],[0,.25,.5,.75,1]).tolist(),
      'negative_referenced_up_rows':int((a[:,7]<0).sum()),'projection':'EPSG:2193; local km',
      'origin_projected_km':origin.tolist()}
    # Explore source orientation without changing or clipping any velocity.
    weight=np.maximum(a[:,7]-np.quantile(a[:,7],.6),0)**2/np.maximum(a[:,8],.2)**2
    center=np.average(xy,axis=0,weights=weight); cov=np.cov((xy-center).T,aweights=weight)
    val,vec=np.linalg.eigh(cov);along=vec[:,-1]
    if along[1]<0: along=-along
    cross=np.array([along[1],-along[0]])
    sn=(xy-center)@np.column_stack([along,cross])
    report.update(strike_from_east_deg=float(np.degrees(np.arctan2(along[1],along[0]))),
      along_unit=along.tolist(),cross_unit=cross.tolist(),center_local_km=center.tolist(),
      rotated_limits=np.column_stack([sn.min(axis=0),sn.max(axis=0)]).tolist())
    jsave(CHECKS/'DS5_quality.json',report)
    plt=plotting();fig,axs=plt.subplots(1,2,figsize=(12,6));fig.subplots_adjust(wspace=.3,bottom=.15,top=.88)
    for ax,pts,title in zip(axs,[xy,sn],['DS5 原始参考垂向速度','以高值区主方向旋转的坐标']):
        im=ax.scatter(*pts.T,c=a[:,7],s=3,vmin=-3,vmax=12,cmap='turbo');ax.set_aspect('equal');ax.set_title(title)
        ax.set_xlabel('km');ax.set_ylabel('km')
    fig.colorbar(im,ax=axs,label='mm/yr',fraction=.025,pad=.02)
    fig.suptitle('数据检查：保留原始负值及测量误差');fig.savefig(CHECKS/'DS5_raw.png',dpi=160);plt.close(fig)
    print(json.dumps(report,indent=2))

if __name__=='__main__':inspect()
