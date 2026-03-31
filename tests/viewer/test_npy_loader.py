"""Tests for NpyLoader: single-file, directory, validation, and edge cases."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lem_viewer.loaders.npy_loader import NpyLoader
from lem_viewer.models import TerrainDataset


@pytest.fixture()
def loader() -> NpyLoader:
    return NpyLoader()


# ── can_load ────────────────────────────────────────────────────────


class TestCanLoad:
    def test_single_npy_file(self, loader: NpyLoader, tmp_path: Path):
        f = tmp_path / "terrain.npy"
        np.save(f, np.zeros((4, 4)))
        assert loader.can_load(f) is True

    def test_directory_with_npy(self, loader: NpyLoader, tmp_path: Path):
        np.save(tmp_path / "elev.npy", np.zeros((4, 4)))
        assert loader.can_load(tmp_path) is True

    def test_empty_directory(self, loader: NpyLoader, tmp_path: Path):
        assert loader.can_load(tmp_path) is False

    def test_non_npy_file(self, loader: NpyLoader, tmp_path: Path):
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2\n")
        assert loader.can_load(f) is False

    def test_nonexistent_path(self, loader: NpyLoader, tmp_path: Path):
        assert loader.can_load(tmp_path / "no_such_file.npy") is False


# ── Single file loading ─────────────────────────────────────────────


class TestLoadSingleFile:
    def test_basic_2d(self, loader: NpyLoader, tmp_path: Path):
        arr = np.arange(16.0).reshape(4, 4)
        f = tmp_path / "elevation.npy"
        np.save(f, arr)

        ds = loader.load(f)
        assert isinstance(ds, TerrainDataset)
        assert ds.dataset_id == "elevation"
        assert ds.grid_shape == (4, 4)
        assert "elevation" in ds.channels
        np.testing.assert_array_equal(ds.get_channel("elevation").get_array(), arr)

    def test_stats_computed(self, loader: NpyLoader, tmp_path: Path):
        arr = np.array([[0.0, 1.0], [2.0, 3.0]])
        f = tmp_path / "height.npy"
        np.save(f, arr)

        ds = loader.load(f)
        stats = ds.get_channel("height").stats
        assert stats is not None
        assert stats.min == pytest.approx(0.0)
        assert stats.max == pytest.approx(3.0)

    def test_metadata_contains_source(self, loader: NpyLoader, tmp_path: Path):
        f = tmp_path / "topo.npy"
        np.save(f, np.zeros((2, 2)))
        ds = loader.load(f)
        assert ds.metadata["format"] == "npy"
        assert "topo.npy" in ds.metadata["source_path"]

    def test_squeezable_3d_array(self, loader: NpyLoader, tmp_path: Path):
        """A (1, 4, 4) array should be squeezed to (4, 4)."""
        arr = np.zeros((1, 4, 4))
        f = tmp_path / "squeezed.npy"
        np.save(f, arr)
        ds = loader.load(f)
        assert ds.grid_shape == (4, 4)

    def test_non_2d_raises(self, loader: NpyLoader, tmp_path: Path):
        arr = np.zeros((2, 3, 4))
        f = tmp_path / "bad.npy"
        np.save(f, arr)
        with pytest.raises(ValueError, match="2-D"):
            loader.load(f)

    def test_1d_raises(self, loader: NpyLoader, tmp_path: Path):
        arr = np.zeros(10)
        f = tmp_path / "flat.npy"
        np.save(f, arr)
        with pytest.raises(ValueError, match="2-D"):
            loader.load(f)


# ── Directory loading ────────────────────────────────────────────────


class TestLoadDirectory:
    def test_multi_channel(self, loader: NpyLoader, tmp_path: Path):
        shape = (8, 8)
        np.save(tmp_path / "elevation.npy", np.ones(shape))
        np.save(tmp_path / "sediment.npy", np.zeros(shape))

        ds = loader.load(tmp_path)
        assert ds.grid_shape == shape
        assert set(ds.channel_names) == {"elevation", "sediment"}

    def test_channel_names_from_filenames(self, loader: NpyLoader, tmp_path: Path):
        np.save(tmp_path / "alpha.npy", np.zeros((3, 3)))
        np.save(tmp_path / "beta.npy", np.zeros((3, 3)))
        np.save(tmp_path / "gamma.npy", np.zeros((3, 3)))

        ds = loader.load(tmp_path)
        assert sorted(ds.channel_names) == ["alpha", "beta", "gamma"]

    def test_shape_mismatch_raises(self, loader: NpyLoader, tmp_path: Path):
        np.save(tmp_path / "a.npy", np.zeros((4, 4)))
        np.save(tmp_path / "b.npy", np.zeros((4, 5)))

        with pytest.raises(ValueError, match="Shape mismatch"):
            loader.load(tmp_path)

    def test_empty_dir_raises(self, loader: NpyLoader, tmp_path: Path):
        with pytest.raises(ValueError, match="No .npy files"):
            loader.load(tmp_path)

    def test_ignores_non_npy_files(self, loader: NpyLoader, tmp_path: Path):
        np.save(tmp_path / "elev.npy", np.zeros((4, 4)))
        (tmp_path / "readme.txt").write_text("notes")

        ds = loader.load(tmp_path)
        assert ds.channel_names == ["elev"]

    def test_dataset_id_from_dirname(self, loader: NpyLoader, tmp_path: Path):
        sub = tmp_path / "my_sim"
        sub.mkdir()
        np.save(sub / "h.npy", np.zeros((2, 2)))

        ds = loader.load(sub)
        assert ds.dataset_id == "my_sim"

    def test_stats_computed_for_all_channels(self, loader: NpyLoader, tmp_path: Path):
        np.save(tmp_path / "a.npy", np.ones((3, 3)))
        np.save(tmp_path / "b.npy", np.full((3, 3), 5.0))

        ds = loader.load(tmp_path)
        for ch_name in ds.channel_names:
            assert ds.get_channel(ch_name).stats is not None


# ── load with nonexistent path ──────────────────────────────────────


class TestLoadErrors:
    def test_nonexistent_path_raises(self, loader: NpyLoader, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            loader.load(tmp_path / "does_not_exist.npy")


# ── Registry integration ────────────────────────────────────────────


class TestNpyRegistration:
    def test_registered_under_npy(self):
        from lem_viewer.registry import registry

        assert "npy" in registry.get_loaders()
        assert registry.get_loader("npy") is NpyLoader
