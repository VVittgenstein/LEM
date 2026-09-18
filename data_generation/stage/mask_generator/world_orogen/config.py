"""Versioned engineering settings for the first planar experiment."""
from dataclasses import asdict, dataclass
from pathlib import Path

UPSTREAM_COMMIT = "cc2662b4edd52231c4f65d8765f3ef12cd82d9b7"
VERSION = "world-orogen-planar-1.0.0"
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file() and (p / 'AGENTS.md').is_file())
DEFAULT_OUTPUT = ROOT / "output/mask_generator/world_orogen"
DISPLAY_SEEDS = tuple(range(1001, 1007))
COUNTS = (14, 28, 56)


@dataclass(frozen=True)
class Settings:
    size: int = 500
    band: int = 10
    cell_km: float = 1.0
    coarse_side: int = 96
    point_jitter: float = .75
    partition_count: int = 28
    warp_multiplier: float = .5
    center_weight: float = 24.0
    connection_weight: float = 8.0
    center_x_km: float = 250.0
    center_y_km: float = 250.0

    def validate(self):
        import math
        if self.size != 500 or self.band != 10 or self.cell_km != 1:
            raise ValueError("this experiment uses 500x500, 1 km cells and a 10-cell ocean band")
        if not 8 <= self.coarse_side <= 160:
            raise ValueError("coarse_side must be between 8 and 160")
        if not 2 <= self.partition_count <= min(120, self.coarse_side**2):
            raise ValueError("partition_count must be between 2 and 120")
        if not 0 <= self.point_jitter < 1 or not 0 <= self.warp_multiplier <= 2:
            raise ValueError("invalid point jitter or warp multiplier")
        for number in (self.center_weight, self.connection_weight):
            if not math.isfinite(number) or number < 0:
                raise ValueError("selection weights must be finite and nonnegative")
        for coordinate in (self.center_x_km, self.center_y_km):
            if not self.band <= coordinate < self.size-self.band:
                raise ValueError("preferred center must be in the allowed region")
        return self

    def describe(self):
        return {**asdict(self), "version": VERSION, "upstream_commit": UPSTREAM_COMMIT,
                "settings_status": "explicit first-experiment values; not calibrated or user-accepted final values",
                "center_policy": "fixed geometric center in this experiment; no map-type mixture or offset quota"}


def run_settings(settings,counts):
    result=settings.describe()
    result.pop('partition_count')
    result['partition_counts']=list(counts)
    return result
