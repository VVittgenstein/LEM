"""Exact outer cell edges and a single mean offshore observation distance.

Array row zero is at the bottom of the map, as in mask_generator.
Internal mask holes are retained, but are excluded from the outer-coast denominator.
"""
from dataclasses import dataclass
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
import bootstrap as b


@dataclass
class Coast:
    xy: np.ndarray
    normals: np.ndarray
    sea_regions: np.ndarray
    ring_ids: np.ndarray
    ring_slices: list
    ring_s_km: np.ndarray


def load_sample(seed):
    path = b.MASK_BATCH / f'seed{seed}'
    mask = np.load(path / 'mask.npy', allow_pickle=False)
    labels = np.load(path / 'partitions.npy', allow_pickle=False)
    cfg = b.read_json(path / 'config.json')
    settings = cfg.get('settings', cfg)
    if mask.shape != (500, 500) or mask.dtype != bool or labels.shape != mask.shape:
        raise ValueError('Selected 500x500 bool masks and matching partitions are required')
    if settings['partition_count'] != 512 or settings['boundary_layers'] != 3:
        raise ValueError('Input is not the selected 512-partition / 3-layer profile')
    g = b.geometry(labels, boundary_layers=3)
    counts = np.bincount(labels[mask], minlength=513)[1:]
    all_counts = np.bincount(labels.ravel(), minlength=513)[1:]
    if not np.all((counts == 0) | (counts == all_counts)):
        raise ValueError('Platform mask splits an input partition')
    state = counts > 0
    if np.any(state & g.forbidden):
        raise ValueError('Platform enters its reserved partitions')
    contours = b.read_json(path / 'contours.json')
    coast = outer_edges(contours, labels, mask)
    return dict(seed=seed, path=path, mask=mask, labels=labels, geometry=g,
                platform_state=state, contours=contours, coast=coast, settings=settings)


def outer_edges(contours, labels, mask):
    points, normals, owners, ring_ids, ss, slices = [], [], [], [], [], []
    start = 0
    for rid, component in enumerate(contours['components']):
        ring = np.asarray(orient(Polygon(component['outer']), sign=1).exterior.coords, float)
        p, n = [], []
        for a, z in zip(ring[:-1], ring[1:]):
            delta = z-a
            length = float(np.linalg.norm(delta))
            steps = int(round(length))
            if steps == 0:
                continue
            if not np.isclose(length, steps) or np.count_nonzero(np.abs(delta)>1e-8) != 1:
                raise ValueError('Expected exact 1 km orthogonal cell-edge contours')
            tangent = delta/length
            outward = np.array([tangent[1], -tangent[0]])
            p.extend(a+(np.arange(steps)+.5)[:, None]*tangent)
            n.extend(np.broadcast_to(outward, (steps, 2)))
        p, n = np.asarray(p), np.asarray(n)
        side = np.floor(p+1e-4*n).astype(int)
        x, y = side.T
        if np.any((side<0)|(side>=500)) or mask[y,x].any():
            raise ValueError('Outer edge does not face a valid unselected cell')
        points.append(p); normals.append(n); owners.append(labels[y,x]-1)
        ring_ids.append(np.full(len(p),rid,int)); ss.append(np.arange(len(p))+.5)
        slices.append(slice(start,start+len(p))); start+=len(p)
    return Coast(np.concatenate(points),np.concatenate(normals),np.concatenate(owners),
                 np.concatenate(ring_ids),slices,np.concatenate(ss))


