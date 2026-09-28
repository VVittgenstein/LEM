"""Command-line stages, using only the existing project environment."""
import argparse
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from .common import *

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['prepare', 'fit', 'generate', 'resample', 'render', 'audit', 'all'], default='all')
    parser.add_argument('--seeds', type=int, nargs='+', default=list(range(1001, 1009)))
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError('Outputs must remain inside this module')
    if not 1 <= args.workers <= 8:
        raise ValueError('One to eight single-core workers')
    if len(set(args.seeds)) != len(args.seeds):
        raise ValueError('Seed list must be unique')
    initialize(); output.mkdir(parents=True, exist_ok=True)
    if args.stage in ('prepare', 'all'):
        from .prepare import prepare
        prepare()
    if args.stage in ('fit', 'all'):
        from .fit import fit_models
        fit_models()
    if args.stage in ('generate', 'all'):
        from .pipeline import generate_world
        started = time.perf_counter(); worlds = []
        if args.workers == 1:
            worlds = [generate_world(seed, output) for seed in args.seeds]
        else:
            with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('spawn')) as pool:
                futures = {pool.submit(generate_world, seed, output): seed for seed in args.seeds}
                for future in as_completed(futures):
                    worlds.append(future.result())
                    print('World complete:', futures[future], flush=True)
        worlds.sort(key=lambda r: r['seed'])
        save(output/'batch.json', dict(worlds=worlds, events=[e for w in worlds for e in w['events']],
             elapsed_batch_seconds=time.perf_counter()-started, workers=args.workers,
             timing_scope='generation, source-field queries, frame arrays and integrals; excludes figure rendering',
             model_hashes={p.name: sha(p) for p in MODELS.glob('*.json')},
             source_manifest_sha256=sha(SOURCES/'manifest.json')))
    if args.stage == 'resample':
        from .resampling import resample
        resample(output, args.workers)
    if args.stage in ('render', 'all'):
        from .rendering import render_all
        render_all(output)
    if args.stage in ('audit', 'all'):
        from .verify import audit
        if not audit(output)['passed']:
            raise SystemExit('Saved-product audit failed; see audit.json')

if __name__ == '__main__':
    main()
