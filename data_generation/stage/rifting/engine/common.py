from __future__ import annotations
import hashlib,json,os
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'/'generation_v1'
END=48.0

def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    def encode(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        raise TypeError(type(x).__name__)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=encode,allow_nan=False)+'\n',encoding='utf-8')

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def rng(seed,stream):return np.random.default_rng(np.random.SeedSequence([int(seed),int(stream)]))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def smooth(x):
    x=np.clip(x,0,1);return x*x*(3-2*x)

def envelope(episode,t):
    a,b,c,d=episode['knots_Myr']
    x=np.asarray(t,dtype=float)
    return smooth((x-a)/max(b-a,1e-12))*smooth((d-x)/max(d-c,1e-12))

def stress_display(s):
    """Horizontal differential stress and extension principal axis, tension positive."""
    xx,yy,xy=s[...,0],s[...,1],s[...,3]
    mag=np.sqrt((xx-yy)**2+4*xy**2)
    angle=.5*np.arctan2(2*xy,xx-yy)
    return mag,angle

def phase_records(episode):
    a,b,c,d=episode['knots_Myr']
    return [dict(name=name,start_year=x*1e6,end_year=y*1e6) for name,x,y in [('增强',a,b),('维持',b,c),('减弱',c,d)] if y>x]
