"""Application entry point — wires registry discovery and launches the UI."""

from __future__ import annotations

import logging
from pathlib import Path

from lem_viewer.models import TerrainDataset
from lem_viewer.registry import registry

logger = logging.getLogger(__name__)


class Application:
    """Top-level application object.

    Discovers plugins, resolves data sources through the loader registry,
    applies channel providers, and launches the PySide6 event loop.
    """

    def __init__(
        self,
        *,
        sources: list[str | Path] | None = None,
        skip_discovery: bool = False,
    ) -> None:
        self._sources: list[Path] = [Path(s) for s in (sources or [])]
        if not skip_discovery:
            self._discover_plugins()

    def _discover_plugins(self) -> None:
        registry.discover_plugins(
            "lem_viewer.loaders",
            "lem_viewer.channels",
            "lem_viewer.views",
        )

    def load_source(self, path: Path) -> TerrainDataset:
        """Resolve a file/directory through the loader registry and return a dataset."""
        path = Path(path)
        for name, loader_cls in registry.get_loaders().items():
            loader = loader_cls()
            if loader.can_load(path):
                logger.info("Loading %s with %s loader", path, name)
                dataset = loader.load(path)
                self._apply_channel_providers(dataset)
                return dataset
        raise ValueError(
            f"No loader can handle: {path}\n"
            f"Registered loaders: {list(registry.get_loaders().keys())}"
        )

    def _apply_channel_providers(self, dataset: TerrainDataset) -> None:
        """Run all registered channel providers that can contribute to this dataset."""
        for name, provider_cls in registry.get_channel_providers().items():
            provider = provider_cls()
            if provider.can_provide(dataset):
                try:
                    channels = provider.provide(dataset)
                    for ch in channels:
                        if ch.name not in dataset.channels:
                            dataset.add_channel(ch)
                            logger.info("Added derived channel: %s", ch.name)
                except Exception:
                    logger.warning(
                        "Channel provider %s failed", name, exc_info=True
                    )

    def run(self) -> None:
        """Launch the viewer UI."""
        import sys

        from PySide6.QtWidgets import QApplication

        from lem_viewer.ui.main_window import MainWindow

        qt_app = QApplication(sys.argv)
        window = MainWindow()

        # Load the first source if provided via CLI
        if self._sources:
            try:
                dataset = self.load_source(self._sources[0])
                window.set_dataset(dataset)
            except Exception:
                logger.error(
                    "Failed to load %s", self._sources[0], exc_info=True
                )

        window.show()
        qt_app.exec()