def measure_width(sample):
    """Outward-normal contiguous water width, sampled every 0.5 km.

Normals use a chord across five consecutive edge midpoints (4 km arc span),
falling back to the exact edge normal if the
first offshore sample is inside the platform. Stop at another platform edge
or the domain boundary. Each cell edge represents one kilometre of perimeter.
"""
    coast, mask = sample['coast'], sample['mask']
    widths = np.empty(len(coast.xy)); normal_out = np.empty_like(coast.normals)
    stops = np.empty(len(widths), dtype='U16'); fallback_count = 0
    for sl in coast.ring_slices:
        p = coast.xy[sl]
        # Circular positions are one kilometre apart; five-edge chord smoothing.
        tangent = np.roll(p,-2,axis=0)-np.roll(p,2,axis=0)
        norm = np.linalg.norm(tangent,axis=1)
        n = np.column_stack([tangent[:,1],-tangent[:,0]]) / np.maximum(norm[:,None],1e-12)
        probe = np.floor(p+.25*n).astype(int)
        good = np.all((probe>=0)&(probe<500),axis=1)
        ok = good.copy(); ok[good] &= ~mask[probe[good,1],probe[good,0]]
        ok &= norm>1e-8
        n[~ok] = coast.normals[sl][~ok]
        fallback_count += int((~ok).sum())
        normal_out[sl] = n
        for j,(point,normal) in enumerate(zip(p,n),sl.start):
            bounds=[]
            for axis in range(2):
                if normal[axis]>1e-10: bounds.append((500-point[axis])/normal[axis])
                elif normal[axis]<-1e-10: bounds.append(-point[axis]/normal[axis])
            end = min(bounds)
            distances = np.arange(.25,end,.5)
            at = np.floor(point+distances[:,None]*normal).astype(int)
            hit = mask[at[:,1],at[:,0]]
            if hit.any():
                widths[j] = max(.0,float(distances[np.argmax(hit)])-.25)
                stops[j] = 'platform'
            else:
                widths[j] = float(end); stops[j]='domain_edge'
    row=dict(seed=sample['seed'],outer_coast_km=len(widths),mean_width_km=float(widths.mean()),
             minimum_width_km=float(widths.min()),maximum_width_km=float(widths.max()),
             normal_fallbacks=fallback_count,stop_at_platform=int((stops=='platform').sum()),
             stop_at_domain_edge=int((stops=='domain_edge').sum()),ray_step_km=.5)
    return row,dict(xy_km=coast.xy,normals=normal_out,width_km=widths,ring_id=coast.ring_ids,termination=stops)


def circular_runs(values):
    a=np.asarray(values); n=len(a)
    if not n:return []
    starts=np.flatnonzero(a!=np.roll(a,1))
    if not len(starts):return [dict(start=0,count=n,label=int(a[0]))]
    return [dict(start=int(s),count=int((starts[(i+1)%len(starts)]-s)%n),label=int(a[s]))
            for i,s in enumerate(starts)]


def known_binary_runs(values, spacing, lmin=10.):
    """Merge short known binary runs only when both neighbors are known.

Unknown (-1) remains a barrier; runs touching it are censored and omitted
from complete-length fitting. A whole, known ring has its full perimeter.
"""
    a=np.asarray(values,dtype=np.int8).copy(); merges=0
    while lmin>0:
        runs=circular_runs(a)
        if len(runs)==1:break
        eligible=[]
        for i,r in enumerate(runs):
            prev,nxt=runs[i-1],runs[(i+1)%len(runs)]
            if r['label']>=0 and prev['label']>=0 and nxt['label']>=0 and r['count']*spacing<lmin:
                eligible.append((r['count'],r['start'],i))
        if not eligible:break
        _,_,i=min(eligible); r=runs[i]; prev,nxt=runs[i-1],runs[(i+1)%len(runs)]
        label=prev['label'] if prev['count']>=nxt['count'] else nxt['label']
        a[(np.arange(r['count'])+r['start'])%len(a)]=label; merges+=1
    runs=circular_runs(a); out=[]
    for i,r in enumerate(runs):
        if r['label']<0:continue
        censored=len(runs)>1 and (runs[i-1]['label']<0 or runs[(i+1)%len(runs)]['label']<0)
        out.append(dict(r,length_km=r['count']*spacing,censored=bool(censored)))
    return a,out,merges


def lengths_on_coast(coast, deep_by_region):
    label=deep_by_region[coast.sea_regions].astype(np.int8)
    rows=[]
    for rid,sl in enumerate(coast.ring_slices):
        for r in circular_runs(label[sl]):
            rows.append(dict(ring_id=rid,start_km=r['start'],length_km=r['count'],
                             environment='deep' if r['label'] else 'shallow'))
    return label,rows
