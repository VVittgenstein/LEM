"""The approved single-rule sequential selection of whole planar partitions.

No output-shape classes, island quotas, connectedness rejection or island-adding
phase. All unselected regions share the same softmax transition rule.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy.special import softmax

from common.numerics import rng_for


@dataclass
class RegionGeometry:
    areas: np.ndarray
    second_moments: np.ndarray
    adjacency: list[list[int]]
    centers_xy: np.ndarray
    domain_side_km: float
    preferred_center_xy: tuple[float, float]

    @property
    def count(self):
        return len(self.areas)


@dataclass
class SelectionResult:
    mask: np.ndarray = field(repr=False)
    order: list[int]  # one-based region IDs
    trace: list[dict]
    target_fraction: float
    statistics: dict
    geometry: RegionGeometry = field(repr=False)


def geometry_from_labels(labels, center_xy=(250.,250.), cell_km=1.):
    count = int(labels.max())
    if count <= 0:
        raise ValueError("no partition labels")
    yy,xx = np.mgrid[:labels.shape[0],:labels.shape[1]].astype(float)+.5
    xx *= cell_km; yy *= cell_km
    flat = labels.ravel()
    area = np.bincount(flat, minlength=count+1)[1:].astype(float)*cell_km**2
    if np.any(area <= 0):
        raise ValueError("region IDs must be contiguous and nonempty")
    distance2 = (xx-center_xy[0])**2+(yy-center_xy[1])**2+cell_km**2/6
    moments = np.bincount(flat, weights=distance2.ravel()*cell_km**2, minlength=count+1)[1:]
    centers = np.column_stack([np.bincount(flat,weights=xx.ravel()*cell_km**2,minlength=count+1)[1:]/area,
                               np.bincount(flat,weights=yy.ravel()*cell_km**2,minlength=count+1)[1:]/area])
    pairs = []
    for a,b in ((labels[1:,:],labels[:-1,:]), (labels[:,1:],labels[:,:-1])):
        edges = (a != b)&(a > 0)&(b > 0)
        pairs.append(np.column_stack([a[edges], b[edges]]))
    edges = np.concatenate(pairs)
    edges.sort(axis=1)
    edges = np.unique(edges, axis=0)
    adjacency = [[] for _ in range(count)]
    for a,b in edges:
        adjacency[int(a)-1].append(int(b)-1); adjacency[int(b)-1].append(int(a)-1)
    return RegionGeometry(area,moments,adjacency,centers,labels.shape[1]*cell_km,tuple(center_xy))


def component_state(selected, geometry):
    owners = np.full(geometry.count, -1, int)
    masses = []
    for region in np.flatnonzero(selected):
        if owners[region] >= 0:
            continue
        component = len(masses)
        owners[region] = component
        queue = [int(region)]
        area = 0.
        for node in queue:
            area += geometry.areas[node]
            for other in geometry.adjacency[node]:
                if selected[other] and owners[other] < 0:
                    owners[other] = component; queue.append(other)
        masses.append(area)
    return owners, np.asarray(masses)


def candidate_probabilities(selected, geometry, center_weight, connection_weight):
    owners,masses = component_state(selected,geometry)
    if not len(masses):
        raise ValueError("selection must start from a nonempty region")
    candidates = np.flatnonzero(~selected)
    if not len(candidates):
        raise ValueError("no unselected candidates")
    area = float(geometry.areas[selected].sum())
    moment = float(geometry.second_moments[selected].sum())
    sum_squares = float(masses @ masses)
    current_q = sum_squares/area**2
    current_r = moment/(area*geometry.domain_side_km**2)
    next_q, touch = [], []
    for region in candidates:
        adjacent_components = sorted({int(owners[j]) for j in geometry.adjacency[region] if owners[j] >= 0})
        joined = masses[adjacent_components]
        new_squares = sum_squares-float(joined @ joined)+(geometry.areas[region]+float(joined.sum()))**2
        next_q.append(new_squares/(area+geometry.areas[region])**2)
        touch.append(bool(adjacent_components))
    next_q = np.asarray(next_q)
    next_r = (moment+geometry.second_moments[candidates])/((area+geometry.areas[candidates])*geometry.domain_side_km**2)
    scores = connection_weight*(next_q-current_q)-center_weight*(next_r-current_r)
    probabilities = softmax(scores)
    if not np.isfinite(probabilities).all() or np.any(probabilities <= 0):
        raise ValueError("weights cause nonfinite or underflowed candidate probabilities")
    return {"candidates": candidates, "probabilities": probabilities, "scores": scores,
            "next_q": next_q, "next_r": next_r, "current_q": current_q, "current_r": current_r,
            "touches_selected": np.asarray(touch), "current_area": area}


def select_whole_regions(geometry, root, target_area, rng, center_weight=24., connection_weight=8., record_trace=True):
    if not 0 <= root < geometry.count or not 0 < target_area <= geometry.areas.sum():
        raise ValueError("invalid root or target area")
    if not np.isfinite([center_weight,connection_weight]).all() or min(center_weight,connection_weight) < 0:
        raise ValueError("selection weights must be finite and nonnegative")
    selected = np.zeros(geometry.count, bool);selected[root] = True
    order = [int(root)+1]
    area = float(geometry.areas[root])
    initial_r = float(geometry.second_moments[root]/(area*geometry.domain_side_km**2))
    trace = [{"step": 0, "chosen_region": int(root)+1, "chosen_probability": 1.,
              "selected_regions": order.copy(), "area_km2": area, "fraction": area/geometry.domain_side_km**2,
              "R": initial_r, "Q": 1., "reason": "region containing preferred center"}]
    maximum_probability_error, minimum_probability = 0.,1.
    while area < target_area-1e-9:
        candidate = candidate_probabilities(selected,geometry,center_weight,connection_weight)
        probs = candidate["probabilities"]
        maximum_probability_error = max(maximum_probability_error,abs(float(probs.sum())-1))
        minimum_probability = min(minimum_probability,float(probs.min()))
        cumulative = np.cumsum(probs);cumulative[-1] = 1.
        random_value = float(rng.random())
        choice = int(np.searchsorted(cumulative,random_value))
        region = int(candidate["candidates"][choice])
        selected[region] = True;order.append(region+1)
        area += float(geometry.areas[region])
        if record_trace:
            trace.append({"step": len(order)-1, "chosen_region": region+1, "random_uniform": random_value,
                "chosen_probability": float(probs[choice]), "selected_regions": order.copy(),
                "area_km2": area, "fraction": area/geometry.domain_side_km**2,
                "R": float(candidate["next_r"][choice]), "Q": float(candidate["next_q"][choice]),
                "candidate_ids": (candidate["candidates"]+1).tolist(),
                "probabilities": probs.tolist(), "scores": candidate["scores"].tolist(),
                "candidate_R": candidate["next_r"].tolist(), "candidate_Q": candidate["next_q"].tolist(),
                "touches_selected_diagnostic": candidate["touches_selected"].tolist()})
    owners,masses = component_state(selected,geometry)
    radius2 = float(geometry.second_moments[selected].sum()/(area*geometry.domain_side_km**2))
    centroid = (geometry.centers_xy[selected]*geometry.areas[selected,None]).sum(axis=0)/area
    shift = float(np.linalg.norm(centroid-np.asarray(geometry.preferred_center_xy)))
    statistics = {"area_km2": area, "fraction": area/geometry.domain_side_km**2,
                  "target_area_km2": target_area, "overshoot_area_km2": area-target_area,
                  "area_before_last_region_km2": area-float(geometry.areas[order[-1]-1]),
                  "selected_region_count": len(order), "region_component_count": len(masses),
                  "Q": float(masses @ masses/area**2), "R": radius2,
                  "all_land_centroid_xy_km": centroid.tolist(), "centroid_offset_km": shift,
                  "rms_distance_to_preferred_center_km": float(np.sqrt(radius2)*geometry.domain_side_km),
                  "rms_distance_about_land_centroid_km": float(np.sqrt(max(0.,radius2*geometry.domain_side_km**2-shift**2))),
                  "largest_component_fraction_graph": float(masses.max()/area),
                  "root_component_fraction": float(masses[owners[root]]/area),
                  "maximum_probability_sum_error": maximum_probability_error,
                  "minimum_candidate_probability": minimum_probability}
    return selected,order,trace,statistics


def generate_mask(partitions, target_fraction=None, record_trace=True):
    settings = partitions.settings
    if target_fraction is None:
        target_fraction = float(rng_for(partitions.seed,"fraction").uniform(.5,.6))
    if not .5 <= target_fraction <= .6:
        raise ValueError("target preference must be in [0.50,0.60]")
    center = (settings.center_x_km,settings.center_y_km)
    geometry = geometry_from_labels(partitions.labels,center,settings.cell_km)
    row,col = int(np.floor(center[1]/settings.cell_km)),int(np.floor(center[0]/settings.cell_km))
    root = int(partitions.labels[row,col])-1
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([partitions.seed,303])))
    selected,order,trace,statistics = select_whole_regions(geometry,root,target_fraction*settings.size**2,
        rng,settings.center_weight,settings.connection_weight,record_trace)
    lookup = np.r_[False,selected]
    mask = lookup[partitions.labels]
    if int(mask.sum()) != int(statistics["area_km2"]):
        raise RuntimeError("region areas and raster union disagree")
    return SelectionResult(mask,order,trace,target_fraction,statistics,geometry)
