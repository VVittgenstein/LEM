"""Plugin registry with auto-discovery for loaders, channel providers, and views."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lem_viewer.channels.base import ChannelProvider
    from lem_viewer.loaders.base import DatasetLoader
    from lem_viewer.views.base import ViewPlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Central registry for terrain viewer plugins.

    Plugins register themselves via decorators. Auto-discovery imports all
    modules in specified packages so that decorated classes self-register.
    """

    def __init__(self) -> None:
        self._loaders: dict[str, type[DatasetLoader]] = {}
        self._channel_providers: dict[str, type[ChannelProvider]] = {}
        self._view_plugins: dict[str, type[ViewPlugin]] = {}

    # ── Registration decorators ──────────────────────────────────────

    def loader(self, name: str | None = None):
        """Decorator to register a DatasetLoader class."""

        def decorator(cls: type[DatasetLoader]) -> type[DatasetLoader]:
            key = name or cls.__name__
            self._loaders[key] = cls
            logger.debug("Registered loader: %s", key)
            return cls

        return decorator

    def channel_provider(self, name: str | None = None):
        """Decorator to register a ChannelProvider class."""

        def decorator(cls: type[ChannelProvider]) -> type[ChannelProvider]:
            key = name or cls.__name__
            self._channel_providers[key] = cls
            logger.debug("Registered channel provider: %s", key)
            return cls

        return decorator

    def view(self, name: str | None = None):
        """Decorator to register a ViewPlugin class."""

        def decorator(cls: type[ViewPlugin]) -> type[ViewPlugin]:
            key = name or cls.__name__
            self._view_plugins[key] = cls
            logger.debug("Registered view plugin: %s", key)
            return cls

        return decorator

    # ── Queries ──────────────────────────────────────────────────────

    def get_loaders(self) -> dict[str, type[DatasetLoader]]:
        return dict(self._loaders)

    def get_channel_providers(self) -> dict[str, type[ChannelProvider]]:
        return dict(self._channel_providers)

    def get_view_plugins(self) -> dict[str, type[ViewPlugin]]:
        return dict(self._view_plugins)

    def get_loader(self, name: str) -> type[DatasetLoader]:
        return self._loaders[name]

    def get_channel_provider(self, name: str) -> type[ChannelProvider]:
        return self._channel_providers[name]

    def get_view_plugin(self, name: str) -> type[ViewPlugin]:
        return self._view_plugins[name]

    # ── Auto-discovery ───────────────────────────────────────────────

    def discover_plugins(self, *package_names: str) -> None:
        """Import all modules in the given packages to trigger registration.

        Each package is expected to be importable (e.g., "lem_viewer.loaders").
        Modules that fail to import (e.g., missing optional deps) are skipped.
        """
        for pkg_name in package_names:
            try:
                package = importlib.import_module(pkg_name)
            except ImportError:
                logger.warning("Could not import package: %s", pkg_name)
                continue

            if not hasattr(package, "__path__"):
                continue

            for _importer, modname, _ispkg in pkgutil.walk_packages(
                package.__path__, prefix=package.__name__ + "."
            ):
                try:
                    importlib.import_module(modname)
                    logger.debug("Discovered module: %s", modname)
                except ImportError as exc:
                    logger.debug(
                        "Skipping %s (missing dependency: %s)", modname, exc
                    )

    def clear(self) -> None:
        """Remove all registered plugins. Useful for testing."""
        self._loaders.clear()
        self._channel_providers.clear()
        self._view_plugins.clear()


# Module-level singleton used by the application and plugin decorators.
registry = PluginRegistry()
