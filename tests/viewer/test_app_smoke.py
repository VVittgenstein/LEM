"""Smoke tests for widget creation and compare-state logic."""

from __future__ import annotations

import os

# Ensure offscreen mode is set before any transitive Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from lem_viewer.models import TerrainChannel, TerrainDataset
from lem_viewer.settings import downsample_for_display


# -- helpers -------------------------------------------------------


def _make_dataset(rows: int = 64, cols: int = 64) -> TerrainDataset:
    rng = np.random.default_rng(42)
    arr = rng.random((rows, cols), dtype=np.float32)
    ds = TerrainDataset(dataset_id="test", grid_shape=(rows, cols))
    ds.add_channel(TerrainChannel(name="elevation", units="m", array=arr))
    ds.add_channel(
        TerrainChannel(
            name="slope", units="deg", array=np.gradient(arr, axis=0)
        )
    )
    return ds


# -- downsampling (pure numpy, always runs) ------------------------


class TestDownsampling:
    def test_passthrough_when_small(self):
        arr = np.zeros((100, 100))
        result = downsample_for_display(arr, 512)
        assert result.shape == (100, 100)
        assert result is arr  # no copy

    def test_reduces_large_square(self):
        arr = np.zeros((2048, 2048))
        result = downsample_for_display(arr, 512)
        assert max(result.shape) <= 512

    def test_reduces_large_rect(self):
        arr = np.zeros((1024, 512))
        result = downsample_for_display(arr, 256)
        assert max(result.shape) <= 256

    def test_exact_boundary(self):
        arr = np.zeros((512, 512))
        result = downsample_for_display(arr, 512)
        assert result.shape == (512, 512)


# -- ControlPanel (Qt widgets, no GL) -----------------------------


class TestControlPanel:
    def test_creation(self, qapp):
        from lem_viewer.ui.control_panel import ControlPanel

        panel = ControlPanel()
        assert panel is not None

    def test_set_channels(self, qapp):
        from lem_viewer.ui.control_panel import ControlPanel

        panel = ControlPanel()
        panel.set_channels(["elevation", "slope", "hillshade"])
        assert panel.primary_channel == "elevation"
        assert panel.secondary_channel == "elevation"

    def test_compare_mode_default_off(self, qapp):
        from lem_viewer.ui.control_panel import ControlPanel

        panel = ControlPanel()
        assert not panel.compare_mode

    def test_compare_toggle_enables_secondary(self, qapp):
        from lem_viewer.ui.control_panel import ControlPanel

        panel = ControlPanel()
        assert not panel._secondary_combo.isEnabled()
        panel._compare_check.setChecked(True)
        assert panel.compare_mode
        assert panel._secondary_combo.isEnabled()
        panel._compare_check.setChecked(False)
        assert not panel.compare_mode
        assert not panel._secondary_combo.isEnabled()

    def test_display_size_default(self, qapp):
        from lem_viewer.ui.control_panel import ControlPanel

        panel = ControlPanel()
        assert panel.max_display_size == 512

    def test_compare_signal_emitted(self, qapp):
        from lem_viewer.ui.control_panel import ControlPanel

        panel = ControlPanel()
        received: list[bool] = []
        panel.compare_toggled.connect(received.append)
        panel._compare_check.setChecked(True)
        assert received == [True]


# -- MainWindow (Qt layout, GL failures handled gracefully) --------


class TestMainWindow:
    def test_creation_no_dataset(self, qapp):
        from lem_viewer.ui.main_window import MainWindow

        window = MainWindow()
        assert window.windowTitle() == "LEM Terrain Viewer"

    def test_compare_mode_default(self, qapp):
        from lem_viewer.ui.main_window import MainWindow

        window = MainWindow()
        assert not window.compare_mode

    def test_set_dataset_populates_channels(self, qapp):
        from lem_viewer.ui.main_window import MainWindow

        window = MainWindow()
        ds = _make_dataset()
        window.set_dataset(ds)
        assert window._dataset is ds
        assert window.primary_channel == "elevation"

    def test_compare_state_tracking(self, qapp):
        from lem_viewer.ui.main_window import MainWindow

        window = MainWindow()
        ds = _make_dataset()
        window.set_dataset(ds)

        window._control_panel._compare_check.setChecked(True)
        assert window.compare_mode

        window._control_panel._compare_check.setChecked(False)
        assert not window.compare_mode

    def test_max_display_size_property(self, qapp):
        from lem_viewer.ui.main_window import MainWindow

        window = MainWindow()
        assert window.max_display_size == 512


# -- GL views (skipped when OpenGL is unavailable) -----------------


def _gl_available() -> bool:
    try:
        import pyqtgraph.opengl as gl  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _gl_available(), reason="OpenGL not available")
class TestSurface3DView:
    def test_display_name(self):
        from lem_viewer.views.surface_3d import Surface3DView

        assert Surface3DView().display_name == "3D Surface"

    def test_create_widget(self, qapp):
        from lem_viewer.views.surface_3d import Surface3DView

        ds = _make_dataset()
        view = Surface3DView()
        widget = view.create_widget(ds, channel_name="elevation")
        assert widget is not None

    def test_create_widget_with_downsampling(self, qapp):
        from lem_viewer.views.surface_3d import Surface3DView

        ds = _make_dataset(rows=128, cols=128)
        view = Surface3DView()
        widget = view.create_widget(
            ds, channel_name="elevation", max_display_size=32
        )
        assert widget is not None


@pytest.mark.skipif(not _gl_available(), reason="OpenGL not available")
class TestCompareSurface3DView:
    def test_display_name(self):
        from lem_viewer.views.compare_surface_3d import CompareSurface3DView

        assert CompareSurface3DView().display_name == "Compare 3D Surfaces"

    def test_create_compare_widget(self, qapp):
        from lem_viewer.views.compare_surface_3d import CompareSurface3DView

        ds = _make_dataset()
        view = CompareSurface3DView()
        widget = view.create_widget(
            ds, primary_channel="elevation", secondary_channel="slope"
        )
        assert widget is not None
        assert hasattr(widget, "camera_sync")
        assert hasattr(widget, "left_view")
        assert hasattr(widget, "right_view")

    def test_camera_sync_exists(self, qapp):
        from lem_viewer.views.compare_surface_3d import (
            CameraSync,
            CompareSurface3DView,
        )

        ds = _make_dataset()
        view = CompareSurface3DView()
        widget = view.create_widget(
            ds, primary_channel="elevation", secondary_channel="slope"
        )
        assert isinstance(widget.camera_sync, CameraSync)
