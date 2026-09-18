"""Unit tests for the pure-numpy parts of lem_pipeline (no FastScape binding required)."""
from __future__ import annotations

from pathlib import Path as _BootstrapPath
import sys as _bootstrap_sys
_project_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
for _relative in ('.', 'experiments'):
    _code_path = str(_project_root / _relative)
    if _code_path not in _bootstrap_sys.path:
        _bootstrap_sys.path.append(_code_path)


import numpy as np
import pytest

from lem_pipeline import distributions as dist
from lem_pipeline.checks import CheckConfig, evaluate
from lem_pipeline.landmask import LandmaskParams, generate, generate_shape_first, mask_metrics, power_law_field
from lem_pipeline.spectrum import fit_beta, radial_spectrum


def test_sample_range_log_uniform_switch():
    rng = np.random.default_rng(0)
    narrow = np.array([dist.sample_range(rng, 1.0, 5.0) for _ in range(2000)])
    wide = np.array([dist.sample_range(rng, 1.0, 100.0) for _ in range(4000)])
    assert narrow.min() >= 1.0 and narrow.max() <= 5.0
    assert abs(narrow.mean() - 3.0) < 0.15  # uniform on a range narrower than one decade
    assert wide.min() >= 1.0 and wide.max() <= 100.0
    assert abs(np.median(wide) - 10.0) < 1.5  # log-uniform on two decades: median at the geometric centre


def test_quantile_table_roundtrip():
    row = {"minimum": 0.5, "p05": 1.0, "p25": 2.0, "median": 4.0, "p75": 8.0, "p95": 16.0, "maximum": 32.0}
    tab = dist.QuantileTable.from_row(row, "x")
    assert tab.quantile(0.5) == pytest.approx(4.0)
    rng = np.random.default_rng(1)
    s = np.array([tab.sample(rng) for _ in range(4000)])
    assert s.min() >= 0.5 and s.max() <= 32.0
    assert abs(np.median(s) - 4.0) < 0.6


def test_power_law_field_is_normalised_and_seeded():
    rng = np.random.default_rng(3)
    f = power_law_field(rng, 128, 128, 3.0, 1.0, 2.0)
    assert f.shape == (128, 128)
    assert abs(f.mean()) < 1e-9 and abs(f.std() - 1.0) < 1e-9
    g = power_law_field(np.random.default_rng(3), 128, 128, 3.0, 1.0, 2.0)
    assert np.allclose(f, g)


def test_generate_occupancy_first_hits_target_and_keeps_ocean_band():
    p = LandmaskParams(nx=200, ny=200, occupancy=0.4, ocean_band_km=10.0, seed=5)
    land, info = generate(p)
    assert abs(info["occupancy_achieved"] - 0.4) < 0.01
    assert not land[:10, :].any() and not land[-10:, :].any() and not land[:, :10].any() and not land[:, -10:].any()


def test_generate_shape_first_matches_span():
    p = LandmaskParams(nx=200, ny=200, axis_ratio=1.6, beta=3.5, noise_amplitude=0.2, ocean_band_km=10.0, seed=7)
    land, info = generate_shape_first(p, span_km=150.0)
    assert abs(info["min_square_achieved_km"] - 150.0) <= 6.0
    m = mask_metrics(land)
    assert 0 < m["land_fraction"] < 1 and m["components"] >= 1 and m["min_square_km"] > 0


def test_mask_metrics_of_a_disc():
    yy, xx = np.mgrid[0:200, 0:200]
    land = (xx - 100) ** 2 + (yy - 100) ** 2 < 50 ** 2
    m = mask_metrics(land)
    assert m["components"] == 1
    assert abs(m["pca_ratio_main"] - 1.0) < 0.02
    assert abs(m["fill_ratio_main"] - np.pi / 4) < 0.03
    assert m["closed_water_cells"] == 0 and not m["touches_boundary"]


def test_spectrum_recovers_exponent():
    beta = 3.0
    f = power_law_field(np.random.default_rng(11), 512, 512, beta, 1.0, 2.0)
    k, p, c = radial_spectrum(f, 1.0, 1.0)
    fit = fit_beta(k, p, c, 4.0, 100.0)
    assert abs(fit["beta"] - beta) < 0.35
    assert fit["r2"] > 0.95


def test_checks_accept_simple_island_and_apply_the_two_rules():
    ny = nx = 300
    yy, xx = np.mgrid[0:ny, 0:nx]
    z = np.full((ny, nx), -200.0)
    island = (xx - 150) ** 2 / 120 ** 2 + (yy - 150) ** 2 / 90 ** 2 < 1.0
    z[island] = 50.0
    res = evaluate(z, CheckConfig(sea_level_m=0.0, dx_km=1.0, ocean_band_km=10.0, occupancy_band=(0.0, 1.0)))
    assert res["accepted"], res["reasons"]
    assert res["land_components_4"] == 1 and res["closed_sub_sea_level_area_km2"] == 0.0
    # an enclosed basin below sea level is reported as closed water, the milestone-1 rules do not discard for it
    z2 = z.copy()
    z2[140:160, 140:160] = -5.0
    res2 = evaluate(z2, CheckConfig(sea_level_m=0.0, dx_km=1.0, ocean_band_km=10.0, occupancy_band=(0.0, 1.0)))
    assert res2["closed_sub_sea_level_area_km2"] == pytest.approx(400.0)
    # rule 1: land inside the ocean band; rule 2: land fraction outside the occupancy band
    z3 = z.copy()
    z3[5, 150] = 10.0
    res3 = evaluate(z3, CheckConfig(sea_level_m=0.0, dx_km=1.0, ocean_band_km=10.0, occupancy_band=(0.0, 1.0)))
    assert not res3["accepted"] and "ocean band" in res3["reasons"][0]
    res4 = evaluate(z, CheckConfig(sea_level_m=0.0, dx_km=1.0, ocean_band_km=10.0, occupancy_band=(0.5, 0.6)))
    assert not res4["accepted"] and "occupancy band" in res4["reasons"][0]
