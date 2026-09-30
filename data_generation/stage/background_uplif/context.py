"""Paths, units and read-only reuse for the background vertical-motion stage."""
import os
import sys
from pathlib import Path

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"

CODE = Path(__file__).resolve().parent
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
OUTPUT = CODE / "output"
MASK_CODE = ROOT / "data_generation/stage/mask_generator"
MASK_BATCH = ROOT / "output/mask_generator/world_orogen_gibbs_layers_3/partitions_512"
for path in (MASK_CODE, ROOT / "viewer"):
    if str(path) not in sys.path:
        sys.path.append(str(path))
from common.io import read_json, write_json, write_csv, file_sha256, array_sha256, utc_now
from world_orogen_gibbs.geometry import geometry
from lem_viewer.colormaps import BandedScale

SEEDS = tuple(range(1001, 1007))
AGES_MA = (48., 39., 29., 19., 9., 0.)
ELAPSED_MYR = (0., 9., 19., 29., 39., 48.)
VERSION = "background-uplif-1.0.0"


def output_folder(value=None):
    path = Path(value).resolve() if value else OUTPUT.resolve()
    if not path.is_relative_to(CODE.resolve()) or path == CODE.resolve():
        raise ValueError("Output must be a child directory of this module")
    marker = path / ".background_uplif.json"
    if path.exists() and any(path.iterdir()) and not marker.exists():
        raise ValueError("Existing nonempty directory has no module identity marker")
    path.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        write_json(marker, {"module": "background_uplif", "created_utc": utc_now()})
    return path


def load_mask(seed):
    import numpy as np
    folder = MASK_BATCH / f"seed{seed}"
    mask = np.load(folder / "mask.npy", allow_pickle=False)
    labels = np.load(folder / "partitions.npy", allow_pickle=False)
    config = read_json(folder / "config.json")
    settings = config.get("settings", config)
    if mask.shape != (500, 500) or mask.dtype != bool or labels.shape != mask.shape:
        raise ValueError("500x500 Boolean mask and matching partition array required")
    if settings["partition_count"] != 512 or settings["boundary_layers"] != 3:
        raise ValueError("Selected 512-partition, 3-layer input required")
    total = np.bincount(labels.ravel(), minlength=513)[1:]
    counts = np.bincount(labels[mask], minlength=513)[1:]
    if not np.all((counts == 0) | (counts == total)) or total.size != 512:
        raise ValueError("Mask must select whole partitions")
    hashes = [{"path": str(folder / name), "sha256": file_sha256(folder / name)}
              for name in ("mask.npy", "partitions.npy", "config.json", "contours.json")]
    return {"seed": seed, "mask": mask, "labels": labels, "state": counts > 0,
            "geometry": geometry(labels, boundary_layers=3),
            "contours": read_json(folder / "contours.json"), "source_hashes": hashes}
