import numpy as np
from scipy import ndimage as ndi
from common.metrics import shape_metrics,boundary_connected,perimeters
from .geometry import L4


def measures(mask,g,state):
    cc,k=ndi.label(mask,L4);areas=np.sort(np.bincount(cc.ravel())[1:])[::-1]
    water=~mask & ~boundary_connected(~mask)
    _,holes=ndi.label(water,ndi.generate_binary_structure(2,2))
    y,x=np.nonzero(mask)
    center=np.array([x.mean()+.5,y.mean()+.5]);offset=float(np.linalg.norm(center-g.size/2))
    radius=float(np.sqrt(np.mean((x+.5-center[0])**2+(y+.5-center[1])**2)+1/6))
    result=shape_metrics(mask)
    result.update(fraction=float(mask.mean()),components_4=k,component_areas_km2=areas.tolist(),
        largest_component_fraction=float(areas[0]/areas.sum()),
        second_component_fraction=float(areas[1]/areas.sum()) if k>1 else 0.,
        center_xy_km=center.tolist(),center_offset_km=offset,spread_rms_km=radius,
        all_boundary_grid_km=perimeters(mask)[0],closed_water_cells=int(water.sum()),closed_water_components=holes,
        eligible_fraction=float(g.areas[~g.forbidden].sum()),forbidden_count=int(g.forbidden.sum()),
        forbidden_region_ids=(np.flatnonzero(g.forbidden)+1).tolist(),
        selected_region_count=int(state.sum()),initial_center_region_id=g.center_id+1,
        center_region_selected=bool(state[g.center_id]),fixed_ocean_band_km=0,
        excluded_boundary_layers=g.boundary_layers,
        maximum_partition_layer=int(g.region_layer.max()),
        eligible_minimum_clearance_km=float(g.region_clearance_km[~g.forbidden].min()),
        nearest_domain_edge_km=int(min(y.min(),x.min(),g.size-1-y.max(),g.size-1-x.max())),
        partition_area_min_km2=float(g.areas.min()*g.size**2),
        partition_area_max_km2=float(g.areas.max()*g.size**2))
    # Opening is diagnostic only. It never replaces the mask or contour artifact.
    distance=ndi.distance_transform_edt(mask)
    profile=[]
    for radius in (5.,10.,20.):
        core=distance>radius
        opened=ndi.distance_transform_edt(~core)<=radius if core.any() else core
        labels,count=ndi.label(opened,L4)
        sizes=np.bincount(labels.ravel())[1:]
        profile.append(dict(radius_km=radius,retained_fraction=float(opened.sum()/mask.sum()),
                            components=int(count),component_areas_km2=sorted(sizes.tolist(),reverse=True)))
    result['opening_diagnostic']=profile
    result['opening_interpretation']='geometric proxy for narrow parts; not a five-class classifier; mask unchanged'
    return result
