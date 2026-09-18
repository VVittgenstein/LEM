"""Display settings and downsampling utilities for the terrain viewer."""

from __future__ import annotations

import dataclasses

import numpy as np


@dataclasses.dataclass
class DisplaySettings:
    """Configurable display parameters."""

    max_display_size: int = 512


def downsample_for_display(array: np.ndarray, max_display_size: int) -> np.ndarray:
    """Subsample a 2D array so no dimension exceeds *max_display_size*.

    Uses strided slicing — fast, no copy when the array is already small enough.
    """
    rows, cols = array.shape[:2]
    if max(rows, cols) <= max_display_size:
        return array
    step = int(np.ceil(max(rows, cols) / max_display_size))
    return array[::step, ::step]
