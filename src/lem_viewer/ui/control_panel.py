"""Channel selection and display controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ControlPanel(QWidget):
    """Sidebar panel for dataset / channel / compare controls."""

    channel_changed = Signal(str)
    compare_toggled = Signal(bool)
    secondary_channel_changed = Signal(str)
    display_size_changed = Signal(int)

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
