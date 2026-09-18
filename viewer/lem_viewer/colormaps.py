"""Banded (discrete) colour scales with legend edges, in the style of FEM post-processors.

No plotting library is required: palettes are control points interpolated in RGB, then sampled into
``levels`` equal bands between the display-space minimum and maximum.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Control points (0..1 position, RGB 0..255). "fem": blue at the low end, red at the high end.
PALETTES: dict[str, list[tuple[float, tuple[int, int, int]]]] = {
    "fem": [
        (0.00, (0, 0, 143)), (0.11, (0, 51, 255)), (0.22, (0, 153, 255)), (0.33, (0, 221, 255)),
        (0.44, (0, 255, 128)), (0.55, (128, 255, 0)), (0.66, (255, 255, 0)), (0.77, (255, 187, 0)),
        (0.88, (255, 96, 0)), (1.00, (204, 0, 0)),
    ],
    # Sequential single hue (light -> dark blue), steps from the reference palette.
    "blue": [
        (0.00, (205, 226, 251)), (0.25, (134, 182, 239)), (0.50, (57, 135, 229)),
        (0.75, (28, 92, 171)), (1.00, (13, 54, 107)),
    ],
    # Terrain-like ramp for elevation: green lowlands -> brown -> white peaks.
    "terrain": [
        (0.00, (40, 100, 60)), (0.30, (120, 170, 80)), (0.55, (200, 190, 120)),
        (0.80, (140, 100, 70)), (1.00, (245, 245, 245)),
    ],
}

DEFAULT_PALETTE = "fem"
DEFAULT_LEVELS = 12


def _interp(palette: str, t: np.ndarray) -> np.ndarray:
    pts = PALETTES[palette]
    pos = np.array([p for p, _ in pts])
    rgb = np.array([c for _, c in pts], dtype=float)
    out = np.empty((t.size, 3))
    for k in range(3):
        out[:, k] = np.interp(t, pos, rgb[:, k])
    return out


def banded_colors(palette: str = DEFAULT_PALETTE, levels: int = DEFAULT_LEVELS) -> np.ndarray:
    """RGBA (levels, 4) uint8 array, one colour per band, sampled at band centres."""
    levels = max(2, int(levels))
    centres = (np.arange(levels) + 0.5) / levels
    rgb = _interp(palette, centres)
    rgba = np.concatenate([rgb, np.full((levels, 1), 255.0)], axis=1)
    return np.clip(np.round(rgba), 0, 255).astype(np.uint8)


@dataclass
class BandedScale:
    """A discrete colour scale over display-space values [vmin, vmax]."""

    vmin: float
    vmax: float
    levels: int = DEFAULT_LEVELS
    palette: str = DEFAULT_PALETTE

    @classmethod
    def from_array(cls, display_values: np.ndarray, levels: int = DEFAULT_LEVELS,
                   palette: str = DEFAULT_PALETTE) -> "BandedScale":
        finite = display_values[np.isfinite(display_values)]
        if finite.size == 0:
            return cls(0.0, 1.0, levels, palette)
        vmin, vmax = float(finite.min()), float(finite.max())
        if vmax <= vmin:
            vmax = vmin + 1.0
        return cls(vmin, vmax, levels, palette)

    @property
    def edges(self) -> np.ndarray:
        """levels + 1 band edges in display space."""
        return np.linspace(self.vmin, self.vmax, self.levels + 1)

    @property
    def colors(self) -> np.ndarray:
        return banded_colors(self.palette, self.levels)

    def band_index(self, display_values: np.ndarray) -> np.ndarray:
        """Band index (0..levels-1) per value; NaN maps to -1."""
        finite = np.isfinite(display_values)
        t = np.where(finite, (display_values - self.vmin) / (self.vmax - self.vmin), 0.0)
        idx = np.floor(t * self.levels).astype(int)
        idx = np.clip(idx, 0, self.levels - 1)
        idx[~finite] = -1
        return idx

    def rgba(self, display_values: np.ndarray) -> np.ndarray:
        """RGBA uint8 array with shape display_values.shape + (4,); NaN -> transparent grey."""
        idx = self.band_index(display_values)
        table = np.vstack([self.colors, np.array([[128, 128, 128, 0]], dtype=np.uint8)])
        idx = np.where(idx < 0, self.levels, idx)
        return table[idx]

    def lookup_table(self) -> np.ndarray:
        """256-entry RGBA table for pyqtgraph ImageItem.setLookupTable (values scaled to [vmin, vmax])."""
        pos = np.linspace(0.0, 1.0, 256, endpoint=False)
        idx = np.clip(np.floor(pos * self.levels).astype(int), 0, self.levels - 1)
        return self.colors[idx]


def format_edge(value: float, transform: str, units: str) -> str:
    """Legend label for one band edge, in data units."""
    if transform == "log10":
        data = 10.0 ** value
        return f"{data:.3g} {units}".strip()
    if abs(value) >= 1e4 or (abs(value) < 1e-2 and value != 0):
        return f"{value:.3e} {units}".strip()
    return f"{value:.1f} {units}".strip()
