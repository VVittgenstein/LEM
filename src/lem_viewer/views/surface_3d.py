"""3D surface view plugin using pyqtgraph OpenGL."""

from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import Signal
import pyqtgraph.opengl as gl

from lem_viewer.models import TerrainDataset
from lem_viewer.registry import registry
from lem_viewer.settings import downsample_for_display
from lem_viewer.views.base import ViewPlugin


class SyncableGLView(gl.GLViewWidget):
    """GLViewWidget that emits *camera_changed* after user interaction.

    Used by :class:`CameraSync` to keep two views in lock-step.
    """

    camera_changed = Signal()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sync_blocked = False

    # -- mouse hooks that trigger the signal -------------------------

    def mouseMoveEvent(self, ev: Any) -> None:  # noqa: N802
        super().mouseMoveEvent(ev)
        if not self._sync_blocked:
            self.camera_changed.emit()

    def wheelEvent(self, ev: Any) -> None:  # noqa: N802
        super().wheelEvent(ev)
        if not self._sync_blocked:
            self.camera_changed.emit()

    # -- camera state helpers ----------------------------------------

    def camera_state(self) -> dict[str, Any]:
        """Snapshot the current camera pose."""
        return {
            "distance": self.opts["distance"],
            "elevation": self.opts["elevation"],
            "azimuth": self.opts["azimuth"],
            "center": self.opts["center"],
        }

    def apply_camera_state(self, state: dict[str, Any]) -> None:
        """Apply a camera snapshot without re-emitting *camera_changed*."""
        self._sync_blocked = True
        self.setCameraPosition(
            pos=state["center"],
            distance=state["distance"],
            elevation=state["elevation"],
            azimuth=state["azimuth"],
        )
        self._sync_blocked = False


@registry.view("surface_3d")
class Surface3DView(ViewPlugin):
    """Single-channel 3D surface renderer."""

    @property
    def display_name(self) -> str:
        return "3D Surface"

    def create_widget(
        self, dataset: TerrainDataset, **kwargs: Any
    ) -> SyncableGLView:
        channel_name: str = kwargs.get(
            "channel_name", dataset.channel_names[0]
        )
        max_display_size: int = kwargs.get("max_display_size", 512)

        channel = dataset.get_channel(channel_name)
        z = downsample_for_display(channel.get_array(), max_display_size)

        view = SyncableGLView()
        surface = gl.GLSurfacePlotItem(
            z=z,
            shader="normalColor",
            computeNormals=True,
            smooth=True,
        )
        view.addItem(surface)

        # Position the camera to see the full terrain
        rows, cols = z.shape
        dist = float(max(rows, cols) * max(dataset.spacing) * 1.5)
        view.setCameraPosition(distance=dist, elevation=30, azimuth=45)

        return view
