"""Shared fixtures for viewer tests."""

from __future__ import annotations

import os

# Force offscreen rendering before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for widget tests."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
