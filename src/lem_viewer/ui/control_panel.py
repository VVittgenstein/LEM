"""Channel selection and display controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lem_viewer.colormaps import DEFAULT_LEVELS, DEFAULT_PALETTE, PALETTES

VIEW_MODES: list[tuple[str, str]] = [("surface_3d", "3D Surface"), ("map_2d", "2D Map")]


class ControlPanel(QWidget):
    """Sidebar panel for dataset / channel / display controls."""

    channel_changed = Signal(str)
    compare_toggled = Signal(bool)
    secondary_channel_changed = Signal(str)
    display_size_changed = Signal(int)
    view_mode_changed = Signal(str)
    palette_changed = Signal(str)
    levels_changed = Signal(int)
    vertical_exaggeration_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    # -- UI construction ---------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Primary channel
        layout.addWidget(QLabel("Channel:"))
        self._channel_combo = QComboBox()
        self._channel_combo.currentTextChanged.connect(self.channel_changed)
        layout.addWidget(self._channel_combo)

        # View mode
        layout.addWidget(QLabel("View:"))
        self._view_combo = QComboBox()
        for key, label in VIEW_MODES:
            self._view_combo.addItem(label, key)
        self._view_combo.currentIndexChanged.connect(
            lambda _i: self.view_mode_changed.emit(self.view_mode)
        )
        layout.addWidget(self._view_combo)

        # Colour scale
        layout.addWidget(QLabel("Colour bands:"))
        self._palette_combo = QComboBox()
        self._palette_combo.addItems(list(PALETTES.keys()))
        self._palette_combo.setCurrentText(DEFAULT_PALETTE)
        self._palette_combo.currentTextChanged.connect(self.palette_changed)
        layout.addWidget(self._palette_combo)

        layout.addWidget(QLabel("Levels:"))
        self._levels_spin = QSpinBox()
        self._levels_spin.setRange(2, 64)
        self._levels_spin.setValue(DEFAULT_LEVELS)
        self._levels_spin.valueChanged.connect(self.levels_changed)
        layout.addWidget(self._levels_spin)

        # Vertical exaggeration (0 = automatic)
        layout.addWidget(QLabel("Vertical exaggeration (0 = auto):"))
        self._vex_spin = QDoubleSpinBox()
        self._vex_spin.setRange(0.0, 1000.0)
        self._vex_spin.setDecimals(1)
        self._vex_spin.setSingleStep(1.0)
        self._vex_spin.setValue(0.0)
        self._vex_spin.valueChanged.connect(self.vertical_exaggeration_changed)
        layout.addWidget(self._vex_spin)

        # Compare mode
        self._compare_check = QCheckBox("Compare Mode")
        self._compare_check.toggled.connect(self._on_compare_toggled)
        layout.addWidget(self._compare_check)

        # Secondary channel
        layout.addWidget(QLabel("Secondary Channel:"))
        self._secondary_combo = QComboBox()
        self._secondary_combo.setEnabled(False)
        self._secondary_combo.currentTextChanged.connect(
            self.secondary_channel_changed
        )
        layout.addWidget(self._secondary_combo)

        # Display downsampling
        layout.addWidget(QLabel("Max Display Size:"))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(64, 4096)
        self._size_spin.setSingleStep(64)
        self._size_spin.setValue(512)
        self._size_spin.valueChanged.connect(self.display_size_changed)
        layout.addWidget(self._size_spin)

        layout.addStretch()

    # -- Slots -------------------------------------------------------

    def _on_compare_toggled(self, checked: bool) -> None:
        self._secondary_combo.setEnabled(checked)
        self.compare_toggled.emit(checked)

    # -- Public API --------------------------------------------------

    def set_channels(self, names: list[str]) -> None:
        """Populate both channel combo boxes (signals blocked during update)."""
        for combo in (self._channel_combo, self._secondary_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            combo.blockSignals(False)

    def set_primary_channel(self, name: str) -> None:
        """Select a channel in the primary combo without emitting channel_changed."""
        idx = self._channel_combo.findText(name)
        if idx >= 0:
            self._channel_combo.blockSignals(True)
            self._channel_combo.setCurrentIndex(idx)
            self._channel_combo.blockSignals(False)

    def set_view_mode(self, mode: str) -> None:
        idx = self._view_combo.findData(mode)
        if idx >= 0:
            self._view_combo.setCurrentIndex(idx)

    @property
    def compare_mode(self) -> bool:
        return self._compare_check.isChecked()

    @property
    def primary_channel(self) -> str:
        return self._channel_combo.currentText()

    @property
    def secondary_channel(self) -> str:
        return self._secondary_combo.currentText()

    @property
    def max_display_size(self) -> int:
        return self._size_spin.value()

    @property
    def view_mode(self) -> str:
        return str(self._view_combo.currentData())

    @property
    def palette(self) -> str:
        return self._palette_combo.currentText()

    @property
    def levels(self) -> int:
        return self._levels_spin.value()

    @property
    def vertical_exaggeration(self) -> float | None:
        v = self._vex_spin.value()
        return v if v > 0 else None
