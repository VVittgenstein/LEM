"""Paths, serialization and reproducible streams for the temporal stage."""
from pathlib import Path
import csv, hashlib, json, os
import numpy as np

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
REPO = PARENT.parent.parent
SOURCES = ROOT / 'sources'
MODELS = ROOT / 'models'
CHECKS = ROOT / 'checks'
OUT = ROOT / 'output'
VERSION = 'convergent-independent-events-v3'
PYTHON = REPO / 'docs/work/2026-09-08-q1-data/D-landform-statistics/.venv/Scripts/python.exe'
os.environ['MPLCONFIGDIR'] = str(CHECKS / 'matplotlib_cache')
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'

EPOCHS = [
    ('Eocene', '始新世', 48., 33.9),
    ('Oligocene', '渐新世', 33.9, 23.04),
    ('Miocene', '中新世', 23.04, 5.333),
    ('Pliocene', '上新世', 5.333, 2.58),
    ('Pleistocene', '更新世', 2.58, .0117),
    ('Holocene', '全新世', .0117, 0.),
]

def init():
    for p in (SOURCES, MODELS, CHECKS, OUT): p.mkdir(parents=True, exist_ok=True)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def save(path, obj):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def csvsave(path, rows):
    rows = list(rows); p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader(); w.writerows(rows)

def rng(seed, stream=0):
    return np.random.default_rng(np.random.SeedSequence([20260917, int(seed), 43019, int(stream)]))

def plotting():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'axes.unicode_minus': False,
                         'svg.fonttype': 'none', 'svg.hashsalt': VERSION, 'font.size': 10})
    return plt

def epoch_index(sim_myr):
    for i, (_, _, old, young) in enumerate(EPOCHS):
        if 48-old <= sim_myr < 48-young: return i
    return None
