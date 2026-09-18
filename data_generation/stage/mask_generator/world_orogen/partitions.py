"""Planar adaptation of World Orogen's partition-growth and projection stages.

Adapted from js/plates.js and js/coarse-plates.js at upstream commit
cc2662b4edd52231c4f65d8765f3ef12cd82d9b7. GNU GPL version 3; see LICENSE.
All geometry changes relative to the spherical source are listed in README.md.
"""
from collections import deque
from dataclasses import dataclass, field
import math
import time

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import Delaunay, cKDTree

from common.io import array_sha256
from .config import Settings
from .noise import ParkMiller, SimplexNoise

L4 = ndi.generate_binary_structure(2, 1)


@dataclass
class PartitionMap:
    settings: Settings
    seed: int
    labels: np.ndarray = field(repr=False)  # 0 ocean band; IDs 1..P
    seeds_xy: np.ndarray = field(repr=False)
    coarse_points: np.ndarray = field(repr=False)
    coarse_labels: np.ndarray = field(repr=False)
    record: dict
    warp_x_km: np.ndarray = field(repr=False)
    warp_y_km: np.ndarray = field(repr=False)


def point_graph(seed, settings):
    side = settings.coarse_side
    rng = ParkMiller(seed+137)
    jitter = np.fromiter((rng.random() for _ in range(side*side*2)), float).reshape(side*side, 2)
    yy,xx = np.mgrid[:side,:side]
    points = (np.column_stack([xx.ravel()+.5, yy.ravel()+.5])+(jitter-.5)*settings.point_jitter)/side
    triangles = Delaunay(points).simplices
    edges = np.concatenate([triangles[:,[0,1]], triangles[:,[1,2]], triangles[:,[0,2]]])
    edges.sort(axis=1)
    edges = np.unique(edges, axis=0)
    adjacency = [[] for _ in points]
    for a,b in edges:
        adjacency[int(a)].append(int(b)); adjacency[int(b)].append(int(a))
    for neighbors in adjacency:
        neighbors.sort()
    return points, adjacency


def farthest_seeds(points, count, rng):
    chosen = [rng.integer(len(points))]
    minimum = np.sum((points-points[chosen[0]])**2, axis=1)
    minimum[chosen[0]] = -1
    for _ in range(1, count):
        # Stable node-index tie handling; random choice among the three farthest.
        order = np.lexsort((np.arange(len(points)), -minimum))
        pool = order[:min(3, len(points)-len(chosen))]
        pick = int(pool[rng.integer(len(pool))])
        chosen.append(pick)
        minimum = np.minimum(minimum, np.sum((points-points[pick])**2, axis=1))
        minimum[chosen] = -1
    return np.asarray(chosen, dtype=int)


def reconnect_graph(labels, adjacency, seeds):
    good = np.zeros(len(labels), bool)
    for pid, seed in enumerate(seeds):
        if labels[seed] != pid:
            raise RuntimeError("coarse seed ownership lost")
        good[seed] = True
        queue = [int(seed)]
        for node in queue:
            for other in adjacency[node]:
                if not good[other] and labels[other] == pid:
                    good[other] = True; queue.append(other)
    changes = int((~good).sum())
    queue = deque(int(i) for i in np.flatnonzero(good) if any(not good[j] for j in adjacency[i]))
    while queue:
        node = queue.popleft()
        for other in adjacency[node]:
            if not good[other]:
                labels[other] = labels[node]; good[other] = True; queue.append(other)
    if not good.all():
        raise RuntimeError("disconnected coarse graph")
    return changes


