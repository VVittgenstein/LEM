"""Re-select windows for saved events, preserving source fields and time histories."""
import hashlib
import os
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from .common import *
from .sampling_geometry import FullSupport, platform
from .window import choose_window, candidate_metrics, DESIGN, SAMPLING_VERSION
from .schedule import Event

IMMUTABLE_EVENT_FILES = ('event.json', 'mesh.npz', 'reference.npz', 'sampling.npz', 'spatial.json',
                         'time_model.npz', 'time_model.json', 'native_frames.npz', 'frames.json', 'traces.npz')
IMMUTABLE_CODE = ('spatial.py', 'temporal.py', 'fit.py', 'schedule.py', 'pipeline.py')


def immutable_hashes(output, batch):
    files = [ROOT/name for name in IMMUTABLE_CODE]+list(MODELS.glob('*'))
    files += [output/f"seed{w['seed']}/schedule.json" for w in batch['worlds']]
    complete = {}
    for row in batch['events']:
        p = output/f"seed{row['seed']}/event{row['event_index']:02d}"
        files.extend(p/name for name in IMMUTABLE_EVENT_FILES if (p/name).is_file())
        with np.load(p/'displacement.npz') as data:
            complete[(p/'displacement.npz').relative_to(ROOT).as_posix()] = hashlib.sha256(
                np.ascontiguousarray(data['complete_m']).tobytes()).hexdigest()
    return dict(files={p.relative_to(ROOT).as_posix(): sha(p) for p in files if p.is_file()},
                complete_displacement=complete)


def resample_world(world, output, staging):
    import psutil
    physical, topology = physical_cpu_representatives()
    psutil.Process().cpu_affinity([physical[(int(world['seed'])-1001) % len(physical)]])
    started = time.perf_counter()
    results, comparison = [], []
    for summary in world['events']:
        relative = Path(f"seed{summary['seed']}/event{summary['event_index']:02d}")
        directory, destination = output/relative, staging/relative
        event, old = load(directory/'event.json'), load(directory/'selection.json')
        field, land = FullSupport(directory), platform(event['seed'])
        # A diagnostic measurement of the old layout without the new gates.
        measurement = dict(DESIGN, minimum_coverage=0., maximum_coverage=1.)
        previous = candidate_metrics(field, land, np.array(old['center_source_km']),
                                     np.array(old['rotation_matrix']), measurement)
        selected = choose_window(event, directory, destination)
        with np.load(destination/'window.npz') as data:
            query = data['query_vertices'], data['query_weights']
        with np.load(directory/'displacement.npz') as data:
            displacement = dict(data)
        evaluator = Event(directory, 'complete')
        displacement['window_m'] = field.mapper.evaluate(evaluator.history.displacement(0., 48.), query).reshape(500, 500)
        np.savez_compressed(destination/'displacement.npz', **displacement)
        updated = dict(summary, selection=selected)
        save(destination/'summary.json', updated)
        results.append(updated)
        comparison.append(dict(event_id=event['event_id'], seed=event['seed'], event_index=event['event_index'],
            complete_support_area_km2=field.area, platform_area_km2=land.area,
            before=previous, after=selected))
    return dict(seed=world['seed'], events=results, comparison=comparison,
        elapsed_seconds=time.perf_counter()-started, cpu_affinity=psutil.Process().cpu_affinity(),
        affinity_identity=topology)


def resample(output=OUT, workers=8):
    output = Path(output)
    batch = load(output/'batch.json')
    before = immutable_hashes(output, batch)
    staging = CHECKS/'resampling_staging'/SAMPLING_VERSION/output.relative_to(ROOT)
    staging.mkdir(parents=True, exist_ok=True)
    save(staging/'before_batch.json', batch)
    save(staging/'preservation_before.json', before)
    started = time.perf_counter()
    worlds = []
    if workers == 1:
        worlds = [resample_world(world, output, staging) for world in batch['worlds']]
    else:
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as pool:
            futures = {pool.submit(resample_world, world, output, staging): world['seed'] for world in batch['worlds']}
            for future in as_completed(futures):
                worlds.append(future.result())
                print('Window candidates and selection ready:', futures[future], flush=True)
    worlds.sort(key=lambda w: w['seed'])
    # All workers must succeed before any saved event product is replaced.
    mutable = ('window.npz', 'selection.json', 'entry_paths.json', 'window_candidates.csv', 'displacement.npz', 'summary.json')
    for world in worlds:
        for row in world['events']:
            relative = Path(f"seed{row['seed']}/event{row['event_index']:02d}")
            for name in mutable:
                os.replace(staging/relative/name, output/relative/name)
        original = next(w for w in batch['worlds'] if w['seed'] == world['seed'])
        original['events'] = world['events']
        original['window_resampling'] = {k: v for k, v in world.items() if k not in ('events', 'comparison')}
        save(output/f"seed{world['seed']}/generation.json", original)
    batch['events'] = [e for w in batch['worlds'] for e in w['events']]
    after = immutable_hashes(output, batch)
    preservation = dict(passed=before == after, before=before, after=after,
                        unchanged_file_count=len(before['files']), complete_displacement_count=len(before['complete_displacement']))
    save(output/'resampling_preservation.json', preservation)
    if not preservation['passed']:
        raise RuntimeError('Resampling changed a protected input or complete displacement array')
    metadata = dict(version=SAMPLING_VERSION, design=DESIGN, workers=workers,
        elapsed_seconds=time.perf_counter()-started,
        timing_scope='saved-field boundary extraction, candidates, selection, window queries and window displacement; excludes rendering',
        generated_event_count=0, event_count=len(batch['events']), unchanged_file_count=preservation['unchanged_file_count'],
        complete_displacement_count=preservation['complete_displacement_count'],
        comparison=[e for w in worlds for e in w['comparison']],
        resources=[{k: v for k, v in w.items() if k not in ('events', 'comparison')} for w in worlds])
    save(output/'resampling.json', metadata)
    batch['window_resampling'] = {k: v for k, v in metadata.items() if k != 'comparison'}
    save(output/'batch.json', batch)
    print('Window resampling complete:', len(batch['events']), 'events;', round(metadata['elapsed_seconds'], 2), 'seconds', flush=True)
    return metadata
