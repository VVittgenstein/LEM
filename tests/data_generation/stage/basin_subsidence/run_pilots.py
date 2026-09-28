"""Explicit independent-seed spatial diagnostics, not part of default tests."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import numpy as np
from data_generation.stage.basin_subsidence.common import *
from data_generation.stage.basin_subsidence.fit import fit_models
from data_generation.stage.basin_subsidence.spatial import generate_reference
from data_generation.stage.basin_subsidence.rendering import render_spatial, render_time
from data_generation.stage.basin_subsidence.temporal import simulate, make_history, frame_times
from data_generation.stage.basin_subsidence.window import choose_window
from data_generation.stage.basin_subsidence.schedule import Event

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, nargs='+', default=[9001, 9002, 9003])
    args = parser.parse_args()
    fit_models()
    results = []
    for seed in args.seeds:
        directory = OUT/'pilots_current'/f'pilot{seed}'
        result = generate_reference(seed, directory)
        event = simulate(seed)['events'][0]
        event.update(seed=1001+seed-9001, event_seed=seed, event_id=f'pilot-{seed}', event_index=0)
        save(directory/'event.json', event)
        make_history(event, directory); choose_window(event, directory)
        frames = frame_times(event); evaluator = Event(directory, 'complete')
        arrays = np.array([evaluator.at_time(f['sim_Myr']*1e6).astype(np.float32) for f in frames])
        np.savez_compressed(directory/'native_frames.npz', u_m_per_yr=arrays)
        save(directory/'frames.json', frames)
        lo = min(-.08, float(arrays.min()*1000)); hi = max(.02, float(arrays.max()*1000))
        edges = np.linspace(lo, hi, 13)
        render_spatial(directory, edges); render_time(directory, edges)
        results.append(result)
        print(seed, result['diagnostics'], 'core seconds', result['elapsed_seconds'], flush=True)
    save(OUT/'pilots_current/results.json', results)
