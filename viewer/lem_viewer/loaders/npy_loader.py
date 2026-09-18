"""Loader for .npy files: single-file and directory-based datasets.

Directory datasets may carry a ``meta.json`` (written by ``bench/fs_driver.py``) that declares the
grid spacing and, per channel, the file, units, kind and display transform. Without it, channel names
are the file stems and kinds are inferred from the names.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from lem_viewer.loaders.base import DatasetLoader
from lem_viewer.models import DisplayDefaults, TerrainChannel, TerrainDataset
from lem_viewer.registry import registry
from lem_viewer.semantics import KIND_GENERIC, KINDS, infer_kind

logger = logging.getLogger(__name__)

META_FILE = "meta.json"


@registry.loader("npy")
class NpyLoader(DatasetLoader):
    """Load terrain data from .npy files.

    Supports two modes:
    - Single file: produces a one-channel dataset (channel name from filename stem).
    - Directory: loads all .npy files as channels; all must share the same 2D shape. A ``meta.json``
      in the directory supplies spacing and channel semantics when present.
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
        # A file that belongs to a run directory (declared in a sibling meta.json) is opened as the
        # whole run, so spacing, units and the elevation channel used for height are all available.
        meta = _read_meta(file_path.parent)
        if meta:
            for name, spec in (meta.get("channels") or {}).items():
                if spec.get("file") == file_path.name:
                    dataset = self._load_directory(file_path.parent)
                    dataset.metadata["primary_channel"] = name
                    dataset.metadata["opened_file"] = str(file_path)
                    return dataset
        array = np.load(file_path)
        array = _validate_2d(array, file_path)
        name = file_path.stem
        channel = _make_channel(name, array, infer_kind(name))
        return TerrainDataset(
            dataset_id=file_path.stem,
            grid_shape=array.shape,
            channels={name: channel},
            metadata={"source_path": str(file_path), "format": "npy", "semantics": "inferred"},
        )

    def _load_directory(self, dir_path: Path) -> TerrainDataset:
        npy_files = sorted(dir_path.glob("*.npy"))
        if not npy_files:
            raise ValueError(f"No .npy files found in directory: {dir_path}")

        meta = _read_meta(dir_path)
        declared: dict[str, dict] = (meta or {}).get("channels", {}) if meta else {}
        file_to_decl = {str(spec.get("file", "")): (name, spec) for name, spec in declared.items()}

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

            if fp.name in file_to_decl:
                name, spec = file_to_decl[fp.name]
                kind = spec.get("kind", infer_kind(name))
                transform = "log10" if spec.get("display") == "log10" else KINDS.get(kind, KINDS[KIND_GENERIC]).transform
                channel = _make_channel(name, array, kind, units=spec.get("units"), transform=transform)
            else:
                name = fp.stem
                channel = _make_channel(name, array, infer_kind(name))
            channels[name] = channel

        assert reference_shape is not None  # guaranteed by non-empty npy_files
        metadata = {"source_path": str(dir_path), "format": "npy", "semantics": "meta" if meta else "inferred"}
        spacing = (1.0, 1.0)
        if meta:
            metadata["meta"] = meta
            grid = meta.get("grid", {})
            dx = float(grid.get("dx_m", 1.0))
            dy = float(grid.get("dy_m", dx))
            spacing = (dy, dx)
        return TerrainDataset(
            dataset_id=dir_path.name,
            grid_shape=reference_shape,
            spacing=spacing,
            channels=channels,
            metadata=metadata,
        )


def _make_channel(name: str, array: np.ndarray, kind: str, units: str | None = None,
                  transform: str | None = None) -> TerrainChannel:
    info = KINDS.get(kind, KINDS[KIND_GENERIC])
    channel = TerrainChannel(
        name=name,
        units=units if units is not None else info.units,
        array=array,
        kind=kind,
        transform=transform or info.transform,
        display_defaults=DisplayDefaults(),
    )
    channel.compute_stats()
    return channel


def _read_meta(dir_path: Path) -> dict | None:
    p = dir_path / META_FILE
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring unreadable %s", p, exc_info=True)
        return None


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
