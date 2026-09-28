"""Freeze and independently check the original, unloaded B07 observations."""
import shutil
import numpy as np
from .common import *

FILES = {
    'B07_rates.dat': REFERENCE / 'sources/B07/14345750/Backstripped unloaded subsidence rate along Line 1.dat',
    'B07_displacement.dat': REFERENCE / 'sources/B07/14345750/Backstripped unloaded subsidence along Line 1.dat',
    'B07_metadata.json': REFERENCE / 'sources/B07/figshare_14345750.json',
    'B01_nodes.csv': REFERENCE / 'tables/B01_backstripped_nodes.csv',
    'basin_records.md': REFERENCE / 'records/basin.md',
    'B03_paper.txt': REFERENCE / 'sources/B03/article_publisher.txt',
    'B05_paper.txt': REFERENCE / 'sources/B05/article.txt',
    'viewer_colormaps.py': REPO / 'viewer/lem_viewer/colormaps.py',
    'bathymetry_parameters.json': CONVERGENT / 'window_pipeline/inputs/bathymetry_parameters.json',
    'convergent_render_windows.py': CONVERGENT / 'window_pipeline/render_windows.py',
    'convergent_render_time.py': CONVERGENT / 'time_pipeline/render_time.py',
    'convergent_finish.py': CONVERGENT / 'time_pipeline/finish.py',
}

def prepare():
    initialize()
    records = []
    for name, source in FILES.items():
        destination = SOURCES / name
        if not source.is_file():
            raise FileNotFoundError(source)
        if not destination.exists():
            shutil.copyfile(source, destination)
        if sha(source) != sha(destination):
            raise ValueError(f'Frozen source differs: {name}')
        records.append(dict(original=str(source), copy=name, sha256=sha(destination), bytes=destination.stat().st_size))
    # Existing verified domains are inputs. Never regenerate or rewrite them here.
    bases = []
    for seed in range(1001, 1009):
        p = BASES / f'seed{seed}/base.npz'
        with np.load(p) as data:
            if data['mask'].shape != (500, 500) or not np.isfinite(data['elevation_m']).all():
                raise ValueError(f'Invalid existing base: {p}')
        bases.append(dict(seed=seed, path=str(p), sha256=sha(p)))
    rate = np.loadtxt(SOURCES / 'B07_rates.dat', skiprows=1)
    depth = np.loadtxt(SOURCES / 'B07_displacement.dat', skiprows=1)
    young = np.array([0., 1.8, 5.2, 16.4, 23., 30., 40.4])
    old = np.array([1.8, 5.2, 16.4, 23., 30., 40.4, 45.])
    recomputed = (depth[:, 4:-1] - depth[:, 5:]) / (old-young)
    error = float(np.max(abs(recomputed-rate[:, 4:])))
    if rate.shape != (1818, 11) or depth.shape != (1818, 12) or error > 1e-6:
        raise ValueError('B07 identity, column or rate-difference check failed')
    if not np.allclose(rate[:, :4], depth[:, :4]) or not np.all(np.diff(rate[:, 3]) > 0):
        raise ValueError('B07 positional/time pairing failed')
    x = rate[:, 3]
    edges = np.r_[x[0], (x[:-1]+x[1:])/2, x[-1]]
    weights = np.diff(edges)
    np.savez_compressed(MODELS / 'reference.npz', distance_km=x, rates_m_per_Myr=rate[:, 4:][:, ::-1],
                        old_Ma=old[::-1], young_Ma=young[::-1], spatial_weights=weights,
                        cumulative_m=depth[:, 4:][:, ::-1])
    save(SOURCES / 'manifest.json', dict(files=records, bases=bases,
        B07=dict(doi='10.6084/m9.figshare.14345750.v1', license='CC BY 4.0',
                 authors='Bing Han; Zhen Sun; Xiaofang Wang; Zhongxian Zhao',
                 source_quantity='backstripped unloaded tectonic subsidence; positive downward',
                 rate_unit='m/Myr', target_U_unit='m/yr, positive upward',
                 independent_study_families=1, profile_positions=1818, interval_count=7,
                 difference_error_m_per_Myr=error, profile_coverage_km=float(np.ptp(x)),
                 coverage_is_complete_activity_extent=False),
        used_forward_model_as_observations=False, source_and_base_read_only=True))
    print('B07 paired source checks passed; eight existing base domains verified.', flush=True)
    return load(SOURCES / 'manifest.json')
