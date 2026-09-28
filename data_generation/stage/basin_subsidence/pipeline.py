"""One independent generated event for every chronological trigger."""
import time
import numpy as np
from scipy import ndimage
from .common import *
from .temporal import simulate, frame_times, make_history
from .spatial import generate_reference
from .window import choose_window
from .schedule import Event

def generate_world(seed, output=OUT):
    affinity_identity = 'affinity unavailable'
    try:
        import psutil
        p = psutil.Process()
        eligible, affinity_identity = physical_cpu_representatives()
        p.cpu_affinity([eligible[(int(seed)-1001) % len(eligible)]])
    except (ImportError, AttributeError, OSError):
        pass
    started = time.perf_counter()
    output = Path(output)
    directory = output/f'seed{seed}'
    directory.mkdir(parents=True, exist_ok=True)
    schedule = simulate(seed)
    save(directory/'schedule.json', schedule)
    summaries = []
    for event in schedule['events']:
        p = directory/f"event{event['event_index']:02d}"
        p.mkdir(parents=True, exist_ok=True)
        save(p/'event.json', event)
        spatial = generate_reference(event['event_seed'], p)
        make_history(event, p)
        selection = choose_window(event, p)
        full, window = Event(p, 'complete'), Event(p)
        frames = frame_times(event)
        arrays, statistics = [], []
        for frame in frames:
            U = full.at_time(frame['sim_Myr']*1e6)
            arrays.append(U.astype(np.float32))
            statistics.append(dict(sim_Myr=frame['sim_Myr'], min_mm_yr=float(U.min()*1000),
                max_mm_yr=float(U.max()*1000), active_area_km2=int(np.count_nonzero(U)),
                subsiding_area_km2=int(np.count_nonzero(U < 0)), rising_area_km2=int(np.count_nonzero(U > 0))))
        np.savez_compressed(p/'native_frames.npz', u_m_per_yr=np.array(arrays), times_Myr=[f['sim_Myr'] for f in frames],
                            x_km=full.x_km, y_km=full.y_km)
        save(p/'frames.json', frames)
        end = min(48., event['natural_end_sim_Myr'])
        displacement = full.displacement(event['start_sim_Myr']*1e6, end*1e6)
        natural_displacement = full.history.displacement(event['start_sim_Myr'], event['natural_end_sim_Myr'])
        np.savez_compressed(p/'displacement.npz', complete_m=displacement,
                            window_m=window.displacement(0, 48e6), x_km=full.x_km, y_km=full.y_km)
        ref = np.load(p/'reference.npz')['u_m_per_yr']
        labels, count = ndimage.label(ref != 0)
        areas = np.bincount(labels.ravel())[1:]
        active = ref[ref != 0]*1000
        source = load(MODELS/'spatial.json')
        reference_quantiles = np.quantile(-active, [.1, .5, .9]).tolist()
        summary = dict(event_id=event['event_id'], seed=seed, event_index=event['event_index'],
            event_seed=event['event_seed'], frame_statistics=statistics, frames=len(frames),
            reference_min_mm_yr=float(ref.min()*1000), reference_max_mm_yr=float(ref.max()*1000),
            reference_downward_P10_P50_P90_mm_yr=reference_quantiles,
            source_downward_P10_P50_P90_mm_yr=(np.interp([.1, .5, .9], source['quantile_probabilities'], source['magnitude_quantiles_m_per_Myr'])/1000).tolist(),
            complete_long_km=spatial['complete_long_km'], reference_area_km2=int(np.count_nonzero(ref)),
            connected_components=int(count), largest_component_fraction=float(areas.max()/areas.sum()),
            execution_cumulative_min_m=float(displacement.min()), execution_cumulative_max_m=float(displacement.max()),
            natural_mean_node_displacement_m=float(np.average(natural_displacement[full.mesh['active']], weights=full.mesh['mass'][full.mesh['active']])),
            sampling_diagnostics=spatial['diagnostics'], selection=selection,
            source_geometry_sha256=sha(p/'mesh.npz'), temporal_parameters_sha256=sha(p/'time_model.npz'),
            minimum_active_mesh_layer=spatial['minimum_active_mesh_layer'], geometry_attempts=len(spatial['geometry_attempts']),
            elapsed_core_generation_seconds=spatial['elapsed_seconds'])
        save(p/'summary.json', summary)
        summaries.append(summary)
        print(f"seed {seed} event {event['event_index']+1}: L={spatial['complete_long_km']:.1f} km, "
              f"frames={len(frames)}, Rhat={spatial['diagnostics']['maximum_rhat']:.3f}", flush=True)
    resource_record = {}
    try:
        import psutil
        process = psutil.Process()
        memory = process.memory_info()
        resource_record = dict(cpu_affinity=process.cpu_affinity(), peak_working_set_bytes=getattr(memory, 'peak_wset', memory.rss))
        resource_record['affinity_identity'] = affinity_identity
    except (ImportError, AttributeError, OSError):
        pass
    result = dict(seed=seed, events=summaries, elapsed_seconds=time.perf_counter()-started, resources=resource_record)
    save(directory/'generation.json', result)
    return result
