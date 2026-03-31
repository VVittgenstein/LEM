"""Tests for core data models: TerrainChannel, TerrainDataset, ChannelStats."""

from __future__ import annotations

import numpy as np
import pytest

from lem_viewer.models import (
    ChannelStats,
    DisplayDefaults,
    TerrainChannel,
    TerrainDataset,
)


# ── ChannelStats ─────────────────────────────────────────────────────


class TestChannelStats:
    def test_from_array(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0])
        stats = ChannelStats.from_array(arr)
        assert stats.min == pytest.approx(1.0)
        assert stats.max == pytest.approx(4.0)
        assert stats.mean == pytest.approx(2.5)
        assert stats.std == pytest.approx(np.std(arr))

    def test_from_array_with_nan(self):
        arr = np.array([1.0, float("nan"), 3.0])
        stats = ChannelStats.from_array(arr)
        assert stats.min == pytest.approx(1.0)
        assert stats.max == pytest.approx(3.0)


# ── TerrainChannel ───────────────────────────────────────────────────


class TestTerrainChannel:
    def test_eager_array(self):
        arr = np.zeros((4, 4))
        ch = TerrainChannel(name="elevation", units="m", array=arr)
        assert ch.is_loaded
        np.testing.assert_array_equal(ch.get_array(), arr)

    def test_lazy_load(self):
        arr = np.ones((2, 2))
        ch = TerrainChannel(name="lazy", lazy_loader=lambda: arr)
        assert not ch.is_loaded
        np.testing.assert_array_equal(ch.get_array(), arr)
        assert ch.is_loaded  # now cached

    def test_no_data_raises(self):
        ch = TerrainChannel(name="empty")
        with pytest.raises(ValueError, match="no data"):
            ch.get_array()

    def test_compute_stats(self):
        arr = np.arange(9.0).reshape(3, 3)
        ch = TerrainChannel(name="test", array=arr)
        stats = ch.compute_stats()
        assert stats.min == pytest.approx(0.0)
        assert stats.max == pytest.approx(8.0)
        assert ch.stats is stats  # cached on the channel

    def test_default_display_defaults(self):
        ch = TerrainChannel(name="x")
        assert ch.display_defaults is not None
        assert ch.display_defaults.colormap == "terrain"


# ── TerrainDataset ───────────────────────────────────────────────────


class TestTerrainDataset:
    def test_create_empty(self):
        ds = TerrainDataset(dataset_id="test", grid_shape=(64, 64))
        assert ds.dataset_id == "test"
        assert ds.grid_shape == (64, 64)
        assert ds.spacing == (1.0, 1.0)
        assert ds.channels == {}
        assert ds.channel_names == []

    def test_add_and_get_channel(self):
        ds = TerrainDataset(dataset_id="t", grid_shape=(4, 4))
        ch = TerrainChannel(name="elev", units="m", array=np.zeros((4, 4)))
        ds.add_channel(ch)
        assert ds.channel_names == ["elev"]
        assert ds.get_channel("elev") is ch

    def test_get_missing_channel_raises(self):
        ds = TerrainDataset(dataset_id="t", grid_shape=(4, 4))
        with pytest.raises(KeyError, match="not found"):
            ds.get_channel("nope")

    def test_metadata(self):
        ds = TerrainDataset(
            dataset_id="t",
            grid_shape=(4, 4),
            metadata={"source": "landlab", "uplift_rate": 0.001},
        )
        assert ds.metadata["source"] == "landlab"

    def test_add_channel_overwrites(self):
        ds = TerrainDataset(dataset_id="t", grid_shape=(4, 4))
        ch1 = TerrainChannel(name="elev", units="m", array=np.zeros((4, 4)))
        ch2 = TerrainChannel(name="elev", units="m", array=np.ones((4, 4)))
        ds.add_channel(ch1)
        ds.add_channel(ch2)
        assert ds.get_channel("elev") is ch2


# ── DisplayDefaults ──────────────────────────────────────────────────


class TestDisplayDefaults:
    def test_defaults(self):
        dd = DisplayDefaults()
        assert dd.colormap == "terrain"
        assert dd.vmin is None
        assert dd.vmax is None

    def test_custom(self):
        dd = DisplayDefaults(colormap="viridis", vmin=0.0, vmax=100.0)
        assert dd.colormap == "viridis"
        assert dd.vmin == 0.0
