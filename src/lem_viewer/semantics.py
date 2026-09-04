"""Channel semantics: what a channel represents and how it should be displayed.

A channel *kind* comes from ``meta.json`` (preferred) or is inferred from the file name. Kinds carry
the display transform (drainage area is shown as log10) and the default units.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

# Canonical names written by bench/fs_driver.py exports.
KIND_ELEVATION = "elevation"
KIND_DRAINAGE_AREA = "drainage_area"
KIND_GENERIC = "generic"

_ELEVATION_TOKENS = {"elev", "elevation", "topo", "topography"}
_DRAINAGE_TOKENS = {"da", "drainage", "area", "flowacc"}
_SPLIT = re.compile(r"[_\-.\s]+")


@dataclass(frozen=True)
class KindInfo:
    kind: str
    units: str
    transform: str          # "linear" or "log10"
    label: str


KINDS: dict[str, KindInfo] = {
    KIND_ELEVATION: KindInfo(KIND_ELEVATION, "m", "linear", "Elevation"),
    KIND_DRAINAGE_AREA: KindInfo(KIND_DRAINAGE_AREA, "m2", "log10", "Drainage area"),
    KIND_GENERIC: KindInfo(KIND_GENERIC, "", "linear", "Value"),
}


def infer_kind(name: str) -> str:
    """Infer a channel kind from a channel or file name.

    Tokens are examined from the end, so the trailing suffix wins: ``r1_K1e-05_elev_da_FS_da`` is a
    drainage-area array even though an earlier token names the elevation group.
    """
    for token in reversed(_SPLIT.split(name.lower())):
        if token in _ELEVATION_TOKENS:
            return KIND_ELEVATION
        if token in _DRAINAGE_TOKENS:
            return KIND_DRAINAGE_AREA
    return KIND_GENERIC


def display_array(array: np.ndarray, transform: str) -> np.ndarray:
    """Return the array in display space (log10 for drainage area; non-positive values become NaN)."""
    if transform == "log10":
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log10(np.where(array > 0, array, np.nan))
    return np.asarray(array, dtype=float)


def inverse_display(value: float, transform: str) -> float:
    """Map a display-space value back to data units (10**x for log10)."""
    return float(10.0 ** value) if transform == "log10" else float(value)


def find_elevation_channel(dataset):
    """The channel to use as terrain height, or None.

    A channel literally named ``elevation`` always qualifies. Otherwise a channel whose kind is
    elevation qualifies only when kinds came from ``meta.json`` (``metadata["semantics"] == "meta"``),
    so that name-based guesses never silently change what existing datasets display.
    """
    if "elevation" in dataset.channels:
        return dataset.channels["elevation"]
    if dataset.metadata.get("semantics") == "meta":
        for ch in dataset.channels.values():
            if getattr(ch, "kind", KIND_GENERIC) == KIND_ELEVATION:
                return ch
    return None
