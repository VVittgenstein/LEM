"""Surface-only FLEM v1 export, matching the independent viewer loader."""
import struct
import numpy as np

HEADER = struct.Struct("<4sIII8fIf8s")


def write_flem(path, elevation, drainage_area, erosion_rate, dx, water_level=None):
    arrays = [np.asarray(a, dtype="<f4", order="C") for a in
              (elevation, drainage_area, erosion_rate)]
    h, area, erosion = arrays
    if h.ndim != 2 or min(h.shape) < 2 or h.size > 4096**2:
        raise ValueError("invalid FLEM dimensions")
    if any(a.shape != h.shape or not np.isfinite(a).all() for a in arrays):
        raise ValueError("FLEM fields must have matching shapes and finite float32 values")
    if np.any(area < 0):
        raise ValueError("drainage area cannot be negative")
    ny, nx = h.shape
    lengths = np.asarray([(nx - 1) * dx, (ny - 1) * dx], dtype=np.float32)
    if not np.all(np.isfinite(lengths)) or np.any(lengths <= 0):
        raise ValueError("dx and node spans must be positive finite float32 values")
    water = np.float32(0 if water_level is None else water_level)
    if not np.isfinite(water):
        raise ValueError("water level must be finite")
    header = HEADER.pack(b"FLEM", 1, nx, ny, *lengths,
                         float(h.min()), float(h.max()), float(area.min()), float(area.max()),
                         float(erosion.min()), float(erosion.max()),
                         int(water_level is not None), water, b"\0" * 8)
    with open(path, "xb") as stream:
        stream.write(header)
        for array in arrays:
            stream.write(array.tobytes(order="C"))
