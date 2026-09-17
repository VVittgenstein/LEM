from pathlib import Path
import csv, hashlib, json, os, shutil
import numpy as np

ROOT = Path(__file__).resolve().parent
AXIS_ROOT = ROOT.parent
REPO = AXIS_ROOT.parent.parent
RAW = ROOT / 'sources'
MODELS = ROOT / 'models'
CHECKS = ROOT / 'checks'
OUT = ROOT / 'output'
VERSION = 'ds5-complete-field-v1'
os.environ.setdefault('MPLCONFIGDIR', str(CHECKS / 'matplotlib_cache'))

def initialize():
    for p in (RAW, MODELS, CHECKS, OUT): p.mkdir(parents=True, exist_ok=True)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def jsave(path, obj):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def jload(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def csvsave(path, rows):
    rows = list(rows); path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader(); w.writerows(rows)

def rng(seed, stream): return np.random.default_rng(np.random.SeedSequence([20260915, int(seed), 89231, int(stream)]))

def freeze():
    initialize()
    case = REPO/'references/2026-09-13-geological-activity-parameters'
    pairs = [(case/'sources/C03/2024JB030625_DS5_ENU_velocity.txt', RAW/'DS5_ENU_velocity.txt'),
             (case/'sources/C03/article.pdf', RAW/'McGrath2025.pdf'),
             (case/'sources/C03/article.txt', RAW/'McGrath2025.txt'),
             (case/'sources/C06/article.pdf', RAW/'Herman2009.pdf'),
             (AXIS_ROOT/'sources/G/landmass-provinces.csv', RAW/'G_landmass_provinces.csv'),
             (AXIS_ROOT/'sources/G/data_dictionary.md', RAW/'G_data_dictionary.md'),
             (REPO/'src/lem_viewer/colormaps.py', RAW/'viewer_colormaps.py')]
    for ext in ('shp','shx','dbf','prj','cpg'):
        p=REPO/f'datasets/2026-09-08-q1-data/D/global_gprv.{ext}'
        if p.exists(): pairs.append((p, RAW/p.name))
    records=[]
    for src, dst in pairs:
        if not dst.exists(): shutil.copyfile(src, dst)
        if sha(src)!=sha(dst): raise ValueError(f'Frozen source differs: {dst}')
        records.append(dict(original=str(src),copy=str(dst.relative_to(ROOT)),sha256=sha(dst),bytes=dst.stat().st_size))
    jsave(RAW/'manifest.json', {'files':records,'DS5_url':'https://zenodo.org/records/15541458',
      'DS5_quantity':'GNSS-referenced up velocity, column 8, mm/yr; error column 9',
      'DS7_used':False,'G_commit':'6cdcbf021178e9adf65e7f9c3d77c5497a976bf4'})
    return records

def plotting():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,
       'svg.fonttype':'none','svg.hashsalt':VERSION,'path.simplify':False,'font.size':10})
    return plt
