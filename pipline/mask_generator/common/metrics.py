"""Measurements of the full platform mask. Largest-component results are separate.

Land uses four neighbours, water uses eight. Coastline measurements fill closed
water for measurement only; the actual mask is never edited.
"""
import numpy as np
from scipy import ndimage as ndi

from .config import BAND, DX_KM

L4 = ndi.generate_binary_structure(2, 1)
S8 = ndi.generate_binary_structure(2, 2)


def boundary_connected(water: np.ndarray) -> np.ndarray:
    seeds = np.zeros_like(water, dtype=bool)
    seeds[0] = water[0]
    seeds[-1] = water[-1]
    seeds[:, 0] = water[:, 0]
    seeds[:, -1] = water[:, -1]
    return ndi.binary_propagation(seeds, structure=S8, mask=water)


def pca_shape(mask: np.ndarray, dx: float = DX_KM) -> dict:
    y, x = np.nonzero(mask)
    if not len(x):
        raise ValueError("empty mask")
    pts = np.column_stack([x + 0.5, y + 0.5]).astype(np.float64) * dx
    center = pts.mean(0)
    pts -= center
    covariance = pts.T @ pts / len(pts) + np.eye(2) * dx * dx / 12.0
    values, vectors = np.linalg.eigh(covariance)
    return {"axis_ratio": float(np.sqrt(values[1] / values[0])),
            "major_axis_km": float(4 * np.sqrt(values[1])), "minor_axis_km": float(4 * np.sqrt(values[0])),
            "axis_angle_deg": float(np.degrees(np.arctan2(vectors[1, 1], vectors[0, 1])) % 180),
            "center_x_km": float(center[0]), "center_y_km": float(center[1])}


def perimeters(mask: np.ndarray, dx: float = DX_KM) -> tuple[float, float]:
    padded = np.pad(mask.astype(bool), 1)
    vertical = np.count_nonzero(padded[1:] != padded[:-1])
    horizontal = np.count_nonzero(padded[:, 1:] != padded[:, :-1])
    diagonal1 = np.count_nonzero(padded[1:, 1:] != padded[:-1, :-1])
    diagonal2 = np.count_nonzero(padded[1:, :-1] != padded[:-1, 1:])
    grid = (vertical + horizontal) * dx
    crofton = np.pi / 8.0 * (vertical + horizontal + (diagonal1 + diagonal2) / np.sqrt(2)) * dx
    return float(grid), float(crofton)


def shape_metrics(mask: np.ndarray, dx: float = DX_KM) -> dict:
    mask = np.asarray(mask, dtype=bool)
    pca = pca_shape(mask, dx)
    envelope = ~boundary_connected(~mask)
    area = float(mask.sum() * dx * dx)
    coast_area = float(envelope.sum() * dx * dx)
    grid, crofton = perimeters(envelope, dx)
    return {"area_km2": area, "coastal_envelope_area_km2": coast_area, **pca,
            "coast_grid_km": grid, "coast_crofton_km": crofton,
            "shoreline_development": crofton / (2 * np.sqrt(np.pi * coast_area)),
            "shoreline_development_grid": grid / (2 * np.sqrt(np.pi * coast_area)),
            "measurement_scope": "all platform cells; closed water filled for coastline measurement only"}


def _longest_run(values: np.ndarray) -> int:
    padded = np.r_[False, values, False].astype(np.int8)
    diff = np.diff(padded)
    starts, ends = np.flatnonzero(diff == 1), np.flatnonzero(diff == -1)
    return int((ends - starts).max()) if len(starts) else 0


