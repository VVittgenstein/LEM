"""Base interface for view plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from lem_viewer.models import TerrainDataset


class ViewPlugin(ABC):
    """Abstract base class for terrain visualization plugins.

    Each view plugin provides a widget that can be embedded in the main window.
    """

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the view, shown in UI menus."""
        ...

    @abstractmethod
    def create_widget(self, dataset: TerrainDataset, **kwargs: Any) -> Any:
        """Create and return a Qt widget for this view.

        Returns a QWidget (typed as Any to avoid hard PySide6 import in core).
        """
        ...
