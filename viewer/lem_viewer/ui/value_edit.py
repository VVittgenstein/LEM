"""Plain numeric text fields with validation only when an edit is committed."""
from __future__ import annotations

import math
import re
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit


class ValueEdit(QLineEdit):
    valueChanged = Signal(object)

    def __init__(self, minimum, maximum, value, *, decimals=None, zero_text=None, parent=None):
        super().__init__(parent)
        self.minimum=minimum;self.maximum=maximum
        self.decimals=decimals;self.zero_text=zero_text
        self._value=value
        self._help=f"Enter {'an integer' if decimals is None else 'a number'} from {minimum:g} to {maximum:g}. Press Enter to apply."
        self.setMaxLength(64)
        self.setPlaceholderText(f"{minimum:g} to {maximum:g}")
        self.setToolTip(self._help)
        self.setText(self._format(value))
        self.editingFinished.connect(self.interpretText)
        self.textEdited.connect(self._clear_error)

    def _format(self,value):
        if self.zero_text and value==0:return self.zero_text
        return str(int(value)) if self.decimals is None else f"{value:.{self.decimals}f}"

    def _clear_error(self,*_args):
        self.setStyleSheet("")
        self.setToolTip(self._help)

    def value(self):
        """Return the applied value, independently of any incomplete text."""
        return self._value

    def setValue(self,value):  # noqa: N802
        value=max(self.minimum,min(self.maximum,value))
        value=int(value) if self.decimals is None else round(float(value),self.decimals)
        changed=value!=self._value
        self._value=value
        self.setText(self._format(value))
        self._clear_error()
        if changed:self.valueChanged.emit(value)

    def interpretText(self):  # noqa: N802
        # No per-keystroke validator: clearing, inserting and replacing text
        # must work even when an intermediate string is not a valid number.
        raw=self.text().strip()
        try:
            if self.zero_text and raw.lower()==self.zero_text.lower():value=0
            elif self.decimals is None:
                if not re.fullmatch(r"[+-]?[0-9]+",raw):raise ValueError
                value=int(raw)
            else:value=float(raw)
            if not math.isfinite(value) or not self.minimum<=value<=self.maximum:raise ValueError
        except (ValueError,OverflowError):
            self.setStyleSheet("QLineEdit { border: 1px solid #b42318; }")
            self.setToolTip(f"{self._help} Current applied value: {self._format(self._value)}.")
            return False
        self.setValue(value)
        return True

    def lineEdit(self):  # noqa: N802
        """Expose the text editor for existing panel callers."""
        return self
