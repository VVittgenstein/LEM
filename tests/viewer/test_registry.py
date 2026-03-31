"""Tests for PluginRegistry: registration, queries, auto-discovery, and clear."""

from __future__ import annotations

from pathlib import Path

import pytest

from lem_viewer.channels.base import ChannelProvider
from lem_viewer.loaders.base import DatasetLoader
from lem_viewer.models import TerrainChannel, TerrainDataset
from lem_viewer.registry import PluginRegistry


# ── Concrete test doubles ────────────────────────────────────────────


class StubLoader(DatasetLoader):
    def can_load(self, path: Path) -> bool:
        return path.suffix == ".stub"

    def load(self, path: Path) -> TerrainDataset:
        return TerrainDataset(
            dataset_id="stub", grid_shape=(4, 4), spacing=(1.0, 1.0)
        )


class StubChannelProvider(ChannelProvider):
    def can_provide(self, dataset: TerrainDataset) -> bool:
        return True

    def provide(self, dataset: TerrainDataset) -> list[TerrainChannel]:
        return []


class StubView:
    """Minimal stand-in for a ViewPlugin (avoids Qt import)."""

    @property
    def display_name(self) -> str:
        return "Stub View"

    def create_widget(self, dataset: TerrainDataset, **kwargs):
        return None


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def reg() -> PluginRegistry:
    """A fresh, isolated registry for each test."""
    return PluginRegistry()


# ── Loader registration ─────────────────────────────────────────────


class TestLoaderRegistration:
    def test_register_and_retrieve(self, reg: PluginRegistry):
        reg.loader("stub")(StubLoader)
        assert reg.get_loader("stub") is StubLoader

    def test_auto_name_from_class(self, reg: PluginRegistry):
        reg.loader()(StubLoader)
        assert reg.get_loader("StubLoader") is StubLoader

    def test_get_loaders_returns_copy(self, reg: PluginRegistry):
        reg.loader("a")(StubLoader)
        loaders = reg.get_loaders()
        loaders["b"] = StubLoader  # mutate the copy
        assert "b" not in reg.get_loaders()

    def test_missing_loader_raises(self, reg: PluginRegistry):
        with pytest.raises(KeyError):
            reg.get_loader("nonexistent")


# ── Channel provider registration ───────────────────────────────────


class TestChannelProviderRegistration:
    def test_register_and_retrieve(self, reg: PluginRegistry):
        reg.channel_provider("slope")(StubChannelProvider)
        assert reg.get_channel_provider("slope") is StubChannelProvider

    def test_auto_name(self, reg: PluginRegistry):
        reg.channel_provider()(StubChannelProvider)
        assert "StubChannelProvider" in reg.get_channel_providers()


# ── View plugin registration ────────────────────────────────────────


class TestViewRegistration:
    def test_register_and_retrieve(self, reg: PluginRegistry):
        reg.view("3d")(StubView)
        assert reg.get_view_plugin("3d") is StubView

    def test_auto_name(self, reg: PluginRegistry):
        reg.view()(StubView)
        assert "StubView" in reg.get_view_plugins()


# ── Clear ────────────────────────────────────────────────────────────


class TestRegistryClear:
    def test_clear_removes_all(self, reg: PluginRegistry):
        reg.loader("l")(StubLoader)
        reg.channel_provider("c")(StubChannelProvider)
        reg.view("v")(StubView)

        reg.clear()

        assert reg.get_loaders() == {}
        assert reg.get_channel_providers() == {}
        assert reg.get_view_plugins() == {}


# ── Auto-discovery ───────────────────────────────────────────────────


class TestDiscovery:
    def test_discover_builtin_packages_does_not_error(self, reg: PluginRegistry):
        """Discovery should import the (currently empty) plugin packages
        without raising, even when no concrete plugins exist yet."""
        reg.discover_plugins(
            "lem_viewer.loaders",
            "lem_viewer.channels",
            "lem_viewer.views",
        )

    def test_discover_nonexistent_package_is_skipped(self, reg: PluginRegistry):
        """Attempting to discover a missing package should not raise."""
        reg.discover_plugins("lem_viewer.nonexistent_subpackage")

    def test_discover_triggers_registration(self, tmp_path: Path):
        """Create a temporary plugin module and verify discovery registers it."""
        # Build a tiny package with a loader that registers itself.
        pkg_dir = tmp_path / "fake_loaders"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "my_loader.py").write_text(
            "from lem_viewer.registry import registry\n"
            "from lem_viewer.loaders.base import DatasetLoader\n"
            "from lem_viewer.models import TerrainDataset\n"
            "from pathlib import Path\n"
            "\n"
            "@registry.loader('fake')\n"
            "class FakeLoader(DatasetLoader):\n"
            "    def can_load(self, path: Path) -> bool:\n"
            "        return False\n"
            "    def load(self, path: Path) -> TerrainDataset:\n"
            "        raise NotImplementedError\n"
        )

        import sys

        # Make the temp package importable.
        sys.path.insert(0, str(tmp_path))
        try:
            fresh_reg = PluginRegistry()
            # Point discovery at the module-level singleton, which the
            # decorator in the temp file targets.
            from lem_viewer.registry import registry as global_reg

            global_reg.clear()
            global_reg.discover_plugins("fake_loaders")

            assert "fake" in global_reg.get_loaders()
        finally:
            sys.path.remove(str(tmp_path))
            # Clean up imported modules.
            for mod_name in list(sys.modules):
                if mod_name.startswith("fake_loaders"):
                    del sys.modules[mod_name]
            global_reg.clear()


# ── Decorator preserves class identity ───────────────────────────────


class TestDecoratorIdentity:
    def test_decorator_returns_same_class(self, reg: PluginRegistry):
        result = reg.loader("identity_test")(StubLoader)
        assert result is StubLoader
