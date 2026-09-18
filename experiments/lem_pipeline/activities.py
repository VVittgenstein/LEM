"""Class 2 + class 5: geological activities, their placement and the uplift schedule.

Systems (yZz 2026-09-09): every sample has all five land-forming activity types; counting is by independent systems
(convergent, rift, regional, strike-slip), appended parts follow the rules (foreland basin and thrust faults with the
belt, shoulders and normal faults with the rift, pull-apart basins with strike-slip bends, thermal subsidence after
rifting). Hasterok proxies (session G) give only count upper bounds, geometry, strike angles and placement distances;
rates come from H (thermochronology, GEM faults) or, where no distribution exists, from the class-2 case ranges
(uniform, or log-uniform when the range spans an order of magnitude). Every sampled quantity carries an evidence label.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
from scipy import ndimage as ndi

from .distributions import QuantileTable, sample_range
from .driver import Epoch

ASSUMPTION = "尚待验证的假设"
CALC = "本项目借鉴或合成改造"
DIRECT = "来源直接给出"

# H-003 thermochronology 2 to 0 Ma, n = 4000 (mm/yr) — quantile points p05, p25, median, p75, p95, max
CONVERGENT_RATE = QuantileTable((0.05, 0.25, 0.5, 0.75, 0.95, 1.0), (0.237e-3, 0.380e-3, 0.532e-3, 0.800e-3, 2.08e-3, 6.63e-3), 4000, "H-003 2-0 Ma")
REVERSE_FAULT_RATE = QuantileTable((0.05, 0.25, 0.5, 0.75, 0.95, 1.0), (0.0, 0.183e-3, 0.455e-3, 0.826e-3, 1.89e-3, 12.2e-3), 949, "GEM reverse")
NORMAL_FAULT_RATE = QuantileTable((0.05, 0.25, 0.5, 0.75, 0.95, 1.0), (0.0765e-3, 0.215e-3, 0.520e-3, 0.996e-3, 2.99e-3, 15.2e-3), 1039, "GEM normal (magnitude)")
# G orogenic belt geometry (34): clipped long-edge sum, coast distance of pieces, coast angle (±25 km window)
BELT_LENGTH_KM = QuantileTable((0.05, 0.5, 0.95), (106.0, 209.0, 402.0), 17, "G clipped long edge sum")
BELT_COAST_DIST_KM = QuantileTable((0.05, 0.5, 0.95), (1.94, 9.43, 24.9), 19, "G piece coast distance")
BELT_COAST_ANGLE_DEG = QuantileTable((0.05, 0.5, 0.95), (0.46, 16.3, 54.3), 17, "G coast angle ±25 km")
UPLIFT_CAP = 15e-3
SUBSIDENCE_CAP = -4.7e-3
MAX_SUBSIDENCE_TOTAL_M = 8000.0  # B: basin sediment thickness 2 to 8 km (assumption as a cumulative cap)


@dataclass
class Activity:
    kind: str
    system: str
    t_start: float
    t_end: float
    rate_field: np.ndarray  # m/yr, positive up
    params: dict
    evidence: dict = field(default_factory=dict)


def _line_distance(shape: tuple[int, int], x0: float, y0: float, azimuth_deg: float, dx_km: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Signed perpendicular distance (km) to a line through (x0, y0) with the given azimuth, and along-line coordinate."""
    ny, nx = shape
    y, x = np.mgrid[0:ny, 0:nx].astype(float) * dx_km
    th = np.deg2rad(azimuth_deg)
    ux, uy = np.cos(th), np.sin(th)
    along = (x - x0) * ux + (y - y0) * uy
    perp = -(x - x0) * uy + (y - y0) * ux
    return perp, along


def _band_profile(perp: np.ndarray, along: np.ndarray, width_km: float, length_km: float, profile: str = "gaussian") -> np.ndarray:
    half = width_km / 2.0
    inside_len = np.abs(along) <= length_km / 2.0
    if profile == "gaussian":
        w = np.exp(-0.5 * (perp / (half / 2.0)) ** 2) * (np.abs(perp) <= half)
    else:
        w = (np.abs(perp) <= half).astype(float)
    taper = np.clip(1.0 - (np.abs(along) - length_km / 2.0) / 30.0, 0.0, 1.0)  # 30 km end taper (assumption)
    return w * np.where(inside_len, 1.0, taper)


