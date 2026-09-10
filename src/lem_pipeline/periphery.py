"""Periphery (class 1): sea-floor depth around the land region.

Design (yZz 2026-09-08/09, ``architecture-dataflow.md`` 4.1.5 step 2, F session 2026-09-09):

1. The outer outline of the main land component is traced and parameterised by arc length ``u`` (km).
2. Regime: single shallow (p = 20/34) or mixed (14/34) at the 150 km offset. Mixed samples draw the deep share of
   the perimeter from the 14 mixed reference landmasses, the number of deep segments from F's frequency table for
   Lmin = 10 km, and deep-segment lengths from the oceanic segment-length quantiles; the remaining coast is split into
   shelf / transitional / non-shelf continental segments whose lengths follow F's quantile tables and whose class
   proportions follow the marine coast fractions.
3. Every ocean cell takes the segment of its nearest outline point. The trend depth follows the profile
   ``z(d) = z0 + (zb - z0) d / W`` for ``d <= W`` and ``zb + s (d - W)`` beyond, floored at the deep-water depth D
   (Claude 2026-09-08, yZz "支持"). Per-segment parameters: W from F's conditional distribution (shallow at 150 km),
   zb and s from F's landmass-median distributions, z0 and D from the 34-population depth tables (A re-aggregation).
   For deep (oceanic) segments W is capped so that D is reached within 150 km (assumption). Parameters are smoothed
   along the outline over 10 km (assumption) to avoid steps at segment boundaries.
4. Roughness: a power-law random field per regime scaled to the 3 km window standard deviation of the reference
   (shelf 3.5 m, oceanic 9.6 m at 71; 34-population values are read from the pop34 table); the 1 km extrapolation is
   an assumption (yZz 2026-09-08 chose synthesis over cut-outs of real bathymetry).

All sampled values and their evidence states are returned in the ``info`` dictionary.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi

from .distributions import QuantileTable, sample_categorical
from .landmask import power_law_field
from .paths import PRETASKS, POP34_PACKAGE

F_TABLES = PRETASKS / "F-periphery-150km" / "tables"
CALC = "本项目借鉴或合成改造"
ASSUMPTION = "尚待验证的假设"
SHALLOW_CLASSES = ("shelf_continental", "transitional", "continental_non_shelf")


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class PeripheryTables:
    """Lazy access to the F and pop34 tables needed for sampling."""

    def __init__(self, population: str = "34", lmin_km: int = 10, offset_km: int = 150):
        self.population, self.lmin, self.offset = population, lmin_km, offset_km
        freq = [r for r in _read(F_TABLES / "periphery-frequency.csv") if r["population"] == population and r["offset_km"] == str(offset_km)]
        reg = {r["environment"]: int(float(r["landmass_count"])) for r in freq if r["classification"] == "depth_regime"}
        self.p_mixed = reg.get("mixed", 0) / max(1, sum(reg.values()))
        env = {r["environment"]: float(r["coast_fraction_marine"] or 0) for r in freq if r["classification"] == "environment" and r["coast_fraction_marine"]}
        tot = sum(env.get(c, 0) for c in SHALLOW_CLASSES)
        self.shallow_class_p = {c: env.get(c, 0) / tot for c in SHALLOW_CLASSES}
        mds = [r for r in _read(F_TABLES / "mixed-deep-share.csv") if r["population"] == population and r["offset_km"] == str(offset_km)]
        self.deep_share_values = [float(r["deep_fraction_all"]) for r in mds if r["scope"] == "landmass" and r["deep_fraction_all"]]
        dsc = [r for r in _read(F_TABLES / "deep-segment-counts.csv") if r["population"] == population and r["scope"] == "original_mixed_frequency" and r["lmin_km"] == str(lmin_km)]
        self.deep_count_values = [int(float(r["deep_segment_count"])) for r in dsc]
        self.deep_count_weights = [float(r["landmass_count"]) for r in dsc]
        sq = [r for r in _read(F_TABLES / "segment-quantiles.csv") if r["population"] == population and r["scope"] == "pooled_segments"
              and r["offset_km"] == str(offset_km) and r["lmin_km"] == str(lmin_km)]
        self.segment_length = {r["environment"]: QuantileTable.from_row(r, f"seglen {r['environment']}") for r in sq if float(r["n"] or 0) > 0}
        spc = [r for r in _read(F_TABLES / "shelf-profile-conditional.csv") if r["population"] == population and r["scope"] == "pooled_stations"]
        self.W_shallow = QuantileTable.from_row(next(r for r in spc if r["condition"] == "class150_shallow" and r["parameter"] == "W_km"), "W|shallow150")
        spq = [r for r in _read(F_TABLES / "shelf-profile-quantiles.csv") if r["population"] == population and r["scope"] == "landmass_medians" and r["grouping"] == "all"]
        self.zb = QuantileTable.from_row(next(r for r in spq if r["parameter"] == "zb_m"), "zb landmass medians")
        self.slope = QuantileTable.from_row(next(r for r in spq if r["parameter"] == "slope_m_per_m"), "slope landmass medians")
        pop = _read(POP34_PACKAGE / "class1-depth-roughness-land-pop34.csv")
        self.depth = {}
        for r in pop:
            if r["group"] == "depth" and r["margin"] == "all" and r["statistic"] == "landmass_medians" and float(r["n"] or 0) > 1:
                self.depth[(r["environment"], r["band_km"])] = QuantileTable.from_row(r, f"depth {r['environment']} {r['band_km']}")
        self.roughness_3km = {}
        self.roughness_100km = {}
        for r in pop:
            if r["group"] == "roughness" and r["statistic"] == "landmass_medians" and float(r["n"] or 0) > 1:
                if r["band_km"].strip() == "window 3":
                    self.roughness_3km[r["environment"]] = float(r["median"])
                if r["band_km"].strip() == "window 100":
                    self.roughness_100km[r["environment"]] = float(r["median"])

    def nearshore_depth(self, env: str) -> QuantileTable:
        for band in ("0-25", "0-100"):
            if (env, band) in self.depth:
                return self.depth[(env, band)]
        return self.depth[("shelf_continental", "0-100")]

    def floor_depth(self, env: str) -> QuantileTable:
        """Depth reached beyond the shelf break: the subclass's own 100 to 250 km band (oceanic for deep segments)."""
        for band in ("100-250", "0-100"):
            if (env, band) in self.depth:
                return self.depth[(env, band)]
        return self.depth[("oceanic", "0-100")]


