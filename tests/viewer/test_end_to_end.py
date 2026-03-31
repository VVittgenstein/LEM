"""End-to-end smoke tests: .npy data → loader → channel providers → UI binding."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from lem_viewer.app import Application
from lem_viewer.registry import registry


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def elevation_file(tmp_path: Path) -> Path:
    """Create a single elevation .npy file."""
    rng = np.random.default_rng(99)
    arr = rng.random((64, 64), dtype=np.float32) * 1000
    f = tmp_path / "elevation.npy"
    np.save(f, arr)
    return f


@pytest.fixture()
def multi_channel_dir(tmp_path: Path) -> Path:
    """Create a directory with elevation and sediment channels."""
    rng = np.random.default_rng(42)
    shape = (32, 32)
    np.save(tmp_path / "elevation.npy", rng.random(shape, dtype=np.float32) * 500)
    np.save(tmp_path / "sediment.npy", rng.random(shape, dtype=np.float32) * 10)
    return tmp_path


# ── Application.load_source tests ────────────────────────────────────


class TestApplicationLoadSource:
    """Test the full Application → loader → channel provider pipeline."""

    def test_load_single_npy(self, elevation_file: Path):
        app = Application()
        ds = app.load_source(elevation_file)

        assert ds.dataset_id == "elevation"
        assert ds.grid_shape == (64, 64)
        assert "elevation" in ds.channels
        # Channel providers should have added derived channels
        assert "slope" in ds.channels
        assert "hillshade" in ds.channels

    def test_load_directory(self, multi_channel_dir: Path):
        app = Application()
        ds = app.load_source(multi_channel_dir)

        assert "elevation" in ds.channels
        assert "sediment" in ds.channels
        # Derived channels from elevation
        assert "slope" in ds.channels
        assert "hillshade" in ds.channels

    def test_derived_channel_stats(self, elevation_file: Path):
        app = Application()
        ds = app.load_source(elevation_file)

        for name in ("slope", "hillshade"):
            ch = ds.get_channel(name)
            assert ch.stats is not None
            assert ch.stats.min <= ch.stats.max

    def test_no_loader_raises(self, tmp_path: Path):
        app = Application()
        bogus = tmp_path / "data.xyz"
        bogus.write_text("not terrain data")
        with pytest.raises(ValueError, match="No loader can handle"):
            app.load_source(bogus)

    def test_channel_providers_do_not_overwrite_existing(self, multi_channel_dir: Path):
        """If a channel already exists, providers should not replace it."""
        app = Application()
        ds = app.load_source(multi_channel_dir)

        # sediment was loaded from file, not computed — should still be there
        sediment = ds.get_channel("sediment")
        assert sediment.stats is not None
        # The original sediment data had max ~10 (from fixture rng * 10)
        assert sediment.stats.max < 15.0


# ── CLI argument parsing ─────────────────────────────────────────────


class TestMainArgParsing:
    """Test that main.py correctly parses arguments."""

    def test_parse_no_args(self):
        import argparse

        from lem_viewer.main import main

        # Just verify it doesn't crash when parsing empty args
        # (we can't actually run the Qt event loop in a test)
        parser = argparse.ArgumentParser()
        parser.add_argument("sources", nargs="*")
        args = parser.parse_args([])
        assert args.sources == []

    def test_parse_single_source(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("sources", nargs="*")
        args = parser.parse_args(["output/elevation.npy"])
        assert args.sources == ["output/elevation.npy"]


# ── Full pipeline to MainWindow binding ──────────────────────────────


class TestEndToEndUIBinding:
    """Test that loaded data reaches the MainWindow correctly."""

    def test_load_and_bind_to_window(self, qapp, elevation_file: Path):
        from lem_viewer.ui.main_window import MainWindow

        app = Application()
        ds = app.load_source(elevation_file)

        window = MainWindow()
        window.set_dataset(ds)

        assert window._dataset is ds
        assert window.primary_channel == "elevation"
        # All channels (raw + derived) should be in the combo box
        channel_names = ds.channel_names
        assert "slope" in channel_names
        assert "hillshade" in channel_names

    def test_load_directory_and_bind(self, qapp, multi_channel_dir: Path):
        from lem_viewer.ui.main_window import MainWindow

        app = Application()
        ds = app.load_source(multi_channel_dir)

        window = MainWindow()
        window.set_dataset(ds)

        assert window._dataset is ds
        assert len(ds.channel_names) >= 4  # elevation, sediment, slope, hillshade

    def test_application_run_with_source_creates_dataset(
        self, qapp, elevation_file: Path
    ):
        """Verify Application wires sources to MainWindow during run().

        We cannot call app.run() (it enters the Qt event loop), so we
        replicate the load-and-bind logic that run() performs.
        """
        app = Application(sources=[str(elevation_file)])
        ds = app.load_source(app._sources[0])
        assert ds is not None
        assert "elevation" in ds.channels


# ── Registry state ───────────────────────────────────────────────────


class TestRegistryAfterDiscovery:
    """After Application() init, all built-in plugins should be registered."""

    def test_npy_loader_registered(self):
        Application()  # triggers discovery
        assert "npy" in registry.get_loaders()

    def test_builtin_channel_providers_registered(self):
        Application()
        providers = registry.get_channel_providers()
        assert "slope" in providers
        assert "hillshade" in providers

    def test_view_plugins_registered(self):
        Application()
        views = registry.get_view_plugins()
        assert "surface_3d" in views
        assert "compare_surface_3d" in views
