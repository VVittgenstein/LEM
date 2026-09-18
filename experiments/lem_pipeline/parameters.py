"""Class-3 process parameters and their arrays (K, D, precipitation) plus the marine parameter set.

Decisions (2026-09-09): K takes the Li 2025 Himalaya calibration (2.6 to 4.0e-6 m^0.1/yr with m = 0.45, n = 1) as the
hard-rock centre; softer lithologies are scaled by the Stock & Montgomery class ratios (interim scheme B of the third
class, an assumption until workstream A delivers 1 km calibrations); D = 0.01 m²/yr (Li 2025 fixed value, not
calibrated at 1 km); G = 1 (Li 2025); precipitation multiplier drawn between 0.2 and 3 m/yr relative to P0 = 1
(log-uniform, spans more than one order of magnitude) and applied uniformly in this version; marine parameters take
one of the three Glerum 2024 sets as a whole (yZz 2026-09-09).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .distributions import sample_range
from .driver import MarineParams, ProcessParams
from .landmask import power_law_field

ASSUMPTION = "尚待验证的假设"
CALC = "本项目借鉴或合成改造"
DIRECT = "来源直接给出"

GLERUM_PAIRS = ((120.0, 40.0), (210.0, 70.0), (300.0, 100.0))
LITHOLOGY_CLASSES = {  # multiplier ranges relative to the hard-rock centre (Stock & Montgomery class ratios; assumption)
    "crystalline": (0.6, 1.5),
    "volcaniclastic": (10.0, 100.0),
    "mudstone": (100.0, 1000.0),
}


@dataclass
class ParameterSample:
    k_hard: float
    lithology_zones: list[dict]
    D: float
    G: float
    m: float
    n: float
    precip_multiplier: float
    marine: dict
    evidence: dict


def sample_parameters(rng: np.random.Generator, land: np.ndarray, dx_km: float = 1.0, n_zones: int | None = None,
                      seed_field: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, ProcessParams, MarineParams, ParameterSample]:
    """Return (kf array, kd array, precip array, ProcessParams, MarineParams, sample record)."""
    ny, nx = land.shape
    k_hard = float(sample_range(rng, 2.6e-6, 4.0e-6, force="uniform"))
    n_zones = n_zones if n_zones is not None else int(rng.integers(1, 4))  # 1 to 3 lithology zones
    kf = np.full((ny, nx), k_hard)
    zones = []
    if n_zones > 1:
        fld = power_law_field(np.random.default_rng(seed_field if seed_field is not None else int(rng.integers(1 << 31))), ny, nx, 3.5, dx_km, 5.0)
        cuts = np.quantile(fld, np.linspace(0, 1, n_zones + 1)[1:-1])
        zone_id = np.digitize(fld, cuts)
        names = list(LITHOLOGY_CLASSES)
        for z in range(n_zones):
            cls = names[0] if z == 0 else str(rng.choice(names[1:]))
            lo, hi = LITHOLOGY_CLASSES[cls]
            mult = float(sample_range(rng, lo, hi))
            kf[zone_id == z] = k_hard * mult
            zones.append({"zone": z, "lithology": cls, "k_multiplier": mult, "area_fraction": float((zone_id == z).mean())})
    else:
        zones.append({"zone": 0, "lithology": "crystalline", "k_multiplier": 1.0, "area_fraction": 1.0})
    D = 0.01
    G = 1.0
    precip_mult = float(sample_range(rng, 0.2, 3.0))
    precip = np.full((ny, nx), precip_mult)
    pair = GLERUM_PAIRS[int(rng.integers(len(GLERUM_PAIRS)))]
    marine = MarineParams(kds1=pair[0], kds2=pair[1], ratio=0.5, poro1=0.0, poro2=0.0, layer=1000.0)
    process = ProcessParams(m=0.45, n=1.0, g1=G, g2=G, p=1.0, kfsed=-1.0, kdsed=-1.0)
    rec = ParameterSample(k_hard=k_hard, lithology_zones=zones, D=D, G=G, m=0.45, n=1.0, precip_multiplier=precip_mult,
                          marine=asdict(marine),
                          evidence={"k_hard": ("Li 2025 1 km calibration, m=0.45 n=1", CALC), "lithology_multipliers": ("Stock & Montgomery class ratios", ASSUMPTION),
                                    "D": ("Li 2025 fixed value", ASSUMPTION), "G": ("Li 2025 setting; Guérit range 0 to 3.1", ASSUMPTION),
                                    "precip": ("0.2 to 3 m/yr relative, uniform in space", ASSUMPTION), "marine": ("Glerum 2024 parameter set", DIRECT)})
    return kf, np.full((ny, nx), D), precip, process, marine, rec
