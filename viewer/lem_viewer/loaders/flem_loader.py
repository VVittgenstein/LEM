"""Read J31415's FLEM v1 surface arrays into the shared viewer dataset."""
from pathlib import Path
import math
import struct
import numpy as np
from lem_viewer.loaders.base import DatasetLoader
from lem_viewer.models import TerrainChannel, TerrainDataset
from lem_viewer.registry import registry

HEADER = struct.Struct("<4sIII8fIf8s")

@registry.loader("flem")
class FlemLoader(DatasetLoader):
    def can_load(self, path: Path) -> bool:
        return Path(path).is_file() and Path(path).suffix.lower() == ".flem"

    def load(self, path: Path) -> TerrainDataset:
        path = Path(path)
        with path.open("rb") as stream:
            header = stream.read(HEADER.size)
            if len(header) != HEADER.size:
                raise ValueError("Truncated FLEM header")
            magic, version, nx, ny, lx, ly, hmin, hmax, amin, amax, emin, emax, has_water, water, _ = HEADER.unpack(header)
            if magic != b"FLEM" or version != 1 or min(nx, ny) < 2 or nx * ny > 4096**2:
                raise ValueError("Invalid FLEM format, version or dimensions")
            if path.stat().st_size != HEADER.size + nx * ny * 12:
                raise ValueError("FLEM array length does not match the header")
            if not all(math.isfinite(v) for v in (lx, ly, hmin, hmax, amin, amax, emin, emax, water)) or min(lx, ly) <= 0 or has_water not in (0, 1):
                raise ValueError("Invalid FLEM scale or water level")
            arrays = np.frombuffer(stream.read(), dtype="<f4").reshape(3, ny, nx).copy()
        if not np.isfinite(arrays).all() or (arrays[1] < 0).any():
            raise ValueError("FLEM contains invalid values")
        ds = TerrainDataset(path.stem, (ny, nx), (ly / (ny - 1), lx / (nx - 1)), metadata={
            "format": "flem", "source_path": str(path), "semantics": "meta",
            "meta": {"has_water": bool(has_water), "water_level_m": float(water)},
        })
        for name, array, units, kind, transform in zip(
            ("elevation", "drainage_area", "erosion_rate"), arrays,
            ("m", "m2", ""), ("elevation", "drainage_area", "generic"), ("linear", "log10", "linear")
        ):
            # FLEM v1 does not declare an erosion-rate time unit.
            ch = TerrainChannel(name, units=units, array=array, kind=kind, transform=transform)
            ch.compute_stats(); ds.add_channel(ch)
        return ds
