"""Main application window."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMenuBar,
    QWidget,
)

from lem_viewer.models import TerrainDataset
from lem_viewer.ui.control_panel import ControlPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level viewer window with control dock and embeddable 3D view."""

    def __init__(
        self,
        dataset: TerrainDataset | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("LEM Terrain Viewer")
        self.resize(1200, 800)

        self._dataset: TerrainDataset | None = None
        self._current_view: QWidget | None = None

        self._setup_ui()
        self._connect_signals()

        if dataset is not None:
            self.set_dataset(dataset)

    # -- Layout ------------------------------------------------------

    def _setup_ui(self) -> None:
        # Menu bar
        menu_bar = QMenuBar(self)
        file_menu = menu_bar.addMenu("&File")
        open_file_action = file_menu.addAction("Open &File...")
        open_file_action.triggered.connect(self._on_open_file)
        open_dir_action = file_menu.addAction("Open &Directory...")
        open_dir_action.triggered.connect(self._on_open_directory)
        self.setMenuBar(menu_bar)

        # Control dock (left sidebar)
        self._control_panel = ControlPanel()
        dock = QDockWidget("Controls", self)
        dock.setWidget(self._control_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        # Central view area
        container = QWidget()
        self._view_layout = QHBoxLayout(container)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(container)

    def _connect_signals(self) -> None:
        cp = self._control_panel
        cp.channel_changed.connect(self._on_setting_changed)
        cp.compare_toggled.connect(self._on_setting_changed)
        cp.secondary_channel_changed.connect(self._on_setting_changed)
        cp.display_size_changed.connect(self._on_setting_changed)

    # -- Public API --------------------------------------------------

    @property
    def compare_mode(self) -> bool:
        return self._control_panel.compare_mode

    @property
    def primary_channel(self) -> str:
        return self._control_panel.primary_channel

    @property
    def secondary_channel(self) -> str:
        return self._control_panel.secondary_channel

    @property
    def max_display_size(self) -> int:
        return self._control_panel.max_display_size

    def set_dataset(self, dataset: TerrainDataset) -> None:
        """Load a dataset and refresh the view."""
        self._dataset = dataset
        self._control_panel.set_channels(dataset.channel_names)
        self._rebuild_view()

    # -- View management ---------------------------------------------

    def _on_setting_changed(self, *_args: Any) -> None:
        """Slot for any control-panel change that requires a view rebuild."""
        self._rebuild_view()

    def _clear_views(self) -> None:
        while self._view_layout.count():
            item = self._view_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._current_view = None

    def _rebuild_view(self) -> None:
        self._clear_views()
        if self._dataset is None:
            return

        primary = self._control_panel.primary_channel
        if not primary:
            return

        try:
            if self.compare_mode:
                self._build_compare_view(primary)
            else:
                self._build_single_view(primary)
        except Exception:
            logger.warning("Could not create 3D view", exc_info=True)

    def _build_single_view(self, channel_name: str) -> None:
        from lem_viewer.views.surface_3d import Surface3DView

        plugin = Surface3DView()
        widget = plugin.create_widget(
            self._dataset,
            channel_name=channel_name,
            max_display_size=self.max_display_size,
        )
        self._current_view = widget
        self._view_layout.addWidget(widget)

    def _build_compare_view(self, primary: str) -> None:
        from lem_viewer.views.compare_surface_3d import CompareSurface3DView

        secondary = self._control_panel.secondary_channel
        plugin = CompareSurface3DView()
        widget = plugin.create_widget(
            self._dataset,
            primary_channel=primary,
            secondary_channel=secondary or primary,
            max_display_size=self.max_display_size,
        )
        self._current_view = widget
        self._view_layout.addWidget(widget)

    # -- File loading (delegates to Application) ---------------------

    def _on_open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Terrain File", "", "NumPy files (*.npy);;All files (*)"
        )
        if path:
            self._load_via_app(path)

    def _on_open_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Terrain Directory")
        if path:
            self._load_via_app(path)

    def _load_via_app(self, path: str) -> None:
        from lem_viewer.app import Application

        try:
            app = Application(skip_discovery=True)
            dataset = app.load_source(path)
            self.set_dataset(dataset)
            self.setWindowTitle(f"LEM Terrain Viewer — {dataset.dataset_id}")
        except Exception:
            logger.error("Failed to load %s", path, exc_info=True)
