"""Approved numerical conventions. Coordinates refer to cell centres."""
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

VERSION = "1.0.0"
SIZE = 500
DX_KM = 1.0
BAND = 10
WINDOWS = (1, 5, 25)
COEFFICIENTS = (0.005, 0.015, 0.050)
TEMPLATE_SIZE = 1024
PIXELS_PER_UNIT = 500.0
CALIBRATION_SEEDS = tuple(range(64))
STRETCHES = (0.50, 0.75, 1.00, 1.25, 1.50)
GAINS = (0.50, 1.00, 2.00, 4.00)
METHODS = ("ellipse", "reference_overlay")
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
# common/config.py -> mask_generator -> pipline -> repository
POPULATION = ROOT / "docs/work/2026-09-08-q1-data/merged/data-package/pop34/population-members.csv"
REFERENCE_TABLE = ROOT / "docs/work/2026-09-08-q1-data/D-landform-statistics/tables/reference-landmasses.csv"
REFERENCE_MASKS = ROOT / "references/data/2026-09-08-q1-data/D/derived-1km-masks"
GSHHG = ROOT / "references/data/2026-09-08-q1-data/D/gshhs_f.b"
DEFAULT_OUTPUT = ROOT / "output/mask_generator"


@dataclass
class SharedSample:
    seed: int
    target_fraction: float
    angle_deg: float
    center_x_km: float
    center_y_km: float
    fields: dict[int, np.ndarray] = field(repr=False)
    rng_info: dict = field(default_factory=dict)

    def describe(self) -> dict:
        return {"seed": self.seed, "target_fraction": self.target_fraction,
                "target_cells": round(self.target_fraction * SIZE * SIZE),
                "angle_deg": self.angle_deg, "center_x_km": self.center_x_km,
                "center_y_km": self.center_y_km, "windows_km": list(WINDOWS),
                "rng": self.rng_info}


@dataclass
class MaskResult:
    method: str
    shared: SharedSample
    envelope: np.ndarray = field(repr=False)
    combined: np.ndarray = field(repr=False)
    mask: np.ndarray = field(repr=False)
    threshold: dict
    parameters: dict

