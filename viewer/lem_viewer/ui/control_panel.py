"""Controls editing one explicitly selected display slot."""
from __future__ import annotations
from dataclasses import replace
from PySide6.QtCore import Signal, QSignalBlocker
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QFormLayout,QComboBox,
                               QCheckBox,QPushButton,QLabel,QGroupBox)
from lem_viewer.colormaps import PALETTES
from lem_viewer.ui.view_state import ViewState
from lem_viewer.ui.value_edit import ValueEdit

VIEW_MODES = [("surface_3d","3D Surface"),("map_2d","2D Map"),("voxel_3d","3D Voxel")]

class ControlPanel(QWidget):
    settings_changed = Signal()
    slot_changed = Signal(int)
    reset_camera = Signal()
    palette_file_requested = Signal()
    sync_changed = Signal(bool)

    def __init__(self,parent=None):
        super().__init__(parent)
        self._state=ViewState()
        layout=QVBoxLayout(self)
        self._slot_combo=QComboBox()
        self._slot_combo.addItems(["View 1 (left)","View 2 (right)"])
        layout.addWidget(QLabel("Editing display:"))
        layout.addWidget(self._slot_combo)
        self._slot_combo.currentIndexChanged.connect(self.slot_changed)
        form=QFormLayout()
        self._view_combo=QComboBox()
        for key,label in VIEW_MODES:self._view_combo.addItem(label,key)
        self._channel_combo=QComboBox()
        self._palette_combo=QComboBox();self._palette_combo.addItems(list(PALETTES))
        self._levels_spin=ValueEdit(2,64,12)
        self._vex_spin=ValueEdit(0,1000,1,decimals=2,zero_text="Auto")
        self._size_spin=ValueEdit(16,4096,512)
        for label,control in [("View",self._view_combo),("Colour channel",self._channel_combo),
                              ("Colour palette",self._palette_combo),("Colour levels",self._levels_spin),
                              ("Vertical scale",self._vex_spin),("Max display size",self._size_spin)]:
            form.addRow(label,control)
        layout.addLayout(form)
        self._voxel_group=QGroupBox("Voxel display")
        voxel=QFormLayout(self._voxel_group)
        self._height_spin=ValueEdit(2,4096,36)
        self._height_spin.setToolTip("Height precision only. Changing this count preserves physical proportions.")
        self._material_check=QCheckBox("Material appearance")
        self._water_auto=QCheckBox("Water level from data / default");self._water_auto.setChecked(True)
        self._water_spin=ValueEdit(-1e7,1e7,0,decimals=2)
        self._camera_combo=QComboBox();self._camera_combo.addItems(["Orbit","Fly"])
        self._reset=QPushButton("Reset camera");self._reset.clicked.connect(self.reset_camera)
        self._grid_check=QCheckBox("Reference grid")
        self._hud_check=QCheckBox("Status overlay")
        self._profiler_check=QCheckBox("Performance panel")
        self._culling_check=QCheckBox("Frustum culling");self._culling_check.setChecked(True)
        self._fps_combo=QComboBox()
        for label,value in [("60 FPS",60),("144 FPS",144),("Uncapped",0)]:self._fps_combo.addItem(label,value)
        self._palette_file=QPushButton("Load material palette…");self._palette_file.clicked.connect(self.palette_file_requested)
        voxel.addRow("Height levels",self._height_spin)
        for control in (self._material_check,self._water_auto):voxel.addRow(control)
        voxel.addRow("Water override (m)",self._water_spin)
        voxel.addRow("Camera",self._camera_combo)
        for control in (self._reset,self._grid_check,self._hud_check,self._profiler_check,self._culling_check):voxel.addRow(control)
        voxel.addRow("Frame limit",self._fps_combo);voxel.addRow(self._palette_file)
        layout.addWidget(self._voxel_group)
        self._sync_check=QCheckBox("Sync two surface cameras")
        self._sync_check.setChecked(True);self._sync_check.toggled.connect(self.sync_changed)
        layout.addWidget(self._sync_check)
        layout.addStretch()
        self._controls=[self._view_combo,self._channel_combo,self._palette_combo,self._levels_spin,
                        self._vex_spin,self._size_spin,self._height_spin,self._material_check,self._water_auto,
                        self._water_spin,self._camera_combo,self._grid_check,self._hud_check,
                        self._profiler_check,self._culling_check,self._fps_combo]
        for control in self._controls:
            signal=(control.currentIndexChanged if isinstance(control,QComboBox) else
                    control.toggled if isinstance(control,QCheckBox) else control.valueChanged)
            signal.connect(self._changed)
        self._update_visibility()

    def _changed(self,*_args):
        self._update_visibility();self.settings_changed.emit()

    def _update_visibility(self):
        voxel=self.view_mode=="voxel_3d"
        self._voxel_group.setVisible(voxel)
        self._vex_spin.setEnabled(self.view_mode!="map_2d")
        scientific=not (voxel and self._material_check.isChecked())
        for control in (self._channel_combo,self._palette_combo,self._levels_spin):control.setEnabled(scientific)
        self._water_spin.setEnabled(not self._water_auto.isChecked())

    def set_channels(self,names):
        blocker=QSignalBlocker(self._channel_combo)
        self._channel_combo.clear();self._channel_combo.addItems(names)
        del blocker

    def commit_pending_edits(self):
        focus=QApplication.focusWidget()
        if focus is None:return
        for control in self._controls:
            if isinstance(control,ValueEdit) and (focus is control or control.isAncestorOf(focus)):
                control.interpretText()

    def set_state(self,state: ViewState,slot: int):
        focus=QApplication.focusWidget()
        same_slot=self._slot_combo.currentIndex()==slot
        def set_number(control,value):
            # Native status messages must not replace a partially edited number.
            editing=same_slot and focus is not None and (focus is control or control.isAncestorOf(focus))
            if not editing:control.setValue(value)
        blockers=[QSignalBlocker(c) for c in self._controls+[self._slot_combo]]
        self._state=replace(state)
        self._slot_combo.setCurrentIndex(slot)
        self._view_combo.setCurrentIndex(self._view_combo.findData(state.mode))
        self._channel_combo.setCurrentText(state.channel)
        self._palette_combo.setCurrentText(state.palette)
        set_number(self._levels_spin,state.levels);set_number(self._vex_spin,state.vertical_exaggeration)
        set_number(self._size_spin,state.max_display_size);set_number(self._height_spin,state.height_levels)
        self._material_check.setChecked(state.material);self._water_auto.setChecked(state.water_auto)
        set_number(self._water_spin,state.water_metres);self._camera_combo.setCurrentIndex(state.camera_mode)
        for field,control in [("show_grid",self._grid_check),("show_hud",self._hud_check),
                              ("show_profiler",self._profiler_check),("culling",self._culling_check)]:
            control.setChecked(getattr(state,field))
        self._fps_combo.setCurrentIndex(self._fps_combo.findData(state.fps_limit))
        del blockers
        self._update_visibility()

    def set_slot_visibility(self,visible):
        for index,enabled in enumerate(visible):
            self._slot_combo.model().item(index).setEnabled(enabled)
            suffix=(" (left)" if index==0 else " (right)") if all(visible) else ("" if enabled else " (closed)")
            self._slot_combo.setItemText(index,f"View {index+1}{suffix}")

    def state(self):
        return ViewState(mode=self.view_mode,channel=self.primary_channel,palette=self.palette,levels=self.levels,
                         vertical_exaggeration=self._vex_spin.value(),max_display_size=self.max_display_size,
                         height_levels=self._height_spin.value(),material=self._material_check.isChecked(),
                         water_auto=self._water_auto.isChecked(),water_metres=self._water_spin.value(),
                         camera_mode=self._camera_combo.currentIndex(),show_grid=self._grid_check.isChecked(),
                         show_hud=self._hud_check.isChecked(),show_profiler=self._profiler_check.isChecked(),
                         culling=self._culling_check.isChecked(),fps_limit=self._fps_combo.currentData())

    def set_primary_channel(self,name):
        with QSignalBlocker(self._channel_combo):self._channel_combo.setCurrentText(name)
    def set_view_mode(self,mode):
        self._view_combo.setCurrentIndex(self._view_combo.findData(mode))
    @property
    def primary_channel(self):return self._channel_combo.currentText()
    @property
    def max_display_size(self):return self._size_spin.value()
    @property
    def view_mode(self):return self._view_combo.currentData()
    @property
    def palette(self):return self._palette_combo.currentText()
    @property
    def levels(self):return self._levels_spin.value()
    @property
    def vertical_exaggeration(self):return self._vex_spin.value() or None
