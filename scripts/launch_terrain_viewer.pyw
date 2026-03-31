"""Windows launch helper for the LEM Terrain Viewer.

The .pyw extension tells Windows to use pythonw.exe when it is double-clicked.
The same file is also invoked by ``launch_terrain_viewer.bat`` via python.exe so
the console launcher and the no-console launcher share the same bootstrap path.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ensure_src_on_path() -> Path:
    """Make the repo-local ``src/`` importable without editable install."""

    src_dir = repo_root() / "src"
    src_dir_str = str(src_dir)
    if src_dir_str not in sys.path:
        sys.path.insert(0, src_dir_str)
    return src_dir


def format_launch_error(exc: BaseException) -> str:
    return (
        "LEM Terrain Viewer failed to start.\n"
        "Verify that this repository checkout is intact and that the selected "
        "Python environment has the viewer dependencies installed.\n\n"
        f"{exc.__class__.__name__}: {exc}"
    )


def _show_error_dialog(message: str) -> None:
    """Show a GUI error when launched via pythonw.exe with no console."""

    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        return

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        messagebox.showerror("LEM Terrain Viewer", message)
    finally:
        root.destroy()


def run(argv: list[str] | None = None) -> int:
    ensure_src_on_path()

    from lem_viewer.main import main as viewer_main  # noqa: E402

    viewer_main(argv)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except Exception as exc:
        message = format_launch_error(exc)
        if sys.stderr is not None and hasattr(sys.stderr, "write"):
            print(message, file=sys.stderr)
            traceback.print_exc()
        else:
            _show_error_dialog(message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
