"""Stub loader for Zarr datasets.

The interface is defined so future implementation does not require core-code changes.
Actual loading requires the ``zarr`` optional dependency.
"""

from __future__ import annotations

from pathlib import Path

from lem_viewer.loaders.base import DatasetLoader
from lem_viewer.models import TerrainDataset

try:
    import zarr as _zarr  # noqa: F401

    _HAS_ZARR = True
except ImportError:
    _HAS_ZARR = False


class ZarrLoader(DatasetLoader):
    """Placeholder Zarr loader — registered only when zarr is available."""

    def can_load(self, path: Path) -> bool:
        if not _HAS_ZARR:
            return False
        path = Path(path)
        return path.is_dir() and (path / ".zarray").exists()

    def load(self, path: Path) -> TerrainDataset:
        raise NotImplementedError(
            "Zarr loading is not yet implemented. Install zarr and check back later."
        )


# Only register when the dependency is present.
if _HAS_ZARR:
    from lem_viewer.registry import registry

    registry.loader("zarr")(ZarrLoader)
