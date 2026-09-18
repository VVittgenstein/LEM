"""Base interface for channel providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from lem_viewer.models import TerrainChannel, TerrainDataset


class ChannelProvider(ABC):
    """Abstract base class for derived-channel providers.

    A channel provider computes one or more derived channels (e.g., slope,
    hillshade) from an existing TerrainDataset.
    """

    @abstractmethod
    def can_provide(self, dataset: TerrainDataset) -> bool:
        """Return True if this provider can compute channels for the dataset."""
        ...

    @abstractmethod
    def provide(self, dataset: TerrainDataset) -> list[TerrainChannel]:
        """Compute and return derived channels for the dataset."""
        ...
