"""Tests for the Windows launcher bootstrap contract."""

from __future__ import annotations

import io
import runpy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYW_LAUNCHER = REPO_ROOT / "scripts" / "launch_terrain_viewer.pyw"
BAT_LAUNCHER = REPO_ROOT / "launch_terrain_viewer.bat"


def load_pyw_launcher() -> dict[str, object]:
    """Load the .pyw launcher module without executing its __main__ block."""

    return runpy.run_path(str(PYW_LAUNCHER), run_name="lem_windows_launcher_test")


def test_pyw_launcher_bootstraps_repo_src(monkeypatch):
    launcher = load_pyw_launcher()
    ensure_src_on_path = launcher["ensure_src_on_path"]

    src_dir = str(REPO_ROOT / "src")
    original_path = list(sys.path)
    monkeypatch.setattr(sys, "path", [p for p in original_path if p != src_dir])

    added = ensure_src_on_path()

    assert added == REPO_ROOT / "src"
    assert sys.path[0] == src_dir


def test_pyw_launcher_reports_meaningful_errors(monkeypatch):
    launcher = load_pyw_launcher()
    main = launcher["main"]

    def boom(_argv=None):
        raise ModuleNotFoundError("No module named 'PySide6'")

    monkeypatch.setitem(main.__globals__, "run", boom)
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)

    exit_code = main([])
    output = stderr.getvalue()

    assert exit_code == 1
    assert "LEM Terrain Viewer failed to start" in output
    assert "ModuleNotFoundError" in output
    assert "PySide6" in output


def test_batch_launcher_bootstrap_contract():
    content = BAT_LAUNCHER.read_text(encoding="utf-8")

    assert 'set "WINDOWS_ENV=%REPO_ROOT%\\lem-env-win"' in content
    assert 'set "WINDOWS_PYTHON=%WINDOWS_ENV%\\Scripts\\python.exe"' in content
    assert "-m venv" in content
    assert "-m pip install -e" in content
    assert 'scripts\\launch_terrain_viewer.pyw' in content
    assert "Could not find a usable Python interpreter" in content
    assert "Terrain viewer failed to start" in content
    assert "pause" in content.lower()
