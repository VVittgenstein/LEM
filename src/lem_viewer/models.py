"""Core data models for the terrain viewer."""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

import numpy as np


@dataclasses.dataclass
class ChannelStats:
    """Precomputed statistics for a terrain channel."""

    min: float
    max: float
    mean: float
    std: float

    @classmethod
    def from_array(cls, array: np.ndarray) -> ChannelStats:
        return cls(
            min=float(np.nanmin(array)),
            max=float(np.nanmax(array)),
            mean=float(np.nanmean(array)),
            std=float(np.nanstd(array)),
        )


@dataclasses.dataclass
class DisplayDefaults:
    """Default display settings for a channel."""

    colormap: str = "terrain"
    vmin: float | None = None
    vmax: float | None = None


@dataclasses.dataclass
class TerrainChannel:
    """A single data channel (raw or derived) in a terrain dataset.

    Supports both eager (array) and lazy (lazy_loader) data access.
    """

    name: str
    units: str = ""
    array: np.ndarray | None = dataclasses.field(default=None, repr=False)
    lazy_loader: Callable[[], np.ndarray] | None = dataclasses.field(
        default=None, repr=False
    )
    stats: ChannelStats | None = None
    display_defaults: DisplayDefaults | None = dataclasses.field(
        default_factory=DisplayDefaults
    )

    def get_array(self) -> np.ndarray:
        """Return the channel's array, triggering lazy load if needed."""
        if self.array is None and self.lazy_loader is not None:
            self.array = self.lazy_loader()
        if self.array is None:
            raise ValueError(f"Channel '{self.name}' has no data loaded")
        return self.array

    @property
    def is_loaded(self) -> bool:
        return self.array is not None

    def compute_stats(self) -> ChannelStats:
        """Compute and cache stats from the array."""
        self.stats = ChannelStats.from_array(self.get_array())
        return self.stats


@dataclasses.dataclass
class TerrainDataset:
    """A terrain dataset with named channels and metadata."""

    dataset_id: str
    grid_shape: tuple[int, int]
    spacing: tuple[float, float] = (1.0, 1.0)
    channels: dict[str, TerrainChannel] = dataclasses.field(default_factory=dict)
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def add_channel(self, channel: TerrainChannel) -> None:
        self.channels[channel.name] = channel

    def get_channel(self, name: str) -> TerrainChannel:
        if name not in self.channels:
            raise KeyError(
                f"Channel '{name}' not found. "
                f"Available: {list(self.channels.keys())}"
            )
        return self.channels[name]

    @property
    def channel_names(self) -> list[str]:
        return list(self.channels.keys())