def trace_outline(mask: np.ndarray) -> np.ndarray:
    """Ordered (row, col) vertices (cell units, sub-pixel) of the longest closed 0.5-level contour of the filled mask.

    Uses contourpy (a matplotlib dependency available in lem-env); the main component's outer outline is the longest
    closed line. Vertices are roughly one cell apart, so arc length equals the cumulative vertex spacing."""
    import contourpy

    filled = ndi.binary_fill_holes(mask).astype(float)
    gen = contourpy.contour_generator(z=filled)
    lines = gen.lines(0.5)
    if not lines:
        return np.zeros((0, 2), dtype=float)
    best = max(lines, key=lambda a: len(a))
    xy = np.asarray(best, dtype=float)
    if len(xy) > 1 and np.allclose(xy[0], xy[-1]):
        xy = xy[:-1]
    return np.column_stack([xy[:, 1], xy[:, 0]])  # (row, col)


@dataclass
class Segment:
    start_km: float
    length_km: float
    env: str
    deep: bool
    W_km: float
    zb_m: float
    slope: float
    z0_m: float
    D_m: float


@dataclass
class PeripheryInfo:
    regime: str
    deep_share: float | None
    perimeter_km: float
    segments: list[dict] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


def sample_segments(rng: np.random.Generator, tables: PeripheryTables, perimeter_km: float) -> tuple[list[Segment], PeripheryInfo]:
    mixed = rng.random() < tables.p_mixed
    info = PeripheryInfo(regime="mixed" if mixed else "single_shallow", deep_share=None, perimeter_km=perimeter_km)
    deep_intervals: list[tuple[float, float]] = []
    if mixed:
        share = float(rng.choice(tables.deep_share_values))
        n_deep = max(1, int(rng.choice(tables.deep_count_values, p=np.asarray(tables.deep_count_weights) / np.sum(tables.deep_count_weights))))
        total_deep = share * perimeter_km
        lengths = tables.segment_length["oceanic"].sample(rng, size=n_deep)
        lengths = np.asarray(lengths) * (total_deep / max(np.sum(lengths), 1e-9))
        info.deep_share = share
        # place deep segments with random gaps
        gap_total = perimeter_km - total_deep
        gaps = rng.dirichlet(np.ones(n_deep)) * gap_total
        pos = float(rng.uniform(0, perimeter_km))
        for L, g in zip(lengths, gaps):
            deep_intervals.append((pos % perimeter_km, float(L)))
            pos += L + g
    # shallow stretches: fill the complement
    segs: list[Segment] = []
    zb_tab, s_tab, W_tab = tables.zb, tables.slope, tables.W_shallow
    def new_seg(start, length, env, deep):
        z0 = float(tables.nearshore_depth(env if not deep else "shelf_continental").sample(rng))
        zb = max(float(zb_tab.sample(rng)), z0 + 5.0)
        s = float(s_tab.sample(rng))
        D = max(float(tables.floor_depth("oceanic" if deep else env).sample(rng)), zb + 20.0)
        W = float(W_tab.sample(rng))
        if deep:
            W = min(W, max(5.0, tables.offset - (D - zb) / (s * 1000.0)))
        return Segment(start, length, env, deep, W, zb, s, z0, D)
    for start, L in deep_intervals:
        segs.append(new_seg(start, L, "oceanic", True))
    # shallow: iterate over the free arcs
    occupied = sorted(((s % perimeter_km), ((s % perimeter_km) + L)) for s, L in deep_intervals)
    free = []
    cursor = 0.0
    for a, b in occupied:
        if a > cursor:
            free.append((cursor, a - cursor))
        cursor = max(cursor, b)
    if cursor < perimeter_km:
        free.append((cursor, perimeter_km - cursor))
    if not occupied:
        free = [(0.0, perimeter_km)]
    labels, probs = zip(*tables.shallow_class_p.items())
    for a, L in free:
        pos = a
        remaining = L
        while remaining > 1e-6:
            env = str(sample_categorical(rng, labels, probs))
            seglen = float(tables.segment_length[env].sample(rng)) if env in tables.segment_length else remaining
            seglen = min(max(seglen, 2.0), remaining)
            segs.append(new_seg(pos, seglen, env, False))
            pos += seglen
            remaining -= seglen
    segs.sort(key=lambda s: s.start_km)
    info.segments = [vars(s) for s in segs]
    info.evidence = {"regime_p_mixed": (tables.p_mixed, CALC), "deep_share": ("14 mixed landmasses, F", CALC),
                     "deep_segment_count": (f"F frequency Lmin={tables.lmin} km", ASSUMPTION), "segment_lengths": ("F pooled segments Lmin=10", CALC),
                     "W": ("F conditional shallow@150", CALC), "zb, slope": ("F landmass medians", CALC),
                     "z0, D": ("pop34 depth landmass medians", CALC), "deep W cap": ("reach D within 150 km", ASSUMPTION)}
    return segs, info