def inner_sea_proxy(mask: np.ndarray, dx: float = DX_KM) -> list[dict]:
    original_ocean = boundary_connected(~mask)
    results = []
    for radius in (5.0, 10.0, 20.0, 40.0):
        pad = int(np.ceil(radius / dx)) + 3
        padded = np.pad(mask, pad)
        dilated = ndi.distance_transform_edt(~padded, sampling=dx) <= radius
        closed = (ndi.distance_transform_edt(dilated, sampling=dx) > radius)[pad:-pad, pad:-pad]
        isolated = ~closed & ~boundary_connected(~closed) & original_ocean
        labels, count = ndi.label(isolated, S8)
        areas = np.bincount(labels.ravel()) * dx * dx
        ids = np.arange(1, count + 1)
        ids = ids[areas[ids] >= 100.0]
        results.append({"nominal_mouth_width_km": 2 * radius, "minimum_area_km2": 100.0,
                        "count": int(len(ids)), "residual_water_area_km2": float(areas[ids].sum())})
    return results


def full_metrics(mask: np.ndarray, band: int = BAND) -> dict:
    result = shape_metrics(mask)
    labels, count = ndi.label(mask, L4)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest = labels == int(sizes.argmax())
    sea = boundary_connected(~mask)
    closed, n_closed = ndi.label(~mask & ~sea, S8)
    y, x = np.nonzero(mask)
    pts = np.column_stack([x, y]).astype(float)
    pts -= pts.mean(0)
    min_square = float("inf")
    for angle in range(0, 90, 3):
        t = np.deg2rad(angle)
        rotated = pts @ np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        # A rotated unit cell extends |cos(theta)|+|sin(theta)| across either axis.
        cell_extent = abs(np.cos(t)) + abs(np.sin(t))
        min_square = min(min_square, float(np.ptp(rotated, axis=0).max() + cell_extent))
    contact = {"bottom": mask[band, band:-band], "top": mask[-band - 1, band:-band],
               "left": mask[band:-band, band], "right": mask[band:-band, -band - 1]}
    band_mask = np.ones(mask.shape, bool)
    band_mask[band:-band, band:-band] = False
    cx, cy = result["center_x_km"], result["center_y_km"]
    yy, xx = np.mgrid[0:mask.shape[0], 0:mask.shape[1]].astype(float) + 0.5
    radius = np.sqrt(mask.sum() / np.pi)
    circle = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2
    square_half = np.sqrt(mask.sum()) / 2.0
    best_square_iou = 0.0
    for degrees in range(0, 90, 3):
        theta = np.deg2rad(degrees)
        xr = (xx - cx) * np.cos(theta) + (yy - cy) * np.sin(theta)
        yr = -(xx - cx) * np.sin(theta) + (yy - cy) * np.cos(theta)
        square = (np.abs(xr) <= square_half) & (np.abs(yr) <= square_half)
        best_square_iou = max(best_square_iou, float((mask & square).sum() / (mask | square).sum()))
    result.update({"shape": list(mask.shape), "dtype": str(mask.dtype), "cell_km": DX_KM,
                   "fraction": float(mask.mean()), "components_4": int(count),
                   "components_8": int(ndi.label(mask, S8)[1]),
                   "components_ge_10km2": int(np.count_nonzero(sizes[1:] >= 10)),
                   "components_ge_100km2": int(np.count_nonzero(sizes[1:] >= 100)),
                   "largest_component_fraction": float(sizes.max() / mask.sum()),
                   "largest_component_metrics": shape_metrics(largest),
                   "closed_water_cells": int((closed > 0).sum()), "closed_water_components": int(n_closed),
                   "minimum_square_km": min_square, "fill_ratio": float(mask.sum() / min_square ** 2),
                   "ocean_band_cells": band, "cells_in_ocean_band": int(mask[band_mask].sum()),
                   "inner_band_contact_cells": {k: int(v.sum()) for k, v in contact.items()},
                   "longest_straight_band_contact_km": {k: _longest_run(v) for k, v in contact.items()},
                   "equal_area_circle_iou": float((mask & circle).sum() / (mask | circle).sum()),
                   "equal_area_square_iou": best_square_iou,
                   "inner_sea_proxy": inner_sea_proxy(mask),
                   "inner_sea_proxy_status": "几何代理，地学含义尚未验证"})
    return result
