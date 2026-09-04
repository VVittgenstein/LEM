"""2D map view: one channel as a banded colour image with a legend and a hover readout."""

from __future__ import annotations

from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lem_viewer.colormaps import DEFAULT_LEVELS, DEFAULT_PALETTE, BandedScale
from lem_viewer.models import TerrainChannel, TerrainDataset
from lem_viewer.registry import registry
from lem_viewer.semantics import KINDS, inverse_display
from lem_viewer.settings import downsample_for_display
from lem_viewer.ui.legend import LegendWidget
from lem_viewer.views.base import ViewPlugin


class Map2DWidget(QWidget):
    """Image of one channel (banded colours) with axes in km, a legend, and a hover readout."""

    def __init__(self, dataset: TerrainDataset, channel: TerrainChannel, *, palette: str, levels: int,
                 max_display_size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.dataset = dataset
        self.channel = channel
        values = downsample_for_display(channel.display_array(), max_display_size)
        self._values = values
        self.scale = BandedScale.from_array(values, levels=levels, palette=palette)
        rgba = self.scale.rgba(values)

        rows, cols = values.shape
        full_rows, full_cols = channel.get_array().shape
        dy, dx = dataset.spacing
        step_y = dy * full_rows / rows
        step_x = dx * full_cols / cols
        self._step_km = (step_y / 1e3, step_x / 1e3)
        width_km = cols * step_x / 1e3
        height_km = rows * step_y / 1e3

        self.plot = pg.PlotWidget()
        self.plot.setAspectLocked(True)
        self.plot.setLabel("bottom", "x (km)")
        self.plot.setLabel("left", "y (km)")
        self.image = pg.ImageItem(image=rgba, axisOrder="row-major")
        self.image.setRect(QRectF(0.0, 0.0, width_km, height_km))
        self.plot.addItem(self.image)
        self.plot.setRange(xRange=(0, width_km), yRange=(0, height_km), padding=0.02)

        info = KINDS.get(channel.kind)
        title = f"{channel.name} ({channel.units})" if channel.units else channel.name
        if channel.transform == "log10":
            title += ", log10 bands"
        self.legend = LegendWidget(self.scale, channel.transform, channel.units,
                                   info.label if info else channel.name)

        self.readout = QLabel("")
        self.readout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        right = QVBoxLayout()
        right.addWidget(self.legend)
        right.addStretch()
        left = QVBoxLayout()
        left.addWidget(QLabel(title))
        left.addWidget(self.plot, stretch=1)
        left.addWidget(self.readout)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(left, stretch=1)
        layout.addLayout(right)

        self.plot.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def value_at(self, x_km: float, y_km: float) -> tuple[float, float] | None:
        """(display value, data value) under a map position, or None outside the grid or at NaN."""
        step_y, step_x = self._step_km
        if x_km < 0 or y_km < 0:
            return None
        col = int(x_km / step_x)
        row = int(y_km / step_y)
        rows, cols = self._values.shape
        if row < rows and col < cols:
            v = float(self._values[row, col])
            if np.isfinite(v):
                return v, inverse_display(v, self.channel.transform)
        return None

    def _on_mouse_moved(self, pos: Any) -> None:
        p = self.plot.plotItem.vb.mapSceneToView(pos)
        hit = self.value_at(p.x(), p.y())
        if hit is None:
            self.readout.setText("")
            return
        _disp, data = hit
        self.readout.setText(
            f"x = {p.x():.1f} km, y = {p.y():.1f} km, {self.channel.name} = {data:.4g} {self.channel.units}"
        )


@registry.view("map_2d")
class Map2DView(ViewPlugin):
    """Plan-view map of one channel with banded colours."""

    @property
    def display_name(self) -> str:
        return "2D Map"

    def create_widget(self, dataset: TerrainDataset, **kwargs: Any) -> Map2DWidget:
        channel_name: str = kwargs.get("channel_name", dataset.channel_names[0])
        channel = dataset.get_channel(channel_name)
        defaults = channel.display_defaults
        return Map2DWidget(
            dataset,
            channel,
            palette=kwargs.get("palette") or (defaults.palette if defaults else DEFAULT_PALETTE),
            levels=int(kwargs.get("levels") or (defaults.levels if defaults else DEFAULT_LEVELS)),
            max_display_size=int(kwargs.get("max_display_size", 512)),
        )
