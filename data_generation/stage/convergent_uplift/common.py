"""Paths and provenance helpers for the complete-axis pipeline."""
from pathlib import Path
import csv,hashlib,json
import numpy as np

ROOT=Path(__file__).resolve().parent
MASTER_SEED=20260915
VERSION='complete-axis-v1'

def rng_for(seed,stream,attempt=0):
    return np.random.default_rng(np.random.SeedSequence([MASTER_SEED,int(seed),int(stream),int(attempt)]))

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def write_csv(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()

def code_hashes():return {p.name:sha(p) for p in sorted(ROOT.glob('*.py'))}