def grow_partitions(seed, settings, graph=None):
    points, adjacency = point_graph(seed, settings) if graph is None else graph
    count, total = settings.partition_count, len(points)
    rng, index_rng = ParkMiller(seed+.5), ParkMiller(seed)
    seeds = farthest_seeds(points, count, index_rng)
    low = float(np.clip((80-count)/60, 0, 1))
    rates, directions, strengths = [], [], []
    for _ in seeds:
        rate = .7-.4*low+rng.random()*rng.random()*(2.3+2.4*low)
        angle = 2*math.pi*rng.random()
        rates.append(rate); directions.append((math.cos(angle), math.sin(angle)))
        strengths.append(min(.85, rng.random()*(.15+.25*low+(.25+.25*low)/rate)))
    labels = np.full(total, -1, np.int16)
    labels[seeds] = np.arange(count)
    frontiers = [[int(node)] for node in seeds]
    areas = np.ones(count, int)
    remaining = total-count
    compact_weight, governor = .3-.22*low, 2+2*low
    expected_area = (total-count)/count
    while remaining:
        progress = False
        for pid in range(count):
            frontier = frontiers[pid]
            if not frontier:
                continue
            steps = max(1, math.ceil(rates[pid]*(.5+rng.random())))
            if areas[pid] > expected_area*governor:
                steps = max(1, math.ceil(steps*.5))
            # Planar squared-distance comparison to an equal-area radius.
            radius2 = (areas[pid]/total)/math.pi
            threshold2 = radius2*1.8**2
            sx,sy = points[seeds[pid]]
            direction_x,direction_y = directions[pid]
            strength = strengths[pid]
            for _ in range(steps):
                if not frontier:
                    break
                best_index, best_score = 0, -float("inf")
                for _ in range(min(len(frontier), 3+math.floor(strength*5))):
                    position = index_rng.integer(len(frontier))
                    node = frontier[position]
                    dx,dy = points[node,0]-sx, points[node,1]-sy
                    distance2 = dx*dx+dy*dy
                    alignment = (dx*direction_x+dy*direction_y)/(math.sqrt(distance2) or 1.)
                    penalty = max(0., distance2-threshold2)*compact_weight*4
                    score = alignment*strength+rng.random()*(1-strength*.5)-penalty
                    if score > best_score:
                        best_score, best_index = score, position
                node = frontier[best_index]
                frontier[best_index] = frontier[-1]; frontier.pop()
                for other in adjacency[node]:
                    if labels[other] == -1:
                        labels[other] = pid; frontier.append(other)
                        areas[pid] += 1; remaining -= 1; progress = True
        # A round may consume only interior frontier entries. Remaining frontier
        # entries can still reach unclaimed nodes in subsequent rounds.
        if not progress and remaining and not any(frontiers):
            raise RuntimeError("coarse growth stopped before covering its graph")
    is_seed = np.zeros(total, bool); is_seed[seeds] = True
    passes = int(math.floor(3-2*low+.5))
    smooth_changes = 0
    for iteration in range(passes):
        threshold = .4 if iteration == 0 else .5
        for node in range(total):
            if is_seed[node]:
                continue
            counts = np.bincount(labels[adjacency[node]], minlength=count)
            winner = int(counts.argmax())
            if counts[winner] > len(adjacency[node])*threshold and labels[node] != winner:
                labels[node] = winner; smooth_changes += 1
    reconnected = reconnect_graph(labels, adjacency, seeds)
    return points, labels, seeds, {"growth_rates": rates, "directions_xy": directions,
             "direction_strengths": strengths, "low_partition_factor": low,
             "compact_weight": compact_weight, "growth_governor": governor,
             "coarse_smoothing_passes": passes, "coarse_relabel_operations": smooth_changes,
             "coarse_connectivity_reassigned_points": reconnected}


def reconnect_pixels(labels, seed_pixels, count):
    """Keep each seed-connected region and reassign unconnected input fragments.

    This finishes the partition construction before any platform is selected.
    Every allowed cell remains assigned; no selected platform pixels are edited.
    """
    valid = labels > 0
    anchors_restored = 0
    for pid,(row,col) in enumerate(seed_pixels, 1):
        anchors_restored += int(labels[row,col] != pid)
        labels[row,col] = pid
    good = np.zeros(labels.shape, bool)
    for pid,(row,col) in enumerate(seed_pixels, 1):
        components, _ = ndi.label(labels == pid, L4)
        good |= components == int(components[row,col])
    orphan = valid & ~good
    changes = int(orphan.sum())
    labels[orphan] = -1
    boundary = good & ndi.binary_dilation(orphan, structure=L4)
    width = labels.shape[1]
    flat, inside = labels.ravel(), valid.ravel()
    queue = deque(map(int, np.flatnonzero(boundary)))
    while queue:
        node = queue.popleft()
        for other in (node-width, node+width, node-1, node+1):
            if 0 <= other < flat.size and inside[other] and flat[other] == -1:
                flat[other] = flat[node]; queue.append(other)
    if (labels[valid] <= 0).any():
        raise RuntimeError("raster partition reconnection failed")
    for pid,(row,col) in enumerate(seed_pixels, 1):
        if labels[row,col] != pid or ndi.label(labels == pid, L4)[1] != 1:
            raise RuntimeError(f"partition {pid} is not seed-connected")
    return {"seed_pixels_restored": anchors_restored, "raster_connectivity_reassigned_cells": changes,
            "raster_reassigned_fraction": changes/int(valid.sum())}