@dataclass
class OutlineMargins:
    """Active/passive labels along the outline (F 100 km rule; unclassified redistributed by the classified share)."""
    contour: np.ndarray
    u_km: np.ndarray
    label: np.ndarray  # 'active' or 'passive' per outline cell

    @classmethod
    def sample(cls, rng: np.random.Generator, contour: np.ndarray, dx_km: float, p_active: float = 0.373,
               active_len=QuantileTable((0.05, 0.25, 0.5, 0.75, 0.95), (3.0, 9.0, 56.0, 264.0, 1328.0), 18, "F active segments"),
               passive_len=QuantileTable((0.05, 0.25, 0.5, 0.75, 0.95), (1.0, 4.0, 7.0, 28.0, 598.0), 146, "F passive segments")):
        steps = np.hypot(*(np.diff(np.vstack([contour, contour[:1]]), axis=0).T.astype(float))) * dx_km
        u = np.concatenate([[0.0], np.cumsum(steps)[:-1]])
        perimeter = float(steps.sum())
        labels = np.empty(len(contour), dtype=object)
        pos = float(rng.uniform(0, perimeter))
        filled = 0.0
        while filled < perimeter:
            lab = "active" if rng.random() < p_active else "passive"
            L = float((active_len if lab == "active" else passive_len).sample(rng))
            L = max(L, 5.0)
            sel = ((u - pos) % perimeter) < L
            labels[sel & (labels == None)] = lab  # noqa: E711
            pos = (pos + L) % perimeter
            filled += L
        labels[labels == None] = "passive"  # noqa: E711
        return cls(contour, u, labels.astype(str))


def _coast_tangent(contour: np.ndarray, idx: int, dx_km: float, window: int = 12) -> float:
    n = len(contour)
    a = contour[(idx - window) % n]
    b = contour[(idx + window) % n]
    return float(np.degrees(np.arctan2((b[0] - a[0]) * dx_km, (b[1] - a[1]) * dx_km)))


