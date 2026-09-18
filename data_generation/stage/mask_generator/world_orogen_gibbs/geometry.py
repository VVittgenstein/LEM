"""Full-domain World Orogen projection and exact cell-edge geometry.

The read-only growth/noise dependencies are GPLv3 adaptations; see THIRD_PARTY.md.
"""
from collections import deque
from dataclasses import dataclass
import time
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from common.io import array_sha256
from world_orogen.partitions import grow_partitions
from world_orogen.noise import SimplexNoise

L4 = ndi.generate_binary_structure(2,1)


def reconnect(labels, seed_pixels):
    """Repair only INPUT partitions, using bounded pixel neighbors (no row wrap)."""
    for rid,(y,x) in enumerate(seed_pixels,1):
        labels[y,x]=rid
    good=np.zeros_like(labels,bool)
    slices=ndi.find_objects(labels)
    for rid,(region_slice,(y,x)) in enumerate(zip(slices,seed_pixels),1):
        if region_slice is None:
            raise ValueError('empty input region')
        local=labels[region_slice]
        cc,_=ndi.label(local==rid,L4)
        root=cc[y-region_slice[0].start,x-region_slice[1].start]
        good[region_slice] |= cc==root
    orphan=~good
    changes=int(orphan.sum())
    labels[orphan]=0
    queue=deque(map(int,np.flatnonzero(good & ndi.binary_dilation(orphan,L4))))
    h,w=labels.shape
    flat=labels.ravel()
    while queue:
        k=queue.popleft(); y,x=divmod(k,w)
        neighbors=[]
        if y: neighbors.append(k-w)
        if y+1<h: neighbors.append(k+w)
        if x: neighbors.append(k-1)
        if x+1<w: neighbors.append(k+1)
        for j in neighbors:
            if flat[j]==0:
                flat[j]=flat[k]; queue.append(j)
    if (labels==0).any(): raise ValueError('partition repair failed')
    return changes


def generate_partitions(seed, settings):
    settings.validate(); start=time.perf_counter()
    points,coarse,seeds,growth=grow_partitions(seed,settings)
    size=settings.size
    xy=points[seeds]*size
    yy,xx=np.mgrid[:size,:size].astype(float)+.5
    u,v=xx/size,yy/size
    coarse_km=size/settings.coarse_side
    amplitude=coarse_km*(1.5+growth['low_partition_factor'])*settings.warp_multiplier
    noise=SimplexNoise(seed+999)
    dx,dy=np.zeros_like(xx),np.zeros_like(yy)
    for octave in range(4):
        freq=8*2**octave
        dx+=amplitude*.5**octave*noise.noise3d(u*freq,v*freq,0.)
        dy+=amplitude*.5**octave*noise.noise3d(u*freq+100,v*freq+100,100.)
    distance=cKDTree(xy).query(np.column_stack([xx.ravel(),yy.ravel()]),workers=1)[0].reshape(xx.shape)
    pin=1-np.exp(-.5*(distance/coarse_km)**2)
    edge=np.minimum.reduce([xx,size-xx,yy,size-yy])
    taper=np.clip(edge/(2*coarse_km),0,1);taper=taper*taper*(3-2*taper)
    dx*=pin*taper;dy*=pin*taper
    query=np.column_stack([np.clip((xx+dx)/size,0,1).ravel(),np.clip((yy+dy)/size,0,1).ravel()])
    owner=cKDTree(points).query(query,workers=1)[1]
    labels=(coarse[owner].reshape(size,size)+1).astype(np.int16)
    pixels=np.floor(xy[:,[1,0]]).astype(int)
    changes=reconnect(labels,pixels)
    slices=ndi.find_objects(labels)
    for rid,sl in enumerate(slices,1):
        if ndi.label(labels[sl]==rid,L4)[1]!=1:
            raise ValueError('disconnected input partition')
    return labels,xy,dict(growth,seed=seed,seed_point_indices=seeds.tolist(),
        seed_pixels_row_col=pixels.tolist(),seed_xy_km=xy.tolist(),
        raster_reassigned_cells=changes,raster_reassigned_fraction=changes/labels.size,
        labels_sha256=array_sha256(labels),wall_s=time.perf_counter()-start,
        fixed_ocean_band_km=0,post_selection_pixel_edits=False),dict(points=points,labels=coarse,dx=dx,dy=dy)


