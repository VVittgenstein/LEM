"""Qt view embedding J31415's native raylib renderer."""
from __future__ import annotations
from typing import Any
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QApplication
from lem_viewer.models import TerrainDataset
from lem_viewer.registry import registry
from lem_viewer.ui.legend import LegendWidget
from lem_viewer.views.base import ViewPlugin
from lem_viewer.voxel.adapter import prepare_display
from lem_viewer.voxel.backend import VoxelBackend

def rescale_camera_pose(pose: str, factor: float) -> str:
    fields = pose.split()
    if len(fields) not in (16,17):
        raise ValueError("Invalid native camera snapshot")
    for index in (*range(1, 11), 15):
        fields[index] = f"{float(fields[index]) * factor:.10g}"
    return " ".join(fields)

class Voxel3DWidget(QWidget):
    state_changed = Signal(dict)
    action = Signal(dict)

    def __init__(self, dataset: TerrainDataset, channel_name: str, parent=None, **settings: Any):
        super().__init__(parent)
        self.dataset = dataset
        self.channel_name = channel_name
        self.settings = dict(settings)
        saved = settings.pop("saved_pose", None)
        self.pose: str | None = saved.get("pose") if isinstance(saved, dict) else saved
        self._saved_scene_unit = saved.get("scene_unit_m") if isinstance(saved, dict) else None
        self.pose_unit = self._saved_scene_unit
        self.foreign_window: QWindow | None = None
        self.container: QWidget | None = None
        self._closed = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        self._restored = False
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        self.status = QLabel("Starting voxel renderer…")
        self.status.setWordWrap(True)
        self._host = QVBoxLayout()
        self._host.setContentsMargins(0,0,0,0)
        self._host.addWidget(self.status)
        self._legend_layout = QVBoxLayout()
        row = QHBoxLayout()
        row.addLayout(self._host, 1)
        row.addLayout(self._legend_layout)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4,4,4,4)
        layout.addWidget(self.caption)
        layout.addLayout(row, 1)
        self.help = QLabel("Orbit: left drag rotates; middle/right drag pans; wheel zooms. M: camera; R: reset; F3: profiler.")
        self.help.setWordWrap(True)
        layout.addWidget(self.help)
        self.backend = VoxelBackend(self)
        self.backend.ready.connect(self._embed)
        self.backend.event.connect(self._event)
        self.backend.failed.connect(self._failed)
        QApplication.instance().applicationStateChanged.connect(self._application_state)
        self.update_display(channel_name=channel_name, **settings)
        QTimer.singleShot(0, self.backend.start)

    def update_display(self, *, channel_name: str, **settings) -> None:
        display = prepare_display(self.dataset, channel_name, **settings)
        self.display = display
        self.channel_name = channel_name
        self.settings.update(settings)
        water = display.water
        water_text = f"water: {water.metres:g} m ({water.source})" if water.enabled else water.source
        precision = f"height levels: {display.height_levels}, {display.layer_metres:g} m/step" if display.layer_metres else "flat elevation"
        caption = f"height ×{display.exaggeration:g} | {precision} | {water_text}"
        if not display.spacing_known: caption += " | spacing: default, physical scale unverified"
        if display.material: caption += " | material appearance rules"
        self.caption.setText(caption)
        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not display.material:
            self.legend = LegendWidget(display.scale, display.transform, display.units, display.channel_name)
            self._legend_layout.addWidget(self.legend)
            self._legend_layout.addStretch()
        self.status.setText("Building voxel mesh…"); self.status.show()
        self.backend.load(display)

    def _embed(self, handle: int) -> None:
        if self._closed: return
        self.foreign_window = QWindow.fromWinId(handle)
        if self.foreign_window is None:
            self._failed("This platform cannot embed the native renderer window.")
            self.backend.close(); return
        self.container = QWidget.createWindowContainer(self.foreign_window, self)
        self.container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.container.setMinimumSize(120, 120)
        self._host.addWidget(self.container, 1)
        self.foreign_window.show()
        self.container.show()
        for key, command in (("camera_mode","CAMERA"),("show_grid","GRID"),("show_hud","HUD"),
                             ("show_profiler","PROFILER"),("culling","CULL"),("fps_limit","FPS")):
            if key in self.settings:
                self.command(f"{command} {int(self.settings[key])}")

    def _event(self, message: dict) -> None:
        kind = message.get("event")
        if kind == "loaded":
            self.last_loaded = message
            self.status.hide()
            if self.pose and not self._restored:
                factor = self._saved_scene_unit / message["scene_unit_m"] if self._saved_scene_unit else 1.0
                self.command("POSE " + rescale_camera_pose(self.pose, factor))
                self._restored = True
        elif kind == "state":
            self.pose = message.get("pose")
            self.pose_unit = message.get("scene_unit_m", max(self.display.dx, self.display.dy))
            if message.get("camera") == 1:
                self.help.setText("Fly: WASD moves; Space/Shift rises/descends; Ctrl boosts; drag turns; wheel zooms. M: orbit; R: reset.")
            else:
                self.help.setText("Orbit: left drag rotates; middle/right drag pans; wheel zooms. M: fly; R: reset; F3: profiler.")
            self.state_changed.emit(message)
        elif kind in ("color", "open", "drop", "fullscreen", "palette", "activate"):
            self.action.emit(message)

    def command(self, command: str) -> None:
        self.backend.send(command)

    def focusInEvent(self, event) -> None:
        self.command("ACTIVE 1")
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.command("ACTIVE 0")
        super().focusOutEvent(event)

    def _application_state(self, state) -> None:
        self.command(f"ACTIVE {int(state == Qt.ApplicationState.ApplicationActive and self.hasFocus())}")

    @staticmethod
    def _native_key(event) -> int | None:
        key = event.key()
        special = {Qt.Key.Key_Shift: 340, Qt.Key.Key_Control: 341,
                   Qt.Key.Key_F3: 292, Qt.Key.Key_F11: 300}
        if key in special: return special[key]
        return key if 32 <= key <= 90 else None

    def keyPressEvent(self, event) -> None:
        key = self._native_key(event)
        if key is None: return super().keyPressEvent(event)
        if not event.isAutoRepeat(): self.command(f"KEY {key} 1")
        event.accept()

    def keyReleaseEvent(self, event) -> None:
        key = self._native_key(event)
        if key is None: return super().keyReleaseEvent(event)
        if not event.isAutoRepeat(): self.command(f"KEY {key} 0")
        event.accept()

    def _failed(self, message: str) -> None:
        self.status.setText(message); self.status.show()

    def shutdown(self) -> None:
        if self._closed: return
        self._closed = True
        if self.container: self.container.hide()
        self.backend.close()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

@registry.view("voxel_3d")
class Voxel3DView(ViewPlugin):
    @property
    def display_name(self) -> str:
        return "3D Voxel"

    def create_widget(self, dataset: TerrainDataset, **kwargs: Any) -> Voxel3DWidget:
        channel = kwargs.pop("channel_name", dataset.channel_names[0])
        return Voxel3DWidget(dataset, channel, **kwargs)