def sample_activities(rng: np.random.Generator, land: np.ndarray, contour: np.ndarray, margins: OutlineMargins, *, T: float,
                      dx_km: float = 1.0, ocean_band_km: float = 10.0, emergence: bool = False, platform_depth_m: float = 0.0) -> list[Activity]:
    ny, nx = land.shape
    filled = ndi.binary_fill_holes(land)
    dist_in = ndi.distance_transform_edt(filled) * dx_km  # distance inland from the coast
    ys, xs = np.nonzero(filled)
    cx, cy = xs.mean() * dx_km, ys.mean() * dx_km
    acts: list[Activity] = []
    n_out = len(contour)

    # ---- convergent belt system(s): 1 with p 16/18, 2 with p 2/18 (G, conditional on at least one; assumption)
    n_conv = 1 if rng.random() < 16 / 18 else 2
    active_idx = np.nonzero(margins.label == "active")[0]
    belt_axes = []
    for k in range(n_conv):
        subduction = len(active_idx) > 0 and rng.random() < 0.5  # subduction vs collision ratio: assumption
        if subduction:
            i = int(rng.choice(active_idx))
            base_az = _coast_tangent(contour, i, dx_km)
            dev = float(BELT_COAST_ANGLE_DEG.sample(rng)) * rng.choice([-1, 1])
            az = base_az + dev
            d_coast = float(BELT_COAST_DIST_KM.sample(rng))
            width = float(sample_range(rng, 70.0, 300.0))
            # move the axis inland by the coast distance plus half width along the inward normal
            r0, c0 = contour[i]
            nrm = np.deg2rad(base_az + 90.0)
            cand = []
            for sgn in (1, -1):
                x0 = c0 * dx_km + sgn * np.cos(nrm) * (d_coast + width / 2)
                y0 = r0 * dx_km + sgn * np.sin(nrm) * (d_coast + width / 2)
                ii, jj = int(round(y0 / dx_km)), int(round(x0 / dx_km))
                inside = 0 <= ii < ny and 0 <= jj < nx and filled[ii, jj]
                cand.append((inside, x0, y0, sgn))
            inside_c = [c for c in cand if c[0]] or cand
            _, x0, y0, sgn = inside_c[0]
            foreland_side = sgn  # inland side
            kind = "subduction"
        else:
            # collision belt along an assumed suture: a random chord through the interior (assumption)
            az = float(rng.uniform(0, 180))
            perp_c, _ = _line_distance(land.shape, cx, cy, az, dx_km)
            offset = float(rng.uniform(-0.3, 0.3)) * (dist_in.max() * 2)
            x0, y0 = cx - np.sin(np.deg2rad(az)) * offset, cy + np.cos(np.deg2rad(az)) * offset
            width = float(sample_range(rng, 70.0, 300.0))
            foreland_side = rng.choice([-1, 1])
            kind = "collision"
        # E-010: contemporaneous belts must not cross: reject if axis angle differs by > 20° and lines intersect inside land
        if belt_axes and any(abs(((az - a2 + 90) % 180) - 90) > 20 for a2, _ in belt_axes):
            az = belt_axes[0][0] + float(rng.uniform(-15, 15))
        belt_axes.append((az, (x0, y0)))
        length = float(BELT_LENGTH_KM.sample(rng)) * (1.5 if kind == "collision" else 1.0)
        perp, along = _line_distance(land.shape, x0, y0, az, dx_km)
        rate = float(CONVERGENT_RATE.sample(rng))
        prof = _band_profile(perp, along, width, length, "gaussian")
        t_start = float(rng.uniform(0.0, 0.3 * T))
        acts.append(Activity("convergent_belt", f"convergent_{k}", t_start, T, rate * prof,
                             dict(type=kind, azimuth_deg=az, x0_km=x0, y0_km=y0, width_km=width, length_km=length, peak_rate_m_per_yr=rate),
                             dict(rate=("H-003 thermochronology 2-0 Ma", CALC), width=("B range 70 to 300 km", ASSUMPTION),
                                  length=("G clipped long edge", CALC), angle=("G coast angle", CALC), placement=("E-001/E-005; suture by assumption", ASSUMPTION),
                                  timing=("start uniform in 0 to 0.3 T, active to T", ASSUMPTION))))
        # thrust faults inside the belt (E-053): 1 to 3 step strips on the foreland side
        for f in range(int(rng.integers(1, 4))):
            off = float(rng.uniform(0.1, 0.45)) * width * foreland_side
            fw = float(rng.uniform(5.0, 20.0))
            frate = float(REVERSE_FAULT_RATE.sample(rng))
            strip = (np.abs(perp - off) <= fw) & (np.abs(along) <= length / 2)
            hanging = (perp - off) * foreland_side < 0
            fld = np.where(strip & hanging, frate, 0.0) * np.exp(-np.abs(perp - off) / fw)
            acts.append(Activity("thrust_fault", f"convergent_{k}", t_start, T, fld, dict(offset_km=off, width_km=fw, rate_m_per_yr=frate),
                                 dict(rate=("GEM reverse faults relative vertical", CALC), geometry=("strip inside belt", ASSUMPTION))))
        # foreland basin (E-035, E-C002 observed width 100 to 300 km) on the foreland side, adjacent to the belt
        fb_width = float(sample_range(rng, 100.0, 300.0))
        fb_rate = -float(sample_range(rng, 0.1e-3, 4.7e-3))  # B Taiwan foreland range, log-uniform
        fb_center = foreland_side * (width / 2 + fb_width / 2)
        fb_prof = _band_profile(perp - fb_center, along, fb_width, length * 1.2, "gaussian")
        fb_duration = min(T - t_start, MAX_SUBSIDENCE_TOTAL_M / abs(fb_rate))
        acts.append(Activity("foreland_basin", f"convergent_{k}", t_start, t_start + fb_duration, fb_rate * fb_prof,
                             dict(width_km=fb_width, rate_m_per_yr=fb_rate, side=int(foreland_side)),
                             dict(width=("E-C002 observed 100 to 300 km", DIRECT), rate=("B foreland range, log-uniform", ASSUMPTION),
                                  duration=("capped at 8 km cumulative subsidence", ASSUMPTION))))

    # ---- rift system: exactly one (lower bound by design, upper bound 1 from G)
    for attempt in range(20):
        az = float(rng.uniform(0, 180))
        offset = float(rng.uniform(-0.4, 0.4)) * dist_in.max() * 2
        x0, y0 = cx - np.sin(np.deg2rad(az)) * offset, cy + np.cos(np.deg2rad(az)) * offset
        if not belt_axes or all(abs(((az - a2 + 90) % 180) - 90) > 25 or np.hypot(x0 - p2[0], y0 - p2[1]) > 120 for a2, p2 in belt_axes):
            break
    graben = float(sample_range(rng, 50.0, 80.0))
    shoulder = float(sample_range(rng, 30.0, 100.0))  # B: isostatic range 100 km
    perp, along = _line_distance(land.shape, x0, y0, az, dx_km)
    rift_len = float(rng.uniform(150.0, 400.0))
    sub_rate = -float(sample_range(rng, 1.0e-3, 2.0e-3))  # B North Island back-arc, uniform
    relief = float(sample_range(rng, 1500.0, 2500.0))
    rift_T = min(float(sample_range(rng, 16e6, 35e6)), T)  # Neuharth 24 Myr reference, sensitivity 16 to 35
    active_T = min(rift_T, MAX_SUBSIDENCE_TOTAL_M / abs(sub_rate))
    shoulder_rate = relief / rift_T
    t0 = float(rng.uniform(0.0, max(T - active_T, 0.0)))
    center = _band_profile(perp, along, graben, rift_len, "box")
    sh = ((np.abs(perp) > graben / 2) & (np.abs(perp) <= graben / 2 + shoulder)).astype(float) * np.exp(-(np.abs(perp) - graben / 2) / shoulder) * (np.abs(along) <= rift_len / 2)
    acts.append(Activity("rift_center", "rift_0", t0, t0 + active_T, sub_rate * center, dict(azimuth_deg=az, x0_km=x0, y0_km=y0, graben_km=graben, length_km=rift_len, rate_m_per_yr=sub_rate),
                         dict(width=("B East Africa 50 to 80 km", CALC), rate=("B back-arc subsidence, uniform", ASSUMPTION), duration=("Neuharth stages, capped at 8 km", ASSUMPTION), placement=("E-013 interior chord", ASSUMPTION))))
    acts.append(Activity("rift_shoulder", "rift_0", t0, t0 + rift_T, shoulder_rate * sh, dict(shoulder_km=shoulder, relief_m=relief, rate_m_per_yr=shoulder_rate),
                         dict(relief=("B 1.5 to 2.5 km", CALC), rate=("relief over rift duration", ASSUMPTION))))
    # normal faults bounding the graben (E-019): steps at the graben edges
    for side in (-1, 1):
        frate = float(NORMAL_FAULT_RATE.sample(rng))
        edge = side * graben / 2
        strip = (np.abs(perp - edge) <= 8.0) & (np.abs(along) <= rift_len / 2)
        fld = np.where(strip & (np.sign(perp - edge) != side), -frate, 0.0) * np.exp(-np.abs(perp - edge) / 8.0)
        acts.append(Activity("normal_fault", "rift_0", t0, t0 + active_T, fld, dict(side=side, rate_m_per_yr=-frate),
                             dict(rate=("GEM normal faults relative vertical", CALC), geometry=("graben-bounding strip", ASSUMPTION))))
    # post-rift thermal subsidence (E-022): exponential decay tau = 62.8 Myr, r0 uniform 0.02 to 0.064 mm/yr (assumption)
    tau = 62.8e6
    r0 = -float(sample_range(rng, 0.02e-3, 0.064e-3))
    if t0 + active_T < T:
        acts.append(Activity("thermal_subsidence", "rift_0", t0 + active_T, T, r0 * _band_profile(perp, along, graben + 2 * shoulder, rift_len, "gaussian"),
                             dict(tau_yr=tau, r0_m_per_yr=r0, decay="exponential from rift end"),
                             dict(tau=("McKenzie 62.8 Myr", DIRECT), r0=("4 km over 150 Myr bound", ASSUMPTION))))

    # ---- regional uplift: one per sample (yZz P-5), wavelength 300 to 1000 km, rate 0.03 to 0.4 mm/yr (log-uniform)
    lam = float(sample_range(rng, 300.0, 1000.0))
    rrate = float(sample_range(rng, 0.03e-3, 0.4e-3))
    if emergence:
        rrate = max(rrate, 2.0 * platform_depth_m / T)  # must lift the platform above the sea within T (assumption)
    rx, ry = cx + float(rng.uniform(-0.3, 0.3)) * lam, cy + float(rng.uniform(-0.3, 0.3)) * lam
    y, x = np.mgrid[0:ny, 0:nx].astype(float) * dx_km
    dome = np.exp(-0.5 * (np.hypot(x - rx, y - ry) / (lam / 2.355)) ** 2)
    acts.append(Activity("regional_uplift", "regional_0", 0.0, T, rrate * dome, dict(wavelength_km=lam, rate_m_per_yr=rrate, center=(rx, ry)),
                         dict(wavelength=("B 300 to 1000 km", CALC), rate=("B 0.03 to 0.4 mm/yr, log-uniform", ASSUMPTION), count=("1 per sample", ASSUMPTION))))

    # ---- strike-slip system: 0 with p 0.9, 1 with 0.08, 2 with 0.02 (G: one positive landmass of 34; assumption)
    n_ss = int(rng.choice([0, 1, 2], p=[0.9, 0.08, 0.02]))
    for k in range(n_ss):
        az = float(rng.uniform(0, 180))
        offset = float(rng.uniform(-0.4, 0.4)) * dist_in.max() * 2
        x0, y0 = cx - np.sin(np.deg2rad(az)) * offset, cy + np.cos(np.deg2rad(az)) * offset
        perp, along = _line_distance(land.shape, x0, y0, az, dx_km)
        fld = np.zeros(land.shape)
        for b in range(int(rng.integers(1, 4))):
            pos = float(rng.uniform(-150, 150))
            L, Wb = float(rng.uniform(20, 60)), float(rng.uniform(10, 30))
            frate = -float(NORMAL_FAULT_RATE.sample(rng))
            patch = (np.abs(along - pos) <= L / 2) & (np.abs(perp) <= Wb / 2)
            fld = np.where(patch, frate, fld)
        acts.append(Activity("pull_apart_basin", f"strike_slip_{k}", float(rng.uniform(0, 0.5 * T)), T, fld, dict(azimuth_deg=az, x0_km=x0, y0_km=y0),
                             dict(rate=("GEM normal faults", CALC), geometry=("bend basins 20 to 60 km", ASSUMPTION), count=("0/1/2 with 0.9/0.08/0.02", ASSUMPTION))))

    # ---- domain rules: no land-forming activity inside the outer ocean band (E-071), borders at zero (E-072)
    band = int(round(ocean_band_km / dx_km))
    mask = np.ones(land.shape, bool)
    mask[:band, :] = mask[-band:, :] = mask[:, :band] = mask[:, -band:] = False
    for a in acts:
        a.rate_field = np.where(mask, a.rate_field, 0.0)
        a.rate_field[0, :] = a.rate_field[-1, :] = a.rate_field[:, 0] = a.rate_field[:, -1] = 0.0
    return acts


