"""Stub loader for HDF5 datasets.

The interface is defined so future implementation does not require core-code changes.
Actual loading requires the ``h5py`` optional dependency.
"""

from __future__ import annotations

from pathlib import Path

from lem_viewer.loaders.base import DatasetLoader
from lem_viewer.models import TerrainDataset

try:
    import h5py as _h5py  # noqa: F401

    _HAS_H5PY = True
except ImportError:
    _HAS_H5PY = False


class Hdf5Loader(DatasetLoader):
    """Placeholder HDF5 loader — registered only when h5py is available."""

    def can_load(self, path: Path) -> bool:
        if not _HAS_H5PY:
            return False
        path = Path(path)
        return path.is_file() and path.suffix in (".h5", ".hdf5")

    def load(self, path: Path) -> TerrainDataset:
        raise NotImplementedError(
            "HDF5 loading is not yet implemented. Install h5py and check back later."
        )


# Only register when the dependency is present so the registry stays clean.
if _HAS_H5PY:
    from lem_viewer.registry import registry

    registry.loader("hdf5")(Hdf5Loader)
