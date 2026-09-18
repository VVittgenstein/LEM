"""Run explicitly configured test groups in their required local environments."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('suites.json'))
    parser.add_argument('--group', action='append', default=[])
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/tests')
    parser.add_argument('extra', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.list:
        for name, suite in config['suites'].items():
            print(f"{name:24} {suite['kind']:10} {'default' if suite.get('default', False) else 'explicit':8} {suite['description']}")
        return 0
    names = args.group or [name for name, s in config['suites'].items() if s.get('default')]
    unknown = set(names) - config['suites'].keys()
    if unknown:
        parser.error('Unknown groups: ' + ', '.join(sorted(unknown)))
    args.output.mkdir(parents=True, exist_ok=True)
    outcomes = []
    for name in names:
        suite = config['suites'][name]
        interpreter = ROOT / config['interpreters'][suite['environment']]
        env = dict(os.environ)
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', OMP_NUM_THREADS='1',
                   OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
        env['PYTHONPATH'] = os.pathsep.join(str(ROOT / p) for p in suite.get('paths', []))
        env['LEM_TEST_OUTPUT'] = str(args.output.resolve() / name)
        env['LEM_MASK_TEST_OUTPUT'] = str(args.output.resolve() / name / 'sampler')
        env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
        env['MPLCONFIGDIR'] = str(args.output.resolve() / 'matplotlib')
        extra = args.extra[1:] if args.extra[:1] == ['--'] else args.extra
        if suite['kind'] == 'pytest':
            # pytest and its pure-Python helpers may be available in the viewer
            # environment. Append that location after the selected interpreter's
            # own libraries so its NumPy/SciPy installations retain precedence.
            support = ROOT / config['pytest_support']
            bootstrap = 'import sys;sys.path.append(sys.argv.pop(1));import pytest;raise SystemExit(pytest.main(sys.argv[1:]))'
            command = [str(interpreter), '-B', '-c', bootstrap, str(support), '-q', '-p', 'no:cacheprovider', *suite['args'], *extra]
        elif suite['kind'] == 'unittest':
            if suite.get('modules'):
                env['PYTHONPATH'] = str(ROOT / suite['test_dir']) + os.pathsep + env['PYTHONPATH']
                command = [str(interpreter), '-B', '-m', 'unittest', '-v', *suite['modules'], *extra]
            else:
                command = [str(interpreter), '-B', '-m', 'unittest', 'discover', '-s', str(ROOT / suite['test_dir']), '-p', suite.get('pattern', 'test_*.py'), '-v', *extra]
        else:
            command = [str(interpreter), '-B', str(ROOT / suite['script']), *suite.get('args', []), *extra]
        started = time.perf_counter()
        print(f'Running {name}', flush=True)
        try:
            completed = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            code, output = completed.returncode, completed.stdout
        except OSError as exc:
            code, output = 127, str(exc)
        log = args.output / f'{name}.log'
        log.write_text(output, encoding='utf-8')
        outcome = {'group': name, 'returncode': code, 'seconds': time.perf_counter() - started, 'command': command, 'log': str(log)}
        outcomes.append(outcome)
        print(output[-2500:] if code else output[-600:], flush=True)
        (args.output / 'summary.json').write_text(json.dumps(outcomes, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return int(any(row['returncode'] for row in outcomes))


if __name__ == '__main__':
    raise SystemExit(main())
