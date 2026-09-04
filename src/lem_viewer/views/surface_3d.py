"""3D surface view plugin using pyqtgraph OpenGL.

Height comes from the dataset's elevation channel (see ``semantics.find_elevation_channel``); colour
comes from the selected channel through a banded colour scale, so drainage area (log10) can be draped
over the terrain. Datasets without an elevation channel fall back to the selected channel as height
when it is a linear quantity, or to a flat plane otherwise.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyqtgraph.opengl as gl
from pyqtgraph import Vector
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lem_viewer.colormaps import DEFAULT_LEVELS, DEFAULT_PALETTE, BandedScale
from lem_viewer.models import TerrainChannel, TerrainDataset
from lem_viewer.registry import registry
from lem_viewer.semantics import KIND_DRAINAGE_AREA, KINDS, find_elevation_channel
from lem_viewer.settings import downsample_for_display
from lem_viewer.ui.legend import LegendWidget
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


AUTO_RELIEF_FRACTION = 0.15


def auto_vertical_exaggeration(extent_xy: float, relief: float) -> float:
    """Height factor that makes the relief span ``AUTO_RELIEF_FRACTION`` of the horizontal extent.

    Works whatever the units are: a 6 km massif on a 500 km grid gets about ×12, a 50 m noise field on
    a 500-cell unit grid gets about ×1.5, and a flat plane keeps ×1.
    """
    if relief <= 0 or extent_xy <= 0:
        return 1.0
    return AUTO_RELIEF_FRACTION * extent_xy / relief


def build_surface(dataset: TerrainDataset, channel_name: str, *, max_display_size: int = 512,
                  palette: str = DEFAULT_PALETTE, levels: int = DEFAULT_LEVELS,
                  vertical_exaggeration: float | None = None):
    """Return (GLSurfacePlotItem, BandedScale, extents, colour channel, height channel, exaggeration)."""
    color_ch: TerrainChannel = dataset.get_channel(channel_name)
    height_ch = find_elevation_channel(dataset)
    if height_ch is None and color_ch.kind != KIND_DRAINAGE_AREA and color_ch.transform == "linear":
        height_ch = color_ch

    values = downsample_for_display(color_ch.display_array(), max_display_size)
    if height_ch is not None:
        z = downsample_for_display(np.asarray(height_ch.get_array(), dtype=float), max_display_size)
    else:
        z = np.zeros_like(values)
    if z.shape != values.shape:
        raise ValueError(f"height {z.shape} and colour {values.shape} grids differ")

    rows, cols = z.shape
    full_rows, full_cols = dataset.grid_shape
    dy, dx = dataset.spacing
    step_y = dy * full_rows / rows
    step_x = dx * full_cols / cols
    xs = np.arange(cols, dtype=float) * step_x
    ys = np.arange(rows, dtype=float) * step_y

    finite_z = z[np.isfinite(z)]
    relief = float(finite_z.max() - finite_z.min()) if finite_z.size else 0.0
    extent_xy = float(max(xs[-1] if cols > 1 else step_x, ys[-1] if rows > 1 else step_y))
    if vertical_exaggeration and vertical_exaggeration > 0:
        vex = float(vertical_exaggeration)
    else:
        vex = auto_vertical_exaggeration(extent_xy, relief)

    scale = BandedScale.from_array(values, levels=levels, palette=palette)
    rgba = scale.rgba(values).astype(np.float32) / 255.0
    fill = float(finite_z.min()) if finite_z.size else 0.0
    z_plot = np.nan_to_num(z, nan=fill) * vex

    # GLSurfacePlotItem expects x of length N, y of length M, z of shape (N, M): transpose (rows, cols).
    # Vertex colours must be flat (N*M, 4) in the same vertex order as z (x index major); pyqtgraph passes
    # the array straight to MeshData.setVertexColors, so a (N, M, 4) array breaks face indexing at paint time.
    surface = gl.GLSurfacePlotItem(
        x=xs, y=ys, z=np.ascontiguousarray(z_plot.T),
        colors=np.ascontiguousarray(rgba.transpose(1, 0, 2)).reshape(-1, 4),
        shader="shaded", computeNormals=True, smooth=True,
    )
    extents = (float(xs[-1]) if cols > 1 else step_x, float(ys[-1]) if rows > 1 else step_y,
               float(z_plot.max() - z_plot.min()))
    return surface, scale, extents, color_ch, height_ch, vex


def make_gl_view(dataset: TerrainDataset, channel_name: str, **kwargs: Any) -> tuple[SyncableGLView, BandedScale, TerrainChannel, float]:
    surface, scale, extents, color_ch, _height_ch, vex = build_surface(dataset, channel_name, **kwargs)
    view = SyncableGLView()
    view.addItem(surface)
    ex, ey, ez = extents
    view.setCameraPosition(pos=Vector(ex / 2.0, ey / 2.0, ez / 2.0), distance=float(max(ex, ey) * 1.3),
                           elevation=35, azimuth=-60)
    return view, scale, color_ch, vex


class Surface3DWidget(QWidget):
    """GL view plus legend and a one-line description of what height and colour show."""

    def __init__(self, dataset: TerrainDataset, channel_name: str, parent: QWidget | None = None, **kwargs: Any) -> None:
        super().__init__(parent)
        self.gl_view, self.scale, self.channel, self.vertical_exaggeration = make_gl_view(dataset, channel_name, **kwargs)
        height_ch = find_elevation_channel(dataset)
        height_name = height_ch.name if height_ch is not None else (
            channel_name if self.channel.kind != KIND_DRAINAGE_AREA and self.channel.transform == "linear" else "flat plane")
        info = KINDS.get(self.channel.kind)
        self.legend = LegendWidget(self.scale, self.channel.transform, self.channel.units,
                                   info.label if info else self.channel.name)
        caption = (f"height: {height_name} ×{self.vertical_exaggeration:g}   colour: {self.channel.name}"
                   + (" (log10 bands)" if self.channel.transform == "log10" else ""))
        left = QVBoxLayout()
        left.addWidget(QLabel(caption))
        left.addWidget(self.gl_view, stretch=1)
        right = QVBoxLayout()
        right.addWidget(self.legend)
        right.addStretch()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(left, stretch=1)
        layout.addLayout(right)


@registry.view("surface_3d")
class Surface3DView(ViewPlugin):
    """Single-channel 3D surface renderer with banded colour drape."""

    @property
    def display_name(self) -> str:
        return "3D Surface"

    def _kwargs(self, dataset: TerrainDataset, kwargs: dict[str, Any]) -> dict[str, Any]:
        channel = dataset.get_channel(kwargs.get("channel_name", dataset.channel_names[0]))
        defaults = channel.display_defaults
        return {
            "max_display_size": int(kwargs.get("max_display_size", 512)),
            "palette": kwargs.get("palette") or (defaults.palette if defaults else DEFAULT_PALETTE),
            "levels": int(kwargs.get("levels") or (defaults.levels if defaults else DEFAULT_LEVELS)),
            "vertical_exaggeration": kwargs.get("vertical_exaggeration"),
        }

    def create_gl_view(self, dataset: TerrainDataset, **kwargs: Any) -> SyncableGLView:
        """Bare GL view (no legend), used by the compare view for camera synchronisation."""
        channel_name: str = kwargs.get("channel_name", dataset.channel_names[0])
        view, _scale, _ch, _vex = make_gl_view(dataset, channel_name, **self._kwargs(dataset, kwargs))
        return view

    def create_widget(self, dataset: TerrainDataset, **kwargs: Any) -> Surface3DWidget:
        channel_name: str = kwargs.get("channel_name", dataset.channel_names[0])
        return Surface3DWidget(dataset, channel_name, **self._kwargs(dataset, kwargs))
