"""Paths and read-only reuse of the selected mask generator."""
import os
import sys
from pathlib import Path

for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_key] = '1'

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
MASK_CODE = ROOT / 'data_generation/stage/mask_generator'
sys.path.insert(0, str(MASK_CODE))
MASK_BATCH = ROOT / 'output/mask_generator/world_orogen_gibbs_layers_3/partitions_512'
REFERENCE = ROOT / 'references/data/2026-09-09-q1-pretasks/F/stations'
COHORT = ROOT / 'docs/work/2026-09-09-q1-pretasks/F-periphery-150km/scripts/reference-cohort.json'
OUTPUT = ROOT / 'output/seafloor_generator/mean_distance_v1'
SEEDS = tuple(range(1001, 1007))
VERSION = 'seafloor-types-1.0.0'

from common.io import read_json, write_json, write_csv, file_sha256, array_sha256  # noqa: E402,F401
from common.render import font  # noqa: E402,F401
from world_orogen_gibbs.geometry import geometry  # noqa: E402,F401