@dataclass
class Geometry:
    labels: np.ndarray
    areas: np.ndarray
    mx: np.ndarray
    my: np.ndarray
    m2: np.ndarray
    edges: np.ndarray
    lengths: np.ndarray
    forbidden: np.ndarray
    neighbors: list
    perimeter: np.ndarray
    center_id: int
    size: int
    boundary_layers: int
    region_clearance_km: np.ndarray
    region_layer: np.ndarray


def boundary_reserve(labels,boundary_layers=1,cell_km=1.,edges=None):
    """Graph layers select whole regions; pixel-edge clearance is diagnostic.

    Layer 1 touches the domain border. Each shared-edge graph hop adds one layer.
    The resulting widths are measured in km and are not assumed constant.
    """
    labels=np.asarray(labels)
    if labels.ndim!=2 or labels.min()<1 or not np.issubdtype(labels.dtype,np.integer):
        raise ValueError('positive integer partition labels required')
    if not np.isfinite(cell_km) or cell_km<=0:
        raise ValueError('cell size must be positive and finite')
    if isinstance(boundary_layers,bool) or not isinstance(boundary_layers,int) or boundary_layers<1:
        raise ValueError('boundary_layers must be a positive integer')
    yy,xx=np.indices(labels.shape)
    pixel_distance=np.minimum.reduce([yy,xx,labels.shape[0]-1-yy,labels.shape[1]-1-xx])*cell_km
    distances=np.full(int(labels.max()),np.inf)
    np.minimum.at(distances,labels.ravel()-1,pixel_distance.ravel())
    if not np.isfinite(distances).all():raise ValueError('partition IDs must be contiguous')
    if edges is None:
        pairs=[]
        for p,q in ((labels[1:],labels[:-1]),(labels[:,1:],labels[:,:-1])):
            changed=p!=q
            pairs.append(np.sort(np.column_stack([p[changed],q[changed]]),axis=1)-1)
        edges=np.unique(np.concatenate(pairs),axis=0)
    neighbors=[[] for _ in distances]
    for i,j in edges:neighbors[i].append(int(j));neighbors[j].append(int(i))
    layers=np.zeros(len(distances),np.int32)
    touching=np.flatnonzero(distances==0);layers[touching]=1
    queue=deque(map(int,touching))
    while queue:
        i=queue.popleft()
        for j in neighbors[i]:
            if layers[j]==0:layers[j]=layers[i]+1;queue.append(j)
    if np.any(layers==0):raise ValueError('partition adjacency graph is disconnected from the domain boundary')
    return layers<=boundary_layers,distances,layers


def geometry(labels,boundary_layers=1):
    n=int(labels.max()); h,w=labels.shape
    if h!=w or labels.min()!=1: raise ValueError('complete square partition array required')
    yy,xx=np.mgrid[:h,:w].astype(float)+.5
    xx=xx/w-.5; yy=yy/h-.5
    flat=labels.ravel()
    a=np.bincount(flat,minlength=n+1)[1:].astype(float)/labels.size
    def moment(values): return np.bincount(flat,weights=values.ravel(),minlength=n+1)[1:]/labels.size
    pairs=[]
    for p,q in ((labels[1:],labels[:-1]),(labels[:,1:],labels[:,:-1])):
        changed=p!=q
        pairs.append(np.sort(np.column_stack([p[changed],q[changed]]),axis=1)-1)
    edges,lengths=np.unique(np.concatenate(pairs),axis=0,return_counts=True)
    lengths=lengths.astype(float)/w
    forbidden,clearances,layers=boundary_reserve(labels,boundary_layers,edges=edges)
    neighbors=[[] for _ in a];perimeter=np.zeros(n)
    for (i,j),length in zip(edges,lengths):
        neighbors[i].append((int(j),float(length)));neighbors[j].append((int(i),float(length)))
        perimeter[i]+=length;perimeter[j]+=length
    return Geometry(labels,a,moment(xx),moment(yy),moment(xx*xx+yy*yy+1/(6*w*w)),
        edges,lengths,forbidden,neighbors,perimeter,int(labels[h//2,w//2])-1,w,boundary_layers,clearances,layers)
