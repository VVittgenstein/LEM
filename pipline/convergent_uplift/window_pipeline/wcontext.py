"""All mutable window-stage artifacts stay under this directory."""
import csv,hashlib,json,os
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent
REPO=PARENT.parent.parent
FIELD=PARENT/'field_pipeline'
INPUT=ROOT/'inputs'
VENDOR=ROOT/'vendor'
BASE=ROOT/'bases'
OUT=ROOT/'output'
CHECKS=ROOT/'checks'
VERSION='boundary-entry-window-v1'
PYTHON=REPO/'docs/work/2026-09-08-q1-data/D-landform-statistics/.venv/Scripts/python.exe'
os.environ['MPLCONFIGDIR']=str(CHECKS/'matplotlib_cache')
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'

def init():
    for p in (INPUT,VENDOR,BASE,OUT,CHECKS):p.mkdir(parents=True,exist_ok=True)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def csvsave(p,rows):
    rows=list(rows)
    with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def rng(seed,stream=0):return np.random.default_rng(np.random.SeedSequence([20260916,int(seed),87023,int(stream)]))
def plotting():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,
       'svg.fonttype':'none','svg.hashsalt':VERSION,'path.simplify':False})
    return plt
