"""Asynchronous native process with an explicit shutdown and input-file lifetime."""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import tempfile
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from lem_viewer.voxel.adapter import DisplayInput

logger = logging.getLogger(__name__)

def backend_path() -> Path:
    if override := os.environ.get("LEM_VOXEL_BACKEND"):
        return Path(override)
    viewer = Path(__file__).resolve().parents[2]
    name = "lem_voxel_backend.exe" if os.name == "nt" else "lem_voxel_backend"
    paths = (viewer / "build/native/bin/Release" / name, viewer / "build/native/bin" / name)
    return next((p for p in paths if p.is_file()), paths[0])

class VoxelBackend(QObject):
    ready = Signal(object)
    event = Signal(dict)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.errorOccurred.connect(self._error)
        self.process.finished.connect(self._finished)
        self._buffer = bytearray()
        self._errors = ""
        self._closing = False
        self.is_ready = False
        self._revision = 0
        self._loading = False
        self._pending: tuple[DisplayInput, bool] | None = None
        cache = Path(__file__).resolve().parents[3] / "output/viewer/sessions"
        cache.mkdir(parents=True, exist_ok=True)
        self._directory = tempfile.TemporaryDirectory(prefix="lem-voxel-", dir=cache)
        self._files: dict[int, Path] = {}
        self.start_timer = QTimer(self)
        self.start_timer.setSingleShot(True)
        self.start_timer.timeout.connect(lambda: self._start_timeout())

    def start(self) -> None:
        if self._closing: return
        path = backend_path()
        if not path.is_file():
            self.failed.emit("Voxel backend is not built. Run viewer/scripts/build_voxel_viewer.py with --raylib-source PATH or --download-cache PATH.")
            return
        env = QProcessEnvironment.systemEnvironment()
        env.insert("OMP_NUM_THREADS", "4")
        self.process.setProcessEnvironment(env)
        self.process.setProgram(str(path))
        self.process.start()
        self.start_timer.start(15000)

    def send(self, command: str) -> None:
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.write((command + "\n").encode("utf-8"))

    def load(self, display: DisplayInput, *, reset: bool = False) -> None:
        if not self.is_ready or self._loading:
            self._pending = (display, reset)
            return
        self._revision += 1
        self._loading = True
        path = Path(self._directory.name) / f"display-{self._revision}.bin"
        display.write(path)
        self._files[self._revision] = path
        self.send(f"LOAD {json.dumps(path.as_posix(), ensure_ascii=False)} {self._revision} {int(reset)}")

    def _read(self) -> None:
        self._buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b"\n" in self._buffer:
            line, _, self._buffer = self._buffer.partition(b"\n")
            text = line.decode("utf-8", errors="replace").strip()
            if not text.startswith("LEM_EVENT "):
                if text: logger.debug("voxel: %s", text)
                continue
            try:
                message = json.loads(text[len("LEM_EVENT "):])
            except (ValueError, TypeError):
                logger.warning("Invalid native event: %s", text)
                continue
            kind = message.get("event")
            if kind == "ready":
                self.start_timer.stop(); self.is_ready = True
                self.ready.emit(int(message["handle"]))
                if self._pending:
                    display, reset = self._pending; self._pending = None
                    self.load(display, reset=reset)
            if kind in ("loaded", "error"):
                self._loading = False
                revision = message.get("revision", 0)
                for key in list(self._files):
                    if key <= revision:
                        self._files.pop(key).unlink(missing_ok=True)
                if revision and revision < self._revision:
                    continue
            self.event.emit(message)
            if kind == "error": self.failed.emit(message.get("message", "Native renderer failed"))
            if kind in ("loaded", "error") and self._pending:
                display, reset = self._pending; self._pending = None
                self.load(display, reset=reset)

    def _stderr(self) -> None:
        self._errors = (self._errors + bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace"))[-4096:]

    def _error(self, _error) -> None:
        if not self._closing:
            self.failed.emit(self.process.errorString())

    def _finished(self, code: int, _status) -> None:
        self.start_timer.stop(); self.is_ready = False
        if not self._closing:
            self.failed.emit(f"Voxel renderer stopped (code {code}). {self._errors}".strip())

    def _start_timeout(self) -> None:
        self.failed.emit("Voxel renderer did not create a window within 15 seconds.")
        self.close()

    def close(self) -> None:
        if self._closing: return
        self._closing = True; self.start_timer.stop()
        self.send("QUIT")
        if self.process.state() != QProcess.ProcessState.NotRunning and not self.process.waitForFinished(800):
            self.process.kill(); self.process.waitForFinished(800)
        self.is_ready = False
        self._directory.cleanup()
