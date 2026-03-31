"""Tests for built-in channel providers: slope and hillshade."""

from __future__ import annotations

import numpy as np
import pytest

from lem_viewer.channels.builtins import HillshadeProvider, SlopeProvider
from lem_viewer.models import TerrainChannel, TerrainDataset


# ── Helpers ──────────────────────────────────────────────────────────


def _make_dataset(
    elev: np.ndarray | None = None,
    spacing: tuple[float, float] = (1.0, 1.0),
    channels: dict[str, TerrainChannel] | None = None,
) -> TerrainDataset:
    if channels is None:
        channels = {}
    if elev is not None:
        ch = TerrainChannel(name="elevation", units="m", array=elev)
        channels["elevation"] = ch
    shape = elev.shape if elev is not None else (4, 4)
    return TerrainDataset(
        dataset_id="test", grid_shape=shape, spacing=spacing, channels=channels
    )


# ── SlopeProvider ────────────────────────────────────────────────────


class TestSlopeProvider:
    @pytest.fixture()
    def provider(self) -> SlopeProvider:
        return SlopeProvider()

    def test_can_provide_with_elevation(self, provider: SlopeProvider):
        ds = _make_dataset(np.zeros((4, 4)))
        assert provider.can_provide(ds) is True

    def test_cannot_provide_without_elevation(self, provider: SlopeProvider):
        ds = _make_dataset(channels={})
        assert provider.can_provide(ds) is False

    def test_flat_surface_zero_slope(self, provider: SlopeProvider):
        ds = _make_dataset(np.ones((8, 8)))
        channels = provider.provide(ds)
        assert len(channels) == 1
        slope_ch = channels[0]
        assert slope_ch.name == "slope"
        assert slope_ch.units == "m/m"
        np.testing.assert_allclose(slope_ch.get_array(), 0.0, atol=1e-12)

    def test_tilted_plane_constant_slope(self, provider: SlopeProvider):
        """A plane tilted 1 m/m in x should produce slope ~1.0 in the interior."""
        rows, cols = 20, 20
        x = np.arange(cols, dtype=float)
        elev = np.tile(x, (rows, 1))  # rises 1.0 per cell in x
        ds = _make_dataset(elev, spacing=(1.0, 1.0))
        channels = provider.provide(ds)
        slope = channels[0].get_array()
        # Interior cells (away from gradient boundary effects) should be ~1.0
        interior = slope[2:-2, 2:-2]
        np.testing.assert_allclose(interior, 1.0, atol=1e-10)

    def test_stats_computed(self, provider: SlopeProvider):
        ds = _make_dataset(np.random.default_rng(42).random((10, 10)))
        channels = provider.provide(ds)
        assert channels[0].stats is not None

    def test_respects_spacing(self, provider: SlopeProvider):
        """Doubling spacing should halve the gradient magnitude."""
        rows, cols = 20, 20
        x = np.arange(cols, dtype=float)
        elev = np.tile(x, (rows, 1))

        ds1 = _make_dataset(elev, spacing=(1.0, 1.0))
        ds2 = _make_dataset(elev, spacing=(1.0, 2.0))  # dx=2 → half gradient in x

        slope1 = provider.provide(ds1)[0].get_array()[5:-5, 5:-5]
        slope2 = provider.provide(ds2)[0].get_array()[5:-5, 5:-5]
        np.testing.assert_allclose(slope2, slope1 / 2.0, atol=1e-10)


# ── HillshadeProvider ───────────────────────────────────────────────


class TestHillshadeProvider:
    @pytest.fixture()
    def provider(self) -> HillshadeProvider:
        return HillshadeProvider()

    def test_can_provide_with_elevation(self, provider: HillshadeProvider):
        ds = _make_dataset(np.zeros((4, 4)))
        assert provider.can_provide(ds) is True

    def test_cannot_provide_without_elevation(self, provider: HillshadeProvider):
        ds = _make_dataset(channels={})
        assert provider.can_provide(ds) is False

    def test_flat_surface_uniform_shade(self, provider: HillshadeProvider):
        ds = _make_dataset(np.ones((8, 8)))
        channels = provider.provide(ds)
        assert len(channels) == 1
        hs = channels[0]
        assert hs.name == "hillshade"
        # Flat surface: all values should be sin(altitude) = sin(45°) ≈ 0.707
        expected = np.sin(np.radians(45.0))
        np.testing.assert_allclose(hs.get_array(), expected, atol=1e-12)

    def test_output_range_0_to_1(self, provider: HillshadeProvider):
        rng = np.random.default_rng(42)
        elev = rng.random((16, 16)) * 100.0
        ds = _make_dataset(elev)
        channels = provider.provide(ds)
        arr = channels[0].get_array()
        assert arr.min() >= 0.0
        assert arr.max() <= 1.0

    def test_stats_computed(self, provider: HillshadeProvider):
        ds = _make_dataset(np.random.default_rng(7).random((10, 10)))
        channels = provider.provide(ds)
        assert channels[0].stats is not None

    def test_display_defaults(self, provider: HillshadeProvider):
        ds = _make_dataset(np.zeros((4, 4)))
        channels = provider.provide(ds)
        dd = channels[0].display_defaults
        assert dd is not None
        assert dd.colormap == "gray"
        assert dd.vmin == 0.0
        assert dd.vmax == 1.0


# ── Registry integration ────────────────────────────────────────────


class TestProviderRegistration:
    def test_slope_registered(self):
        from lem_viewer.registry import registry

        assert "slope" in registry.get_channel_providers()

    def test_hillshade_registered(self):
        from lem_viewer.registry import registry

        assert "hillshade" in registry.get_channel_providers()

    def test_providers_discovered_via_global_registry(self):
        """Verify auto-discovery of the channels package registers providers
        on the global singleton (decorators target registry at import time)."""
        from lem_viewer.registry import registry

        # The builtins module is already imported, so the global registry
        # should already contain the providers. discover_plugins on the
        # channels package should not raise.
        registry.discover_plugins("lem_viewer.channels")
        assert "slope" in registry.get_channel_providers()
        assert "hillshade" in registry.get_channel_providers()


# ── Channel-provider pipeline integration ────────────────────────────


class TestChannelProviderPipeline:
    """Test that providers can enrich a dataset loaded from .npy files."""

    def test_slope_added_to_dataset(self, tmp_path):
        """Load a .npy file, run the slope provider, add result to dataset."""
        from lem_viewer.loaders.npy_loader import NpyLoader

        # Create a tilted plane as elevation
        elev = np.tile(np.arange(10, dtype=float), (10, 1))
        np.save(tmp_path / "elevation.npy", elev)

        loader = NpyLoader()
        ds = loader.load(tmp_path / "elevation.npy")

        provider = SlopeProvider()
        assert provider.can_provide(ds)
        for ch in provider.provide(ds):
            ds.add_channel(ch)

        assert "slope" in ds.channel_names
        assert "elevation" in ds.channel_names

    def test_full_pipeline_with_all_providers(self, tmp_path):
        """Load directory, apply all registered providers."""
        from lem_viewer.loaders.npy_loader import NpyLoader
        from lem_viewer.registry import registry

        np.save(tmp_path / "elevation.npy", np.random.default_rng(0).random((8, 8)))

        ds = NpyLoader().load(tmp_path)
        for _name, prov_cls in registry.get_channel_providers().items():
            prov = prov_cls()
            if prov.can_provide(ds):
                for ch in prov.provide(ds):
                    ds.add_channel(ch)

        assert "elevation" in ds.channel_names
        assert "slope" in ds.channel_names
        assert "hillshade" in ds.channel_names
