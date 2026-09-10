"""T-time checks on a delivered elevation array.

Definitions mirror session D's ``array_statistics.py`` (D7): land is ``z > sea_level``; the ocean is the water
connected to the domain boundary (8-connectivity); land components use 4-connectivity; the focal landmass is the
largest land component; shoreline development uses the coastal envelope of the focal landmass (holes filled).

Acceptance rules recorded on 2026-09-09 (``architecture-dataflow.md`` 4.1.4/4.1.5, milestone 1):
* the outer ocean band (``ocean_band_km``, minimum 10 km) contains no land at time T, otherwise the sample is discarded;
* the land fraction must lie inside the occupancy preference band ``occupancy_band`` (default 0.50 to 0.60);
* the sea-land statistics are reported for comparison with the 34-landmass reference distributions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi

L4 = ndi.generate_binary_structure(2, 1)
S8 = ndi.generate_binary_structure(2, 2)


def boundary_connected(mask: np.ndarray, structure=S8) -> np.ndarray:
    seeds = np.zeros(mask.shape, bool)
    seeds[0, :] = mask[0, :]
    seeds[-1, :] = mask[-1, :]
    seeds[:, 0] = mask[:, 0]
    seeds[:, -1] = mask[:, -1]
    return ndi.binary_propagation(seeds, structure=structure, mask=mask)


def pca_shape(mask: np.ndarray, dx: float = 1.0) -> dict:
    y, x = np.nonzero(mask)
    if len(x) == 0:
        return {"pca_ratio": None, "pca_major_km": None, "pca_minor_km": None, "pca_azimuth_deg": None}
    pts = np.column_stack((x, y)).astype(float) * dx
    pts -= pts.mean(0)
    cov = pts.T @ pts / len(pts) + np.eye(2) * dx * dx / 12
    val, vec = np.linalg.eigh(cov)
    return {"pca_ratio": float(np.sqrt(val[1] / val[0])), "pca_major_km": float(4 * np.sqrt(val[1])),
            "pca_minor_km": float(4 * np.sqrt(val[0])), "pca_azimuth_deg": float(np.degrees(np.arctan2(vec[1, 1], vec[0, 1])) % 180)}


def perimeters(mask: np.ndarray, dx: float = 1.0) -> tuple[float, float]:
    a = np.pad(mask.astype(bool), 1)
    nv = np.count_nonzero(a[1:, :] != a[:-1, :])
    nh = np.count_nonzero(a[:, 1:] != a[:, :-1])
    nd1 = np.count_nonzero(a[1:, 1:] != a[:-1, :-1])
    nd2 = np.count_nonzero(a[1:, :-1] != a[:-1, 1:])
    return float((nv + nh) * dx), float(np.pi / 8 * (nv + nh + (nd1 + nd2) / np.sqrt(2)) * dx)


def coastline_metrics(land: np.ndarray, dx: float = 1.0) -> dict:
    envelope = ~boundary_connected(~land)
    edge, crofton = perimeters(envelope, dx)
    a = float(envelope.sum() * dx * dx)
    return dict(coastal_envelope_area_km2=a, coast_grid_edge_km=edge, coast_crofton4_km=crofton,
                shoreline_development_grid=edge / (2 * np.sqrt(np.pi * a)) if a else None,
                shoreline_development_crofton=crofton / (2 * np.sqrt(np.pi * a)) if a else None)


def min_enclosing_square_km(mask: np.ndarray, dx: float = 1.0, step_deg: int = 3) -> float:
    y, x = np.nonzero(mask)
    if len(x) == 0:
        return 0.0
    pts = np.column_stack((x, y)).astype(float) * dx
    best = np.inf
    for deg in range(0, 90, step_deg):
        th = np.deg2rad(deg)
        rot = pts @ np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
        ext = rot.max(0) - rot.min(0) + dx
        best = min(best, float(ext.max()))
    return best


def embayments(land: np.ndarray, dx: float = 1.0, radii=(5.0, 10.0, 20.0, 40.0), min_area: float = 100.0) -> list[dict]:
    """Inner-sea proxy: original ocean cells isolated after a disc closing of the land (D's definition)."""
    ocean = boundary_connected(~land)
    rows = []
    for r in radii:
        pad = int(np.ceil(r / dx)) + 3
        l = np.pad(land, pad, constant_values=False)
        dilation = ndi.distance_transform_edt(~l, sampling=dx) <= r
        closing = ndi.distance_transform_edt(dilation, sampling=dx) > r
        closed = closing[pad:-pad, pad:-pad]
        isolated = (~closed) & (~boundary_connected(~closed)) & ocean
        labels, n = ndi.label(isolated, structure=S8)
        areas = np.bincount(labels.ravel()) * dx * dx
        eligible = np.arange(1, n + 1)
        eligible = eligible[areas[eligible] >= min_area]
        water_area = float(np.isin(labels, eligible).sum() * dx * dx)
        rows.append(dict(radius_km=r, nominal_mouth_width_km=2 * r, min_area_km2=min_area, count=int(len(eligible)),
                         residual_water_area_km2=water_area, fraction_of_domain=water_area / (land.size * dx * dx)))
    return rows


def neighbour_components(land: np.ndarray, focal: np.ndarray, dx: float = 1.0, distance_km: float = 100.0) -> dict:
    labels, n = ndi.label(land, L4)
    focal_labels = np.unique(labels[focal])
    focal_labels = focal_labels[focal_labels > 0]
    dist = ndi.distance_transform_edt(~focal, sampling=dx)
    near = np.unique(labels[(dist <= distance_km) & land])
    near = near[near > 0]
    others = np.setdiff1d(near, focal_labels)
    areas = np.bincount(labels.ravel()) * dx * dx
    return dict(neighbour_count_1km2=int(len(others)), neighbour_count_10km2=int(sum(areas[k] >= 10 for k in others)),
                neighbour_count_100km2=int(sum(areas[k] >= 100 for k in others)), focal_components_4=int(len(focal_labels)))


@dataclass
class CheckConfig:
    sea_level_m: float = 0.0
    dx_km: float = 1.0
    ocean_band_km: float = 10.0
    occupancy_band: tuple[float, float] = (0.50, 0.60)
    apply_occupancy_rule: bool = True


def evaluate(z: np.ndarray, cfg: CheckConfig | None = None) -> dict:
    """Statistics plus the milestone-1 accept/discard decision for one elevation array (ny, nx)."""
    cfg = cfg or CheckConfig()
    z = np.asarray(z, dtype=float)
    if z.ndim != 2 or not np.isfinite(z).all():
        return {"accepted": False, "reasons": ["non-finite or non-2D array"]}
    dx = cfg.dx_km
    land = z > cfg.sea_level_m
    ocean = boundary_connected(~land)
    labs, n = ndi.label(land, L4)
    sizes = np.bincount(labs.ravel())
    sizes[0] = 0
    focal = labs == sizes.argmax() if n else np.zeros(z.shape, bool)
    b = max(1, int(round(cfg.ocean_band_km / dx)))
    band = np.ones(z.shape, bool)
    band[b:-b, b:-b] = False
    out = dict(shape=list(z.shape), dx_km=dx, sea_level_m=cfg.sea_level_m, land_area_km2=float(land.sum() * dx * dx),
               land_fraction=float(land.mean()), land_components_4=int(n), land_components_8=int(ndi.label(land, S8)[1]),
               closed_sub_sea_level_area_km2=float(((~land) & (~ocean)).sum() * dx * dx),
               land_reaches_boundary=bool(land[0, :].any() or land[-1, :].any() or land[:, 0].any() or land[:, -1].any()),
               land_in_ocean_band=bool(land[band].any()), ocean_band_km=cfg.ocean_band_km,
               maximum_boundary_elevation_m=float(max(z[0, :].max(), z[-1, :].max(), z[:, 0].max(), z[:, -1].max())),
               largest_component_fraction_of_land=float(sizes.max() / land.sum()) if n else None,
               largest_component_shape=pca_shape(focal, dx), largest_component_coast=coastline_metrics(focal, dx))
    if n:
        sq = min_enclosing_square_km(focal, dx)
        out["largest_component_min_square_km"] = sq
        out["largest_component_fill_ratio"] = float(sizes.max() * dx * dx / sq ** 2) if sq else None
        out["neighbours_100km"] = neighbour_components(land, focal, dx)
    out["embayment_proxy"] = embayments(land, dx)
    reasons = []
    if out["land_in_ocean_band"]:
        reasons.append(f"land inside the {cfg.ocean_band_km:g} km ocean band at T")
    lo, hi = cfg.occupancy_band
    out["occupancy_band"] = [lo, hi]
    if cfg.apply_occupancy_rule and not (lo <= out["land_fraction"] <= hi):
        reasons.append(f"land fraction {out['land_fraction']:.3f} outside the occupancy band {lo:.2f} to {hi:.2f}")
    out["accepted"] = not reasons
    out["reasons"] = reasons
    return out