def build_bathymetry(land: np.ndarray, rng: np.random.Generator, tables: PeripheryTables | None = None, dx_km: float = 1.0,
                     smooth_km: float = 10.0, roughness: bool = True, band_mid_km: float = 12.5) -> tuple[np.ndarray, PeripheryInfo]:
    """Return (depth array in m, negative below sea level, defined on ocean cells; NaN on land) and the sampling info.

    ``band_mid_km``: distance from the shoreline at which the nearshore band statistic z0 (0 to 25 km band) is placed."""
    tables = tables or PeripheryTables()
    contour = trace_outline(land)
    if len(contour) == 0:
        raise ValueError("empty land mask")
    steps = np.hypot(*(np.diff(np.vstack([contour, contour[:1]]), axis=0).T.astype(float))) * dx_km
    u = np.concatenate([[0.0], np.cumsum(steps)[:-1]])
    perimeter = float(steps.sum())
    segs, info = sample_segments(rng, tables, perimeter)
    # per-outline-cell parameters
    n = len(contour)
    par = {k: np.zeros(n) for k in ("W", "zb", "s", "z0", "D", "deep")}
    seg_id = np.full(n, -1)
    for i, s in enumerate(segs):
        a, b = s.start_km, s.start_km + s.length_km
        sel = (u >= a) & (u < b) | ((u + perimeter >= a) & (u + perimeter < b))
        seg_id[sel] = i
        par["W"][sel], par["zb"][sel], par["s"][sel], par["z0"][sel], par["D"][sel], par["deep"][sel] = s.W_km, s.zb_m, s.slope, s.z0_m, s.D_m, float(s.deep)
    unassigned = seg_id < 0
    if unassigned.any():  # numerical gaps at the wrap: copy neighbours
        idx = np.nonzero(~unassigned)[0]
        for j in np.nonzero(unassigned)[0]:
            k = idx[np.argmin(np.abs(idx - j))]
            for key in par:
                par[key][j] = par[key][k]
    # nearest outline vertex for every cell (KD-tree on the sub-pixel outline vertices)
    from scipy.spatial import cKDTree

    ny, nx = land.shape
    tree = cKDTree(contour)
    yy, xx = np.mgrid[0:ny, 0:nx]
    _, nearest = tree.query(np.column_stack([yy.ravel(), xx.ravel()]).astype(float), k=1)
    nearest = nearest.reshape(ny, nx)
    dist_km = ndi.distance_transform_edt(~ndi.binary_fill_holes(land)) * dx_km
    # parameters averaged along the outline over a window that widens with distance from the coast (half the distance,
    # at least smooth_km): removes the ray-shaped Voronoi boundaries between segments far offshore (assumption)
    spacing = perimeter / n
    half_cells = np.maximum(int(round(smooth_km / spacing)), np.round(0.5 * dist_km / spacing).astype(int))
    half_cells = np.minimum(half_cells, n // 2)

    def window_mean(values: np.ndarray) -> np.ndarray:
        rep = np.concatenate([values, values, values])
        cs = np.concatenate([[0.0], np.cumsum(rep)])
        lo = nearest + n - half_cells
        hi = nearest + n + half_cells + 1
        return (cs[hi] - cs[lo]) / (hi - lo)

    W = window_mean(par["W"])
    zb = window_mean(par["zb"])
    s = window_mean(par["s"])
    z0 = window_mean(par["z0"])
    D = window_mean(par["D"])
    # Profile from the shoreline outward (2026-09-09 revision): depth 0 at the outline (the shoreline is the zero level
    # set by definition), the nearshore band value z0 at the band midpoint ``band_mid_km`` (the A tables give band
    # statistics, not shoreline depths; midpoint placement is an assumption), the break depth zb at W, then the slope s
    # down to the floor D. When the break lies inside the band (W < band_mid_km) the shelf runs straight to zb.
    # The earlier construction put z0 at the shoreline itself, which created coastal steps of up to 2 km.
    d = dist_km
    wide = W >= band_mid_km
    d1 = np.where(wide, band_mid_km, np.maximum(W, 1e-6))
    zd1 = np.where(wide, z0, zb)
    seg1 = zd1 * d / d1
    seg2 = z0 + (zb - z0) * (d - d1) / np.maximum(W - d1, 1e-6)
    seg3 = zb + s * 1000.0 * (d - W)
    trend = np.where(d <= d1, seg1, np.where(d <= W, seg2, seg3))
    trend = np.maximum(trend, 0.0)
    trend = np.minimum(trend, D)
    depth = -trend
    if roughness:
        deep_cell = par["deep"][nearest] > 0.5
        for regime, mask_r in (("shelf_continental", ~deep_cell), ("oceanic", deep_cell)):
            std3 = tables.roughness_3km.get(regime, 3.5 if regime != "oceanic" else 9.6)
            std100 = tables.roughness_100km.get(regime, 45.0 if regime != "oceanic" else 219.0)
            H = np.clip(np.log(std100 / std3) / np.log(100.0 / 3.0), 0.1, 0.95)
            beta = 2.0 + 2.0 * H
            fld = power_law_field(rng, ny, nx, beta, dx_km, 2.0)
            loc = ndi.uniform_filter(fld, 3)
            local_std = np.sqrt(np.maximum(ndi.uniform_filter(fld ** 2, 3) - loc ** 2, 0)).mean()
            fld *= std3 / max(local_std, 1e-9)
            depth = np.where(mask_r, depth + fld, depth)
        depth = np.minimum(depth, -1.0)
    depth = np.where(land, np.nan, depth)
    info.evidence["roughness"] = ("power-law field scaled to 3 km window std, 1 km extrapolated", ASSUMPTION)
    info.evidence["smoothing_along_outline_km"] = (smooth_km, ASSUMPTION)
    return depth, info
