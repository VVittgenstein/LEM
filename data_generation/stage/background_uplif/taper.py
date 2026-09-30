"""Platform-relative partition rings and continuous interpolation of their weights."""
from collections import deque
import numpy as np
from scipy import ndimage as ndi

L4 = ndi.generate_binary_structure(2, 1)
WEIGHTS = {"platform_interior": 1., "platform_outer": .75,
           "sea_1": .50, "sea_2": .25, "sea_3_and_beyond": 0.}
SMOOTH_SIGMA_KM = 1.0


def partition_rings(labels, mask):
    n = int(labels.max())
    if labels.shape != mask.shape or labels.min() != 1:
        raise ValueError("Matching masks and positive partition labels required")
    total = np.bincount(labels.ravel(), minlength=n+1)[1:]
    land_count = np.bincount(labels[mask], minlength=n+1)[1:]
    if np.any(total == 0) or not np.all((land_count == 0) | (land_count == total)):
        raise ValueError("Whole, contiguous-ID partitions required")
    state = land_count > 0
    pairs = []
    for p, q in ((labels[1:], labels[:-1]), (labels[:,1:], labels[:,:-1])):
        hit = p != q
        pairs.append(np.sort(np.column_stack([p[hit], q[hit]]), axis=1)-1)
    edges = np.unique(np.concatenate(pairs), axis=0)
    neighbors = [[] for _ in range(n)]
    for i,j in edges:
        neighbors[i].append(int(j)); neighbors[j].append(int(i))
    # "Outer" means exterior-connected water. Enclosed holes do not create new exterior rings.
    water = ~mask
    seeds = np.zeros_like(water)
    seeds[0] = water[0]; seeds[-1] = water[-1]
    seeds[:,0] = water[:,0]; seeds[:,-1] = water[:,-1]
    exterior = ndi.binary_propagation(seeds, structure=L4, mask=water)
    ext_region = np.bincount(labels[exterior], minlength=n+1)[1:] > 0
    outer_land = np.array([state[i] and any(ext_region[j] for j in neighbors[i]) for i in range(n)])
    ring = np.full(n, -2, np.int16)  # -2 interior platform, -1 outer platform, 0 enclosed water
    ring[~state] = 0
    ring[outer_land] = -1
    q = deque()
    for i in np.flatnonzero(ext_region):
        if any(state[j] for j in neighbors[i]):
            ring[i] = 1; q.append(int(i))
    while q:
        i = q.popleft()
        for j in neighbors[i]:
            if ext_region[j] and ring[j] == 0:
                ring[j] = ring[i]+1; q.append(j)
    if np.any(ext_region & (ring <= 0)):
        raise ValueError("Exterior sea has no route to the platform")
    weights = np.ones(n)
    weights[outer_land] = .75
    weights[ring == 1] = .5
    weights[ring == 2] = .25
    weights[ring >= 3] = 0.
    return ring, weights, {"outer_platform_regions": int(outer_land.sum()),
                          "sea_ring_counts": {str(k): int((ring==k).sum()) for k in np.unique(ring[ring>0])},
                          "enclosed_water_regions": np.flatnonzero((ring==0)&~state).astype(int).tolist(),
                          "hole_policy": "enclosed holes retain background weight 1; only exterior contours seed rings"}


def make_taper(labels, mask):
    ring, region_weights, info = partition_rings(labels, mask)
    hard = region_weights[labels-1]
    # Compact 4 km support keeps fixed interior values beyond transition fringes.
    smooth = ndi.gaussian_filter(hard, SMOOTH_SIGMA_KM, mode="nearest", truncate=4.)
    zero = ring[labels-1] >= 3
    # Finish the outer transition inside ring 2. Ring 3 and beyond stay exactly zero.
    if zero.any():
        distance = np.maximum(ndi.distance_transform_edt(~zero)-.5, 0.)
        t = np.clip(distance/4., 0., 1.)
        gate = t*t*t*(10.-15.*t+6.*t*t)
        smooth *= gate
        smooth[zero] = 0.
    smooth = np.clip(smooth, 0., 1.)
    info.update({"region_weights": WEIGHTS, "transition_sigma_km": SMOOTH_SIGMA_KM,
                 "transition_support_km": 4., "max_change_from_ring_baseline": float(abs(smooth-hard).max()),
                 "outer_zero_policy": "last 4 km before ring 3 use a quintic gate; ring 3 and beyond exactly zero",
                 "interpretation": "weights are ring baselines; shared-edge transition fringes interpolate continuously",
                 "domain_edge_max_weight": float(max(smooth[0].max(),smooth[-1].max(),smooth[:,0].max(),smooth[:,-1].max()))})
    return smooth, hard, ring[labels-1], info
