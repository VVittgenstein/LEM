"""Base interface for dataset loaders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from lem_viewer.models import TerrainDataset


class DatasetLoader(ABC):
    """Abstract base class for loading terrain data from files.

    Subclasses handle a specific data format (e.g., .npy, HDF5, Zarr).
    Register with the plugin registry to enable auto-discovery.
    """

    @abstractmethod
    def can_load(self, path: Path) -> bool:
        """Return True if this loader can handle the given path."""
        ...

    @abstractmethod
    def load(self, path: Path) -> TerrainDataset:
        """Load a terrain dataset from the given path."""
        ...
