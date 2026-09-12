"""One chronological sea-level reconstruction from 48 Ma BP to the present.

Data are selected by age. Two local overlap windows connect the sources.
The stored master retains the published vertical datum and present estimate;
a simulation window can independently set its initial sea level to zero.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path

for _variable in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_variable]='1'

import numpy as np
from scipy.interpolate import PchipInterpolator

CODE=Path(__file__).resolve().parent
ROOT=CODE.parents[1]
DATA=ROOT/'datasets/2026-09-08-q1-data/A'
OUTPUT=CODE/'output'
VERSION='sea-level-chronological-1.0.0'
MAX_AGE=48_000_000.
KEYS=('miller_smoothed','miller_unsmoothed','spratt_2016')
WINDOWS={'young':[794_000.,798_000.],'old':[980_000.,1_000_000.]}
SOURCE_FILES={
    'miller_smoothed':('miller2020-smoothed.tab','https://doi.org/10.1594/PANGAEA.923139'),
    'miller_unsmoothed':('miller2020-unsmoothed.tab','https://doi.org/10.1594/PANGAEA.923126'),
    'spratt_2016':('spratt2016-noaa.txt','https://doi.org/10.25921/rd66-5820'),
}


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    def convert(v):
        if isinstance(v,np.ndarray):return v.tolist()
        if isinstance(v,np.generic):return v.item()
        if isinstance(v,Path):return str(v)
        raise TypeError(type(v).__name__)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=convert)+'\n',encoding='utf-8')


def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def pangaea_rows(path):
    lines=Path(path).read_text(encoding='utf-8').split('*/',1)[1].strip().splitlines()
    header=lines[0].split('\t')
    age_col=next(i for i,v in enumerate(header) if v.startswith('Age [ka BP]'))
    sea_col=next(i for i,v in enumerate(header) if v.startswith('Sea lev rel [m]'))
    rows=[];invalid=0
    for line in csv.reader(lines[1:],delimiter='\t'):
        if not line or not line[age_col] or not line[sea_col]:invalid+=1;continue
        a,z=float(line[age_col])*1000.,float(line[sea_col])
        if np.isfinite(a) and np.isfinite(z):rows.append((a,z))
        else:invalid+=1
    pairs=np.asarray(rows,float);pairs=pairs[np.argsort(pairs[:,0],kind='stable')]
    return pairs,dict(invalid_rows=invalid,age_column=header[age_col],sea_level_column=header[sea_col])


def source_bundle(data=DATA):
    result={}
    for key,(name,doi) in SOURCE_FILES.items():
        path=Path(data)/name
        if key=='spratt_2016':
            lines=[s for s in path.read_text(encoding='utf-8').splitlines() if s and not s.startswith('#')]
            raw=list(csv.DictReader(lines,delimiter='\t'))
            pairs=np.array([(float(v['age_calkaBP'])*1000,float(v['SeaLev_longPC1'])) for v in raw])
            if not np.isfinite(pairs).all():raise ValueError('Missing Spratt five-record stack value')
            metadata=dict(age_column='age_calkaBP',sea_level_column='SeaLev_longPC1',invalid_rows=0,
                original_uncertainty=[dict(age_yr_bp=float(v['age_calkaBP'])*1000,sigma_m=float(v['SeaLev_longPC1_err_sig']),
                     lower95_m=float(v['SeaLev_longPC1_err_lo']),upper95_m=float(v['SeaLev_longPC1_err_up'])) for v in raw])
            full=pairs.copy()
        else:
            full,metadata=pangaea_rows(path)
            if key=='miller_smoothed':pairs=full[full[:,0]<=MAX_AGE]
            else:
                # Only the bridge and its overlaps are used. Include two
                # neighboring observations to define endpoint interpolation.
                # Retain support for the documented 1..20 kyr overlap check.
                lo=max(0,int(np.searchsorted(full[:,0],778_000.))-2)
                hi=min(len(full),int(np.searchsorted(full[:,0],WINDOWS['old'][1],side='right'))+2)
                pairs=full[lo:hi]
        if len(pairs)<3 or not (np.diff(pairs[:,0])>0).all():
            raise ValueError(f'Nonunique or unordered ages in the used {key} interval')
        metadata.update(path=str(path),sha256=file_hash(path),doi=doi,
             original_rows=len(full),original_age_range_yr_bp=[float(full[0,0]),float(full[-1,0])],
             original_duplicate_age_count=len(full)-len(np.unique(full[:,0])),
             used_rows=len(pairs),used_age_range_yr_bp=[float(pairs[0,0]),float(pairs[-1,0])],
             age_units='years before present',sea_level_units='m, nominally relative to modern sea level')
        result[key]=dict(age_yr_bp=pairs[:,0].tolist(),sea_level_m=pairs[:,1].tolist(),metadata=metadata)
    return dict(version=VERSION,domain_yr_bp=[0.,MAX_AGE],transition_windows_yr_bp=WINDOWS,
                interpolation='PCHIP, extrapolation disabled',sources=result,
                chronology='published age models retained; no added age warping',
                vertical_datum='published relative-to-modern values retained; no independent component demeaning',
                window_basis='old overlap 20 kyr, one Miller smoothed sampling interval; young overlap 4 kyr, shortest tested 1 kyr multiple with composite peak rate no greater than source peak rate in that interval',
                joining='age selection outside overlap windows; local convex smoothstep weights within overlaps')


def smoothstep(t):
    t=np.clip(np.asarray(t,float),0,1)
    return t**3*(10-15*t+6*t*t)


def smoothstep_derivative(t):
    t=np.clip(np.asarray(t,float),0,1)
    return 30*t*t*(1-t)**2


class SeaLevelCurve:
    def __init__(self,bundle):
        if bundle['version']!=VERSION:raise ValueError('Unsupported sea-level model version')
        self.bundle=bundle;self.windows=bundle['transition_windows_yr_bp']
        self.interpolators={}
        for key in KEYS:
            s=bundle['sources'][key]
            self.interpolators[key]=PchipInterpolator(s['age_yr_bp'],s['sea_level_m'],extrapolate=False)

    @classmethod
    def from_files(cls,data=DATA):return cls(source_bundle(data))

    @classmethod
    def from_bundle(cls,path):return cls(read_json(path))

    @staticmethod
    def _ages(age):
        a=np.asarray(age,float)
        if not np.isfinite(a).all() or np.any((a<0)|(a>MAX_AGE)):
            raise ValueError('Requested age is outside 0..48,000,000 yr BP')
        return a,a.ravel()

    def weights(self,age):
        shape,a=self._ages(age);w=np.zeros((len(a),3));dw=np.zeros_like(w)
        yl,yh=self.windows['young'];ol,oh=self.windows['old']
        w[a<=yl,2]=1;w[(a>=yh)&(a<=ol),1]=1;w[a>=oh,0]=1
        for lo,hi,young,old in ((yl,yh,2,1),(ol,oh,1,0)):
            use=(a>lo)&(a<hi);t=(a[use]-lo)/(hi-lo)
            q=smoothstep(t);dq=smoothstep_derivative(t)/(hi-lo)
            w[use,young]=1-q;w[use,old]=q;dw[use,young]=-dq;dw[use,old]=dq
        return w.reshape(shape.shape+(3,)),dw.reshape(shape.shape+(3,))

    def _evaluate(self,age,derivative=False):
        shape,a=self._ages(age);w,dw=self.weights(a);out=np.zeros(len(a))
        for j,key in enumerate(KEYS):
            use=(w[:,j]!=0)|(dw[:,j]!=0)
            if not use.any():continue
            v=self.interpolators[key](a[use])
            if not np.isfinite(v).all():raise ValueError(f'Attempted extrapolation of {key}')
            if derivative:out[use]+=dw[use,j]*v+w[use,j]*self.interpolators[key](a[use],nu=1)
            else:out[use]+=w[use,j]*v
        return float(out[0]) if shape.ndim==0 else out.reshape(shape.shape)

    def at_age(self,age_yr_bp):return self._evaluate(age_yr_bp)

    def derivative_by_age(self,age_yr_bp):
        """m per year towards older ages; forward-time derivative has opposite sign."""
        return self._evaluate(age_yr_bp,derivative=True)

    def unblended(self,age):
        shape,a=self._ages(age);out=np.empty(len(a))
        for key,use in ((KEYS[0],a>=980000),(KEYS[1],(a>=798000)&(a<980000)),(KEYS[2],a<798000)):
            if use.any():out[use]=self.interpolators[key](a[use])
        return float(out[0]) if shape.ndim==0 else out.reshape(shape.shape)

    def regimes(self,age):
        w,_=self.weights(age);w=w.reshape(-1,3)
        names=np.array(KEYS,dtype='U40')[np.argmax(w,axis=1)]
        names[(w[:,0]>0)&(w[:,1]>0)]='transition_unsmoothed_to_smoothed'
        names[(w[:,1]>0)&(w[:,2]>0)]='transition_spratt_to_unsmoothed'
        return names

    def window(self,start_age_yr_bp,duration_yr,step_yr=1000.,zero_initial=True):
        """Extract a continuous forward-time interval of the same master curve."""
        values=np.array([start_age_yr_bp,duration_yr,step_yr],float)
        if not np.isfinite(values).all() or duration_yr<0 or step_yr<=0 or not 0<=duration_yr<=start_age_yr_bp<=MAX_AGE:
            raise ValueError('Invalid simulation interval or step')
        t=np.r_[np.arange(0.,duration_yr,step_yr),float(duration_yr)]
        age=float(start_age_yr_bp)-t;level=self.at_age(age)
        reference=float(self.at_age(start_age_yr_bp)) if zero_initial else 0.
        return dict(time_yr=t,age_yr_bp=age,sea_level_m=level-reference,reference_offset_m=reference)
