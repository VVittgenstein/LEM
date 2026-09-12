from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'output/mask_generator/world_orogen_gibbs'
VERSION = 'world-orogen-gibbs-2.2.0'
COUNTS = (512,)
DEFAULT_BOUNDARY_LAYERS = 3
SEEDS = tuple(range(1001, 1007))


@dataclass(frozen=True)
class Settings:
    size: int = 500
    cell_km: float = 1.
    band: int = 0
    boundary_layers: int = DEFAULT_BOUNDARY_LAYERS
    partition_count: int = 512
    coarse_side: int = 160
    point_jitter: float = .75
    warp_multiplier: float = .5
    field_sigmas_km: tuple = (15., 45., 120.)
    field_weights: tuple = (.30, .85, .65)
    center_weight: float = 5000.
    spread_weight: float = 1600.
    perimeter_weight: float = 15.
    field_weight: float = 600.
    area_weight: float = 60.
    area_softness: float = .12
    area_low: float = .50
    area_high: float = .60
    temperature: float = 1.

    def validate(self):
        import math
        if (self.size, self.cell_km, self.band) != (500, 1., 0):
            raise ValueError('full 500x500 domain, 1 km cells; no fixed ocean band')
        if isinstance(self.boundary_layers,bool) or not isinstance(self.boundary_layers,int) or self.boundary_layers<1:
            raise ValueError('boundary_layers must be a positive integer')
        if not 2 <= self.partition_count <= 2048 or not 16 <= self.coarse_side <= 200:
            raise ValueError('invalid partition resolution')
        if len(self.field_sigmas_km) != len(self.field_weights):
            raise ValueError('field scales and weights differ')
        if any(not math.isfinite(x) or x <= 0 for x in self.field_sigmas_km):
            raise ValueError('field sigmas must be positive')
        if any(not math.isfinite(x) or x < 0 for x in self.field_weights):
            raise ValueError('invalid field weight')
        if not any(self.field_weights):
            raise ValueError('field cannot be identically zero')
        for name in ('center_weight','spread_weight','perimeter_weight','field_weight','area_weight'):
            if not math.isfinite(getattr(self,name)) or getattr(self,name)<0:
                raise ValueError(name)
        if self.temperature<=0 or self.area_softness<=0 or not 0<self.area_low<=self.area_high<1:
            raise ValueError('invalid area preference or temperature')
        return self

    def describe(self):
        return dict(asdict(self), version=VERSION,
                    parameter_status='512 partitions / 3 boundary layers selected for platform shape; numerical settings documented in SELECTED_PROFILE.md',
                    area_definition='fraction of full 250000 km2 domain',
                    boundary_policy='touching partitions are layer 1; edge-sharing graph neighbors advance one layer; all layers through boundary_layers are forbidden',
                    boundary_reserve_status='geometric reserve only; width in km is measured; downstream evolution has not been validated',
                    center_policy='center initialization only; every eligible bit can change both ways')

    @classmethod
    def from_record(cls,record):
        """Old records have no layer count; their one-layer geometry stays unchanged."""
        values={key:record[key] for key in cls.__dataclass_fields__ if key in record}
        values.setdefault('boundary_layers',1)
        return cls(**values)


def default_output_for(partition_counts=COUNTS,boundary_layers=DEFAULT_BOUNDARY_LAYERS):
    """Name new runs by the full configuration, leaving older comparison folders intact."""
    counts='_'.join(str(n) for n in partition_counts)
    return OUTPUT.parent/f'world_orogen_gibbs_{counts}_layers_{boundary_layers}'
