"""Local paths, units, frozen inputs and deterministic random streams."""
from pathlib import Path
import csv
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SOURCES = ROOT / 'sources'
MODELS = ROOT / 'models'
OUT = ROOT / 'output'
CHECKS = ROOT / 'checks'
REFERENCE = REPO / 'references/2026-09-13-geological-activity-parameters'
CONVERGENT = ROOT.parent / 'convergent_uplift'
BASES = CONVERGENT / 'window_pipeline/bases'
VERSION = 'basin-reference-event-20260927'
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
os.environ['MPLCONFIGDIR'] = str(CHECKS / 'matplotlib_cache')
os.environ['NUMBA_CACHE_DIR'] = str(CHECKS / 'numba_cache')

import numpy as np

EPOCHS = [('Eocene', '始新世', 48., 33.9), ('Oligocene', '渐新世', 33.9, 23.04),
          ('Miocene', '中新世', 23.04, 5.333), ('Pliocene', '上新世', 5.333, 2.58),
          ('Pleistocene', '更新世', 2.58, .0117), ('Holocene', '全新世', .0117, 0.)]

def initialize():
    for p in (SOURCES, MODELS, OUT, CHECKS):
        p.mkdir(parents=True, exist_ok=True)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def save(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def csvsave(path, rows):
    rows = list(rows)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)

def rng(seed, stream=0):
    return np.random.default_rng(np.random.SeedSequence([20260927, int(seed), 99173, int(stream)]))

def plotting():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'axes.unicode_minus': False,
                         'svg.fonttype': 'none', 'svg.hashsalt': VERSION, 'font.size': 10})
    return plt

def epoch_index(t):
    return next((i for i, (_, _, old, young) in enumerate(EPOCHS) if 48-old <= t < 48-young), None)

def physical_cpu_representatives():
    """One available logical processor from each Windows physical-core mask."""
    import psutil
    available = psutil.Process().cpu_affinity()
    if os.name != 'nt':
        return available, 'available logical processors; physical topology not resolved'
    import ctypes
    from ctypes import wintypes
    class Info(ctypes.Structure):
        _fields_ = [('mask', ctypes.c_size_t), ('relationship', ctypes.c_int), ('reserved', ctypes.c_ulonglong*2)]
    size = wintypes.DWORD()
    call = ctypes.windll.kernel32.GetLogicalProcessorInformation
    call(None, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    if not call(buffer, ctypes.byref(size)):
        raise ctypes.WinError()
    rows = (Info*(size.value//ctypes.sizeof(Info))).from_buffer(buffer)
    representatives = []
    for row in rows:
        if row.relationship == 0:
            logical = [i for i in available if row.mask & (1 << i)]
            if logical:
                representatives.append(min(logical))
    if not representatives:
        raise RuntimeError('No physical-core affinity representatives')
    return sorted(representatives), 'Windows GetLogicalProcessorInformation physical-core masks'
