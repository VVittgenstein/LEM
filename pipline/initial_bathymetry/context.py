"""Local paths and read-only reuse of the accepted mask and sea-type stages."""
import os
import sys
from pathlib import Path

for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='1'
os.environ.setdefault('PYTHONIOENCODING','utf-8')

ROOT=Path(__file__).resolve().parents[2]
CODE=Path(__file__).resolve().parent
MASK_CODE=ROOT/'pipline/mask_generator'
SEA_CODE=ROOT/'pipline/seafloor_generator'
for folder in (MASK_CODE,SEA_CODE):
    if str(folder) not in sys.path:sys.path.append(str(folder))
from common.io import read_json,write_json,write_csv,file_sha256,array_sha256
from coast import load_sample

MASK_BATCH=ROOT/'output/mask_generator/world_orogen_gibbs_layers_3/partitions_512'
SEA_BATCH=ROOT/'output/seafloor_generator/mean_distance_v1'
F_STATIONS=ROOT/'datasets/2026-09-09-q1-pretasks/F/stations'
COHORT=ROOT/'docs/work/2026-09-09-q1-pretasks/F-periphery-150km/scripts/reference-cohort.json'
ROUGHNESS_TABLE=ROOT/'docs/work/2026-09-08-q1-data/A-initial-elevation-sealevel/tables/spatial-quantiles.csv'
OUTPUT=ROOT/'output/initial_bathymetry/fixed_profiles_v1'
SEEDS=tuple(range(1001,1007))
VERSION='initial-bathymetry-1.0.0'


def load_input(seed):
    import numpy as np
    sample=load_sample(seed)
    folder=SEA_BATCH/f'seed{seed}'
    sample['sea_type']=np.load(folder/'seafloor_type.npy',allow_pickle=False)
    sample['region_types']=np.load(folder/'region_types.npy',allow_pickle=False)
    if not np.array_equal(sample['sea_type']==0,sample['mask']):
        raise ValueError('Accepted sea types do not match the accepted platform')
    if not np.array_equal(sample['sea_type'],sample['region_types'][sample['labels']-1]):
        raise ValueError('Accepted types split an input partition')
    sample['sea_folder']=folder
    paths=[sample['path']/name for name in ('mask.npy','partitions.npy','contours.json','config.json')]
    paths += [folder/name for name in ('seafloor_type.npy','region_types.npy','config.json','metrics.json')]
    paths += [SEA_BATCH/'distance'/f'seed{seed}'/'measurement.npz']
    sample['source_hashes']=[dict(path=str(p),sha256=file_sha256(p)) for p in paths]
    return sample


def check_hashes(rows):
    return all(file_sha256(Path(r['path']))==r['sha256'] for r in rows)
