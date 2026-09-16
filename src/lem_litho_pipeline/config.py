from dataclasses import dataclass, asdict
import math

PRESETS = ("sedimentary_plateau", "fold_belt", "fault_blocks", "intrusive_massif", "mosaic")
LANDFORMS = ("mountain", "hills", "plain", "canyon", "delta")
MATERIALS = [
    {"id": 0, "name": "mudstone", "Kr": 4e-5, "Kdr": 0.02, "Kds": 0.05},
    {"id": 1, "name": "sandstone", "Kr": 1.5e-5, "Kdr": 0.008, "Kds": 0.05},
    {"id": 2, "name": "limestone", "Kr": 8e-6, "Kdr": 0.005, "Kds": 0.05},
    {"id": 3, "name": "crystalline_basement", "Kr": 3e-6, "Kdr": 0.002, "Kds": 0.05},
    {"id": 4, "name": "intrusive_granite", "Kr": 2e-6, "Kdr": 0.001, "Kds": 0.05},
]


@dataclass(frozen=True)
class Config:
    nx: int = 1024
    ny: int = 1024
    dx: float = 100.0
    depth: float = 6000.0
    dz: float = 50.0
    seed: int = 21
    duration: float = 50000.0
    dt: float = 1000.0
    preset: str = "mosaic"
    target_land_fraction: float = 0.62
    ocean_buffer_fraction: float = 0.035
    uplift_scale: float = 1.0
    initial_relief_scale: float = 1.0
    erodibility_scale: float = 1.0
    diffusion_scale: float = 1.0
    lithology_seed_offset: int = 0

    def __post_init__(self):
        for name in ("nx", "ny", "seed", "lithology_seed_offset"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if min(self.nx, self.ny) < 3 or self.nx * self.ny > 4096**2:
            raise ValueError("grid must be at least 3x3 and at most 4096**2 nodes")
        if self.seed < 0:
            raise ValueError("seed must be nonnegative")
        for name in ("dx", "depth", "dz", "duration", "dt", "uplift_scale",
                     "initial_relief_scale", "erodibility_scale", "diffusion_scale"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if self.preset not in PRESETS:
            raise ValueError(f"unknown preset: {self.preset}")
        if (not math.isfinite(self.target_land_fraction) or
                not 0.5 <= self.target_land_fraction <= 0.75):
            raise ValueError("target_land_fraction must be between 0.5 and 0.75")
        if (not math.isfinite(self.ocean_buffer_fraction) or
                not 0 < self.ocean_buffer_fraction < 0.2):
            raise ValueError("ocean_buffer_fraction must be between 0 and 0.2")
        if self.uplift_scale > 10:
            raise ValueError("uplift_scale must be at most 10")
        if self.initial_relief_scale > 10:
            raise ValueError("initial_relief_scale must be at most 10")
        if self.erodibility_scale > 4:
            raise ValueError("erodibility_scale must be at most 4")
        if self.diffusion_scale > 20:
            raise ValueError("diffusion_scale must be at most 20")
        if self.lithology_seed_offset < 0:
            raise ValueError("lithology_seed_offset must be nonnegative")
        if not math.isclose(self.depth / self.dz, round(self.depth / self.dz)):
            raise ValueError("depth must be an integer multiple of dz")
        if self.nz < 2:
            raise ValueError("at least two depth intervals required")

    @property
    def nz(self):
        return round(self.depth / self.dz) + 1

    @property
    def shape(self):
        return self.ny, self.nx

    @property
    def length(self):
        return (self.ny - 1) * self.dx, (self.nx - 1) * self.dx

    @property
    def ocean_buffer_cells(self):
        return max(1, int(math.ceil(min(self.nx, self.ny) * self.ocean_buffer_fraction)))

    def to_dict(self):
        return asdict(self)
