"""Display-only conversion from TerrainDataset to the native renderer's LVT1 input."""
from __future__ import annotations
from dataclasses import dataclass
import math
from pathlib import Path
import struct
import numpy as np
from lem_viewer.colormaps import BandedScale
from lem_viewer.models import TerrainDataset
from lem_viewer.semantics import find_elevation_channel, elevation_in_metres

HEADER = struct.Struct("<4sIIII6d")

@dataclass(frozen=True)
class WaterLevel:
    enabled: bool
    metres: float
    source: str

def water_level(dataset: TerrainDataset, override: float | None = None) -> WaterLevel:
    if override is not None:
        if not math.isfinite(override):
            raise ValueError("Water level must be finite")
        return WaterLevel(True, float(override), "manual")
    meta = dataset.metadata.get("meta", dataset.metadata)
    settings = meta.get("settings", {})
    if meta.get("has_water") is False or meta.get("has_water") == 0:
        return WaterLevel(False, 0.0, "data: no water")
    for obj in (meta, settings):
        for key in ("water_level_m", "sea_level_m", "sea_level_final_m", "water_level"):
            if key in obj and obj[key] is not None:
                value = float(obj[key])
                if not math.isfinite(value):
                    raise ValueError(f"Invalid water level: {key}")
                return WaterLevel(True, value, "data")
    return WaterLevel(True, 0.0, "default")

@dataclass
class DisplayInput:
    elevation: np.ndarray
    drainage: np.ndarray
    erosion: np.ndarray
    colors: np.ndarray
    dx: float
    dy: float
    minimum: float
    maximum: float
    height_levels: int
    exaggeration: float
    material: bool
    water: WaterLevel
    scale: BandedScale
    channel_name: str
    units: str
    transform: str
    spacing_known: bool

    @property
    def layer_metres(self) -> float:
        return (self.maximum - self.minimum) / (self.height_levels - 1)

    def write(self, path: Path) -> None:
        rows, cols = self.elevation.shape
        flags = int(self.water.enabled) | (int(self.material) << 1)
        with path.open("wb") as stream:
            stream.write(HEADER.pack(b"LVT1", cols, rows, self.height_levels, flags,
                                    self.dx, self.dy, self.minimum, self.maximum,
                                    self.water.metres, self.exaggeration))
            for array in (self.elevation, self.drainage, self.erosion):
                stream.write(np.asarray(array, dtype="<f4", order="C").tobytes())
            stream.write(np.asarray(self.colors, dtype=np.uint8, order="C").tobytes())

def prepare_display(dataset: TerrainDataset, channel_name: str, *, max_display_size: int = 512,
                    palette: str = "fem", levels: int = 12, height_levels: int = 36,
                    vertical_exaggeration: float | None = 1.0, material: bool = False,
                    water_override: float | None = None, **_ignored) -> DisplayInput:
    height = find_elevation_channel(dataset)
    if height is None:
        candidate = dataset.get_channel(channel_name)
        if candidate.kind != "drainage_area" and candidate.transform == "linear":
            height = candidate
        else:
            raise ValueError("3D Voxel needs an elevation channel. Open the full dataset containing elevation.")
    raw = elevation_in_metres(height)
    if raw.ndim != 2 or raw.shape != dataset.grid_shape:
        raise ValueError("Elevation shape differs from the dataset grid")
    finite = raw[np.isfinite(raw)]
    if not finite.size:
        raise ValueError("Elevation has no finite values")
    height_levels = int(height_levels)
    if not 2 <= height_levels <= 4096 or max_display_size < 1:
        raise ValueError("Height levels must be 2..4096 and display size positive")
    stride = max(1, math.ceil(max(raw.shape) / max_display_size))
    elevation = raw[::stride, ::stride]
    dy, dx = (float(s) * stride for s in dataset.spacing)
    if not (math.isfinite(dx) and math.isfinite(dy) and dx > 0 and dy > 0):
        raise ValueError("Grid spacing must be positive and finite")
    minimum, maximum = float(finite.min()), float(finite.max())
    if vertical_exaggeration is None or vertical_exaggeration == 0:
        from lem_viewer.views.surface_3d import auto_vertical_exaggeration
        vertical_exaggeration = auto_vertical_exaggeration(max((elevation.shape[1]-1)*dx, (elevation.shape[0]-1)*dy), maximum-minimum)
    if not math.isfinite(vertical_exaggeration) or vertical_exaggeration <= 0:
        raise ValueError("Vertical exaggeration must be positive")
    channel = dataset.get_channel(channel_name)
    values = channel.display_array()[::stride, ::stride]
    if values.shape != elevation.shape:
        raise ValueError("Height and colour shapes differ")
    scale = BandedScale.from_array(values, levels=levels, palette=palette)
    def optional(name: str) -> np.ndarray:
        if name in dataset.channels:
            arr = np.asarray(dataset.get_channel(name).get_array(), dtype=float)[::stride, ::stride]
            if arr.shape != elevation.shape:
                raise ValueError(f"Invalid {name} shape")
            return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        # Only the legacy material-colour calculation uses these zeros. They
        # are never registered as data channels or exported simulation results.
        return np.zeros_like(elevation)
    meta = dataset.metadata.get("meta", {})
    known = "grid" in meta or dataset.metadata.get("format") == "flem"
    return DisplayInput(elevation, optional("drainage_area"), optional("erosion_rate"),
                        scale.rgba(values), dx, dy, minimum, maximum, height_levels,
                        float(vertical_exaggeration), material, water_level(dataset, water_override),
                        scale, channel.name, channel.units, channel.transform, known)
