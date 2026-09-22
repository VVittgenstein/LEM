"""Bounded, fixed-input mesh study. Existing generation artifacts are read-only."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

import numpy as np
import psutil

from .common import OUT, ROOT, load, save

STUDY = ROOT / 'output' / 'numerical_closeout_20260921'
INPUT_NAMES = ('model_run.json', 'forcing.json', 'window.json', 'faults.json',
               'fault_history.npz', 'timeline.json')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    source = OUT / 'seed1001'
    target = STUDY / 'inputs'
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for name in INPUT_NAMES:
        src, dst = source / name, target / name
        if dst.exists() and digest(src) != digest(dst):
            raise ValueError('Frozen study input differs: ' + name)
        if not dst.exists():
            shutil.copy2(src, dst)
        records.append(dict(name=name, sha256=digest(src)))
    save(STUDY / 'protocol.json', dict(
        source=str(source), inputs=records, seed=1001,
        fixed=['physical domain and window', 'source positions, widths, forces and histories',
               'material and boundary conditions', 'fault geometry, slip and regularization'],
        query_spacing_km=5, query_extent_km=500,
        comparisons='all ten force bases, all sixteen faults and all 243 saved times',
        screening_relative_l2=0.05,
        screening_identity='Agent engineering screening value; not a geological standard',
        convergence_rule='Two successive refinements with <=5% maximum active-time field change, plus depth check; report scope explicitly.',
        max_worker_seconds=240, max_worker_rss_GiB=10,
        hardware=dict(platform=platform.platform(), logical_cpus=psutil.cpu_count(),
                      total_memory_bytes=psutil.virtual_memory().total),
        note='A design choice is permitted when convergence and performance cannot be combined.'))


def worker(kind, nodes, layers, dest, seed=1001):
    if kind == 'generation':
        from .fit import main as fit_models
        from .pipeline import generate
        from .schedule import RiftingSchedule
        start = time.perf_counter()
        model = fit_models()
        generate(seed, 'all')
        generated = time.perf_counter()
        schedule = RiftingSchedule(seed)
        values = [schedule.at_time(t*1e6) for t in [0, 12, 24, 36, 48]]
        displacement = schedule.displacement(0, 48e6)
        assert all(np.isfinite(value).all() for value in values+[displacement])
        assert not np.any(values[0])
        np.testing.assert_allclose(displacement, schedule.displacement(0, 19e6)+schedule.displacement(19e6, 48e6), atol=1e-8)
        save(dest/'result.json', dict(kind=kind, nodes_per_side=nodes, depth_nodes=layers,
            seed=seed, profile=model['numerical_profile'],
            input_generation_seconds=generated-start, query_check_seconds=time.perf_counter()-generated,
            compute_seconds=time.perf_counter()-start,
            actual_domain_km=schedule.run.length, fault_count=len(schedule.run.faults),
            forcing_count=len(schedule.run.episodes), timeline_frames=len(schedule.run.timeline['frames']),
            generated_root=str(OUT),
            result_hashes={name:digest(OUT/f'seed{seed}'/name) for name in
                          ['forcing.json', 'faults.json', 'response_basis.npy', 'model_run.json']},
            worker_code_sha256=digest(__file__)))
        return
    from .elastic import ElasticBox, sample_plane
    from .forcing import source_load, diagnostic_plane
    from .response import slip_eigenstrain

    inputs = STUDY / 'inputs'
    p = load(inputs / 'model_run.json')['design_priors']
    window = load(inputs / 'window.json')
    origin = np.array(window['origin_km'])
    x = np.arange(2.5, 500, 5)
    xx, yy = np.meshgrid(x, x)
    length = p['auxiliary_km'] if kind == 'stress' else 500 + 2*p['response_buffer_km']
    start = time.perf_counter()
    box = ElasticBox(length, nodes, layers, p['reference_thickness_km'],
                     p['elastic_young_GPa']*1e9, p['elastic_poisson'],
                     support_bottom=kind == 'response')
    built = time.perf_counter()
    fields, ids = [], []
    if kind == 'stress':
        for e in load(inputs / 'forcing.json'):
            force, _ = source_load(box, e)
            u, _ = box.solve(force)
            plane = diagnostic_plane(box, u, p['diagnostic_depth_km'])*e['reference_force_N']/1e6
            fields.append(sample_plane(plane, xx+origin[0], yy+origin[1], length))
            ids.append(e['id'])
    else:
        response_origin = origin-p['response_buffer_km']
        for f in load(inputs / 'faults.json'):
            for patch in range(3):
                eps, _ = slip_eigenstrain(
                    box, f, patch, response_origin,
                    regularization_width_km=p['response_regularization_width_km'],
                    patch_half_length_km=max(f['length_km']/6, p['response_minimum_patch_half_length_km']),
                    quadrature_order=p['source_quadrature_order'])
                u, _ = box.solve(box.eigenstrain_load(eps))
                fields.append(sample_plane(box.surface(u), xx+p['response_buffer_km'],
                                           yy+p['response_buffer_km'], length)[..., 2])
                ids.append(f['id'] + ':' + str(patch))
    solved = time.perf_counter()
    dest.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dest/'fields.npz', basis=np.asarray(fields), x_km=x)
    save(dest/'result.json', dict(kind=kind, nodes_per_side=nodes, depth_nodes=layers,
        horizontal_spacing_km=length/(nodes-1), vertical_spacing_km=p['reference_thickness_km']/(layers-1),
        total_nodes=len(box.nodes), elements=len(box.tet), field_ids=ids,
        build_seconds=built-start, factor_seconds=box.factor_seconds,
        solve_seconds=solved-built, compute_seconds=solved-start,
        export_seconds=time.perf_counter()-solved,
        worker_code_sha256=digest(__file__)))


def launch(spec, cpu, force=False):
    parts = spec.split(':')
    kind, nodes, layers = parts[:3]
    seed = int(parts[3]) if len(parts)>3 else 1001
    tag = f'{kind}_n{nodes}_z{layers}' + (f'_s{seed}' if kind == 'generation' else '')
    dest = STUDY / tag
    if not force and (dest/'resource.json').exists() and load(dest/'resource.json')['status'] == 'ok':
        return load(dest/'resource.json')
    if force and (dest/'resource.json').exists():
        prior = dest/'previous_runs'
        prior.mkdir(exist_ok=True)
        run_id = str(time.time_ns())
        for name in ('resource.json', 'result.json'):
            if (dest/name).exists():
                shutil.copy2(dest/name, prior/(run_id+'_'+name))
    dest.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
               NUMEXPR_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    if kind == 'generation':
        env['RIFTING_OUTPUT_DIRECTORY'] = str(dest/'generated')
    command = [sys.executable, '-B', '-m', 'engine.mesh_study', 'worker',
               '--kind', kind, '--nodes', nodes, '--layers', layers, '--dest', str(dest), '--cpu', str(cpu), '--seed', str(seed)]
    begin = time.perf_counter()
    peak_rss = peak_private = 0
    status = 'running'
    with (dest/'worker.log').open('w', encoding='utf-8') as log:
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        proc = psutil.Process(child.pid)
        while child.poll() is None:
            try:
                mem = proc.memory_info()
                peak_rss = max(peak_rss, mem.rss, getattr(mem, 'peak_wset', 0))
                peak_private = max(peak_private, getattr(mem, 'private', 0))
                if peak_rss > 10*2**30 or time.perf_counter()-begin > 240:
                    status = 'resource_limit'
                    child.terminate()
                    child.wait(timeout=15)
                    break
            except psutil.NoSuchProcess:
                break
            time.sleep(.2)
        code = child.wait()
    if status == 'running':
        status = 'ok' if code == 0 and (dest/'result.json').exists() else 'failed'
    result = dict(tag=tag, status=status, exit_code=code, cpu=cpu,
                  wall_seconds=time.perf_counter()-begin, peak_rss_bytes=peak_rss,
                  peak_private_bytes=peak_private)
    save(dest/'resource.json', result)
    print(json.dumps(result), flush=True)
    return result


def compare(a, b, kind):
    from .forcing import coefficients
    from .faults import rates_at, cumulative_at
    inputs = STUDY/'inputs'
    timeline = load(inputs/'timeline.json')
    times = np.array([f['elapsed_Myr'] for f in timeline['frames']])
    if kind == 'stress':
        episodes = load(inputs/'forcing.json')
        weights = np.array([coefficients(episodes, t) for t in times])
    else:
        history = dict(np.load(inputs/'fault_history.npz'))
        weights = np.array([rates_at(history, t).ravel() for t in times])
    aa, bb = a.reshape(len(a), -1), b.reshape(len(b), -1)
    delta = aa-bb
    gram = bb@bb.T
    dg = delta@delta.T
    numerator = np.sqrt(np.maximum(np.einsum('ti,ij,tj->t', weights, dg, weights), 0))
    denominator = np.sqrt(np.maximum(np.einsum('ti,ij,tj->t', weights, gram, weights), 0))
    active = denominator > max(float(denominator.max())*1e-8, 1e-20)
    rel = numerator[active]/denominator[active]
    result = dict(relative_l2_max=float(rel.max()), relative_l2_median=float(np.median(rel)),
                  active_times=int(active.sum()), relative_l2_by_time=rel.tolist(),
                  times_Myr=times[active].tolist(), relative_basis_l2=float(np.linalg.norm(delta)/np.linalg.norm(bb)))
    if kind == 'response':
        cumulative = cumulative_at(history, 48).ravel()
        ca, cb = cumulative@aa, cumulative@bb
        result['modern_displacement_relative_l2'] = float(np.linalg.norm(ca-cb)/np.linalg.norm(cb))
        result['modern_displacement_rms_difference_m'] = float(np.sqrt(np.mean((ca-cb)**2)))
        fa, fb = a.reshape(-1, 3, *a.shape[1:]).sum(axis=1), b.reshape(-1, 3, *b.shape[1:]).sum(axis=1)
        result['per_fault_relative_l2'] = (np.linalg.norm((fa-fb).reshape(len(fa), -1), axis=1)/np.maximum(np.linalg.norm(fb.reshape(len(fb), -1), axis=1), 1e-30)).tolist()
    return result


def summarize():
    entries = []
    for path in sorted(STUDY.glob('*/resource.json')):
        entry = load(path)
        if entry['status'] == 'ok':
            entry.update(load(path.parent/'result.json'))
        entries.append(entry)
    comparisons = []
    for i, a in enumerate(entries):
        if a['status'] != 'ok' or a['kind'] not in ('stress', 'response'):
            continue
        for b in entries[i+1:]:
            if b['status'] != 'ok' or a['kind'] != b['kind']:
                continue
            if a['depth_nodes'] != b['depth_nodes'] and a['nodes_per_side'] != b['nodes_per_side']:
                continue
            first, second = sorted([a, b], key=lambda e: (e['nodes_per_side'], e['depth_nodes']))
            aa = np.load(STUDY/first['tag']/'fields.npz')['basis']
            bb = np.load(STUDY/second['tag']/'fields.npz')['basis']
            comparisons.append(dict(coarser=first['tag'], finer=second['tag'],
                axis='horizontal' if a['depth_nodes'] == b['depth_nodes'] else 'vertical',
                **compare(aa, bb, a['kind'])))
    save(STUDY/'summary.json', dict(entries=entries, comparisons=comparisons))
    for c in comparisons:
        print(c['coarser'], 'to', c['finer'], 'max', round(c['relative_l2_max']*100, 3),
              'median', round(c['relative_l2_median']*100, 3), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['run', 'worker', 'summary'])
    ap.add_argument('--jobs', default='stress:65:5,stress:97:5,stress:129:5,stress:161:5,response:41:9,response:49:9,response:65:9,response:81:9')
    ap.add_argument('--kind', choices=['stress', 'response', 'generation'])
    ap.add_argument('--nodes', type=int)
    ap.add_argument('--layers', type=int)
    ap.add_argument('--dest', type=Path)
    ap.add_argument('--cpu', type=int, default=0)
    ap.add_argument('--seed', type=int, default=1001)
    ap.add_argument('--cpus', default='0,2')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    if args.mode == 'worker':
        psutil.Process().cpu_affinity([args.cpu])
        worker(args.kind, args.nodes, args.layers, args.dest, args.seed)
    elif args.mode == 'summary':
        summarize()
    else:
        prepare()
        jobs = args.jobs.split(',')
        # Two independent single-core runs; separate physical-core affinity on this host.
        cpus = [int(value) for value in args.cpus.split(',')]
        groups = [jobs[i::len(cpus)] for i in range(len(cpus))]
        def group(specs, cpu):
            return [launch(spec, cpu, args.force) for spec in specs]
        started = time.perf_counter()
        suite = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(cpus)) as pool:
            futures = [pool.submit(group, specs, cpu) for specs, cpu in zip(groups, cpus)]
            for future in futures:
                suite.extend(future.result())
        record = dict(jobs=jobs, cpus=cpus, wall_seconds=time.perf_counter()-started,
                      results=suite, peak_rss_sum_upper_bound_bytes=sum(r['peak_rss_bytes'] for r in suite),
                      peak_memory_identity='sum of individual peaks; conservative upper bound, not simultaneous peak')
        save(STUDY/f'suite_{time.time_ns()}.json', record)
        print('Suite wall seconds', record['wall_seconds'], flush=True)
        summarize()


if __name__ == '__main__':
    main()
