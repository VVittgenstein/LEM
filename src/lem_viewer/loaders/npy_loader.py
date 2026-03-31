"""Loader for .npy files: single-file and directory-based datasets."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from lem_viewer.loaders.base import DatasetLoader
from lem_viewer.models import TerrainChannel, TerrainDataset
from lem_viewer.registry import registry

logger = logging.getLogger(__name__)


@registry.loader("npy")
class NpyLoader(DatasetLoader):
    """Load terrain data from .npy files.

    Supports two modes:
    - Single file: produces a one-channel dataset (channel name from filename stem).
    - Directory: loads all .npy files as channels; all must share the same 2D shape.
    """

    def can_load(self, path: Path) -> bool:
        path = Path(path)
        if path.is_file() and path.suffix == ".npy":
            return True
        if path.is_dir():
            return any(path.glob("*.npy"))
        return False

    def load(self, path: Path) -> TerrainDataset:
        path = Path(path)
        if path.is_file():
            return self._load_single(path)
        if path.is_dir():
            return self._load_directory(path)
        raise FileNotFoundError(f"Path does not exist: {path}")

    # ── Private helpers ─────────────────────────────────────────────

    def _load_single(self, file_path: Path) -> TerrainDataset:
        array = np.load(file_path)
        array = _validate_2d(array, file_path)
        name = file_path.stem
        channel = TerrainChannel(name=name, array=array)
        channel.compute_stats()
        return TerrainDataset(
            dataset_id=file_path.stem,
            grid_shape=array.shape,
            channels={name: channel},
            metadata={"source_path": str(file_path), "format": "npy"},
        )

    def _load_directory(self, dir_path: Path) -> TerrainDataset:
        npy_files = sorted(dir_path.glob("*.npy"))
        if not npy_files:
            raise ValueError(f"No .npy files found in directory: {dir_path}")

        channels: dict[str, TerrainChannel] = {}
        reference_shape: tuple[int, int] | None = None

        for fp in npy_files:
            array = np.load(fp)
            array = _validate_2d(array, fp)

            if reference_shape is None:
                reference_shape = array.shape
            elif array.shape != reference_shape:
                raise ValueError(
                    f"Shape mismatch: {fp.name} has shape {array.shape}, "
                    f"expected {reference_shape} (from {npy_files[0].name})"
                )

            name = fp.stem
            channel = TerrainChannel(name=name, array=array)
            channel.compute_stats()
            channels[name] = channel

        assert reference_shape is not None  # guaranteed by non-empty npy_files
        return TerrainDataset(
            dataset_id=dir_path.name,
            grid_shape=reference_shape,
            channels=channels,
            metadata={"source_path": str(dir_path), "format": "npy"},
        )


def _validate_2d(array: np.ndarray, source: Path) -> np.ndarray:
    """Ensure the array is 2-D. Squeeze length-1 leading dims if possible."""
    if array.ndim == 2:
        return array
    squeezed = array.squeeze()
    if squeezed.ndim == 2:
        logger.debug("Squeezed %s from shape %s to %s", source.name, array.shape, squeezed.shape)
        return squeezed
    raise ValueError(
        f"Expected a 2-D array from {source.name}, got shape {array.shape}"
    )