def build_epochs(acts: list[Activity], T: float, min_epoch_yr: float = 250e3, decay_epoch_yr: float = 1e6) -> list[Epoch]:
    """Sum activity rate fields into piecewise-constant epochs (thermal subsidence decays per epoch), with caps."""
    bounds = {0.0, T}
    for a in acts:
        bounds.add(max(0.0, min(a.t_start, T)))
        bounds.add(max(0.0, min(a.t_end, T)))
        if a.kind == "thermal_subsidence":
            t = a.t_start
            while t < min(a.t_end, T):
                bounds.add(t)
                t += decay_epoch_yr
    times = sorted(b for b in bounds if 0.0 <= b <= T)
    # merge epochs shorter than min_epoch_yr
    merged = [times[0]]
    for t in times[1:]:
        if t - merged[-1] >= min_epoch_yr or t == T:
            merged.append(t)
    epochs = []
    for t0, t1 in zip(merged[:-1], merged[1:]):
        tm = 0.5 * (t0 + t1)
        u = np.zeros(acts[0].rate_field.shape)
        for a in acts:
            if a.t_start <= tm < a.t_end:
                f = a.rate_field
                if a.kind == "thermal_subsidence":
                    f = f * np.exp(-(tm - a.t_start) / a.params["tau_yr"])
                u = u + f
        u = np.clip(u, SUBSIDENCE_CAP, UPLIFT_CAP)
        epochs.append(Epoch(t0, t1, u))
    return epochs


def describe(acts: list[Activity]) -> list[dict]:
    out = []
    for a in acts:
        d = {"kind": a.kind, "system": a.system, "t_start_yr": a.t_start, "t_end_yr": a.t_end,
             "rate_max_m_per_yr": float(a.rate_field.max()), "rate_min_m_per_yr": float(a.rate_field.min()),
             "cells": int((a.rate_field != 0).sum()), "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in a.params.items()},
             "evidence": a.evidence}
        out.append(d)
    return out
