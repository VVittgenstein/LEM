"""Vertical banded legend widget (one swatch per band, edge values in data units)."""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from lem_viewer.colormaps import BandedScale, format_edge


class LegendWidget(QWidget):
    """Draws the bands of a :class:`BandedScale` from high (top) to low (bottom)."""

    BAND_H = 18
    SWATCH_W = 22
    TOP = 24

    def __init__(self, scale: BandedScale, transform: str, units: str, title: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scale = scale
        self.transform = transform
        self.units = units
        self.title = title
        self.setMinimumWidth(170)
        self.setMinimumHeight(self.TOP + self.BAND_H * (scale.levels + 1) + 8)

    def edge_labels(self) -> list[str]:
        """Edge labels from top (max) to bottom (min), in data units."""
        edges = self.scale.edges
        return [format_edge(float(e), self.transform, self.units) for e in edges[::-1]]

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        ink = self.palette().text().color()
        painter.setPen(ink)
        painter.drawText(4, 14, self.title)
        colors = self.scale.colors
        edges = self.scale.edges
        n = self.scale.levels
        for i in range(n):
            band = n - 1 - i  # highest band drawn first
            y = self.TOP + i * self.BAND_H
            c = colors[band]
            painter.fillRect(4, y, self.SWATCH_W, self.BAND_H, QColor(int(c[0]), int(c[1]), int(c[2])))
            painter.setPen(ink)
            painter.drawText(4 + self.SWATCH_W + 6, y + 4, format_edge(float(edges[band + 1]), self.transform, self.units))
        painter.drawText(4 + self.SWATCH_W + 6, self.TOP + n * self.BAND_H + 4,
                         format_edge(float(edges[0]), self.transform, self.units))
        painter.end()