def generate_partitions(seed: int, settings: Settings, graph=None) -> PartitionMap:
    settings.validate()
    start = time.perf_counter()
    points, coarse_labels, seed_indices, growth = grow_partitions(seed, settings, graph)
    size, band = settings.size, settings.band
    inner = size-2*band
    seeds_xy = band+points[seed_indices]*inner
    yy,xx = np.mgrid[band:size-band,band:size-band].astype(float)+.5
    u,v = (xx-band)/inner,(yy-band)/inner
    low = growth["low_partition_factor"]
    coarse_km = inner/settings.coarse_side
    amplitude = coarse_km*(1.5+low)*settings.warp_multiplier
    dx,dy = np.zeros(u.shape),np.zeros(v.shape)
    noise = SimplexNoise(seed+999)
    for octave in range(4):
        frequency = 8*2**octave
        dx += amplitude*.5**octave*noise.noise3d(u*frequency, v*frequency, 0.)
        dy += amplitude*.5**octave*noise.noise3d(u*frequency+100, v*frequency+100, 100.)
    seed_distance = cKDTree(seeds_xy).query(np.column_stack([xx.ravel(), yy.ravel()]), workers=1)[0].reshape(u.shape)
    pin = 1-np.exp(-.5*(seed_distance/coarse_km)**2)
    edge_distance = np.minimum.reduce([xx-band, size-band-xx, yy-band, size-band-yy])
    taper = np.clip(edge_distance/(2*coarse_km), 0, 1)
    taper = taper*taper*(3-2*taper)
    dx *= pin*taper; dy *= pin*taper
    queries = np.column_stack([np.clip((xx+dx-band)/inner, 0, 1).ravel(),
                               np.clip((yy+dy-band)/inner, 0, 1).ravel()])
    owners = cKDTree(points).query(queries, workers=1)[1]
    labels = np.zeros((size, size), np.int16)
    labels[band:-band,band:-band] = coarse_labels[owners].reshape(u.shape)+1
    seed_pixels = np.floor(seeds_xy[:,[1,0]]).astype(int)
    cleanup = reconnect_pixels(labels, seed_pixels, settings.partition_count)
    record = {**growth, **cleanup, "coarse_points": len(points), "coarse_cell_scale_km": coarse_km,
              "warp_first_amplitude_km": amplitude, "warp_octaves": 4, "warp_base_frequency": 8,
              "warp_boundary_taper_km": 2*coarse_km, "warp_seed_pinning_scale_km": coarse_km,
              "maximum_query_displacement_km": float(np.hypot(dx,dy).max()),
              "seed_point_indices": seed_indices.tolist(), "seed_pixels_row_col": seed_pixels.tolist(),
              "seed_xy_km": seeds_xy.tolist(), "partition_labels_sha256": array_sha256(labels),
              "coarse_labels_sha256": array_sha256(coarse_labels), "wall_s": time.perf_counter()-start,
              "geometry_changes": ["planar jittered sampling and Delaunay adjacency", "2D growth direction",
                                   "planar squared-radius compactness", "seed-rooted partition reconnection",
                                   "seed and boundary pinning of projection noise"],
              "post_selection_pixel_edits": False}
    return PartitionMap(settings, seed, labels, seeds_xy, points, coarse_labels, record, dx, dy)
