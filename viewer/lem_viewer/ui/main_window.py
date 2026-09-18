"""Two independent display slots sharing one loaded terrain dataset."""
from __future__ import annotations
from dataclasses import replace
import json
import logging
from pathlib import Path
from typing import Any
from PySide6.QtCore import Qt,QEvent,QSignalBlocker,QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication,QComboBox,QDockWidget,QFileDialog,QFrame,QHBoxLayout,
                               QLabel,QMainWindow,QMessageBox,QPushButton,QScrollArea,QSplitter,
                               QVBoxLayout,QWidget,QToolButton,QStyle)
from lem_viewer.models import TerrainDataset
from lem_viewer.ui.control_panel import ControlPanel,VIEW_MODES
from lem_viewer.ui.view_state import ViewState

logger=logging.getLogger(__name__)

class DisplaySlot(QFrame):
    def __init__(self,index: int,window):
        super().__init__()
        self.index=index;self.owner=window
        self.state=ViewState(mode="surface_3d" if index==0 else "map_2d")
        self.view: QWidget|None=None;self.built_mode="";self.snapshots={}
        self.display_enabled=True
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout=QVBoxLayout(self);layout.setContentsMargins(5,5,5,5)
        header=QHBoxLayout()
        self.select_button=QPushButton(f"View {index+1}");self.select_button.setCheckable(True)
        self.select_button.clicked.connect(lambda:window.select_slot(index))
        self.mode_combo=QComboBox()
        for key,label in VIEW_MODES:self.mode_combo.addItem(label,key)
        self.mode_combo.setCurrentIndex(index)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        header.addWidget(self.select_button);header.addWidget(self.mode_combo,1)
        self.close_button=QToolButton()
        self.close_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        self.close_button.setAccessibleName(f"Close View {index+1}")
        self.close_button.setToolTip(f"Close View {index+1}; reopen from the View menu")
        self.close_button.clicked.connect(lambda:window.set_slot_visible(index,False))
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.content=QVBoxLayout();layout.addLayout(self.content,1)
        self.placeholder=QLabel("Open a terrain file or directory")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content.addWidget(self.placeholder)
        self.debounce=QTimer(self);self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(lambda:window._render_slot(index))

    def _mode_changed(self):
        self.state.mode=self.mode_combo.currentData()
        self.owner.select_slot(self.index);self.owner._render_slot(self.index)

    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.FocusIn):
            self.owner.select_slot(self.index)
        return super().eventFilter(obj,event)

    def remember(self):
        if self.view is None:return
        if hasattr(self.view,"gl_view"):
            self.snapshots[self.built_mode]=self.view.gl_view.camera_state()
        elif hasattr(self.view,"plot"):
            self.snapshots[self.built_mode]=self.view.plot.viewRange()
        elif hasattr(self.view,"pose") and self.view.pose:
            self.snapshots[self.built_mode]={"pose":self.view.pose,
                "scene_unit_m":self.view.pose_unit or max(self.view.display.dx,self.view.display.dy)}

    def clear_view(self,remember=True):
        if remember:self.remember()
        if self.view is not None and hasattr(self.view,"shutdown"):self.view.shutdown()
        while self.content.count():
            item=self.content.takeAt(0)
            if item.widget():
                item.widget().hide();item.widget().deleteLater()
        self.view=None

class MainWindow(QMainWindow):
    def __init__(self,dataset: TerrainDataset|None=None,parent=None):
        super().__init__(parent)
        self.setWindowTitle("LEM Terrain Viewer");self.resize(1500,900)
        self._dataset=None;self._active_slot=0;self._current_view=None
        self._keyboard_slot=None
        self._control_panel=ControlPanel()
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self._control_panel)
        scroll.setMinimumWidth(310)
        dock=QDockWidget("Controls",self);dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,dock)
        self._splitter=QSplitter(Qt.Orientation.Horizontal)
        self._slots=[DisplaySlot(i,self) for i in range(2)]
        for slot in self._slots:self._splitter.addWidget(slot)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setStretchFactor(0,1);self._splitter.setStretchFactor(1,1)
        self._initial_layout=True
        self.setCentralWidget(self._splitter)
        file_menu=self.menuBar().addMenu("&File")
        file_menu.addAction("Open &File…",self._on_open_file)
        file_menu.addAction("Open &Directory…",self._on_open_directory)
        view_menu=self.menuBar().addMenu("&View")
        self._view_actions=[]
        for index in range(2):
            action=QAction(f"View {index+1}",self);action.setCheckable(True);action.setChecked(True)
            action.toggled.connect(lambda checked,i=index:self.set_slot_visible(i,checked))
            view_menu.addAction(action);self._view_actions.append(action)
        view_menu.addSeparator()
        full=QAction("Fullscreen",self);full.setShortcut("F11");full.triggered.connect(self._fullscreen)
        view_menu.addAction(full)
        cp=self._control_panel
        cp.slot_changed.connect(self.select_slot)
        cp.settings_changed.connect(self._on_setting_changed)
        cp.reset_camera.connect(lambda:self._native_command("RESET"))
        cp.palette_file_requested.connect(self._open_palette)
        cp.sync_changed.connect(lambda _:self._update_sync())
        self.setAcceptDrops(True)
        QApplication.instance().installEventFilter(self)
        self.select_slot(0)
        if dataset is not None:self.set_dataset(dataset)

    @property
    def compare_mode(self):return all(slot.display_enabled for slot in self._slots)
    @property
    def primary_channel(self):return self._slots[0].state.channel
    @property
    def secondary_channel(self):return self._slots[1].state.channel
    @property
    def max_display_size(self):return self._slots[self._active_slot].state.max_display_size

    def select_slot(self,index: int):
        if not self._slots[index].display_enabled:return
        if index!=self._active_slot:self._control_panel.commit_pending_edits()
        self._active_slot=index
        for slot in self._slots:
            with QSignalBlocker(slot.select_button):slot.select_button.setChecked(slot.index==index)
            slot.setStyleSheet("DisplaySlot { border: 2px solid palette(highlight); }" if slot.index==index else "")
        self._control_panel.set_state(self._slots[index].state,index)
        self._current_view=self._slots[index].view
        self._update_sync()

    def set_slot_visible(self,index: int,visible: bool):
        slot=self._slots[index]
        if visible==slot.display_enabled:return
        if not visible and not self._slots[1-index].display_enabled:return
        slot.display_enabled=visible
        if visible:
            if self._dataset is None and not slot.content.count():
                label=QLabel("Open a terrain file or directory")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter);slot.content.addWidget(label)
            slot.show();self._render_slot(index)
            self._splitter.setSizes([600,600])
            self.select_slot(index)
        else:
            if self._keyboard_slot==index:self._set_keyboard_target(None)
            slot.debounce.stop();slot.clear_view();slot.hide()
            self.select_slot(1-index)
        visibility=[item.display_enabled for item in self._slots]
        self._control_panel.set_slot_visibility(visibility)
        for item,action in zip(self._slots,self._view_actions):
            with QSignalBlocker(action):action.setChecked(item.display_enabled)
            can_close=all(visibility)
            action.setEnabled(can_close or not item.display_enabled)
            item.close_button.setEnabled(can_close)
        self._update_sync()

    def set_dataset(self,dataset: TerrainDataset):
        self._dataset=dataset
        primary=dataset.metadata.get("primary_channel",dataset.channel_names[0])
        if primary not in dataset.channels:primary=dataset.channel_names[0]
        self._control_panel.set_channels(dataset.channel_names)
        for slot in self._slots:
            slot.debounce.stop();slot.snapshots.clear();slot.clear_view(remember=False)
            slot.state.channel=primary
            self._render_slot(slot.index)
        self.select_slot(self._active_slot)
        self.setWindowTitle(f"LEM Terrain Viewer · {dataset.dataset_id}")
        if self._initial_layout:
            self._initial_layout=False
            QTimer.singleShot(0,lambda:self._splitter.setSizes([600,600]))

    def _on_setting_changed(self,*_args):
        slot=self._slots[self._active_slot];old=slot.state
        state=self._control_panel.state();slot.state=state
        with QSignalBlocker(slot.mode_combo):slot.mode_combo.setCurrentIndex(slot.mode_combo.findData(state.mode))
        if state.mode=="voxel_3d" and slot.built_mode=="voxel_3d" and hasattr(slot.view,"command"):
            for field,command in [("camera_mode","CAMERA"),("show_grid","GRID"),("show_hud","HUD"),
                                  ("show_profiler","PROFILER"),("culling","CULL"),("fps_limit","FPS")]:
                if getattr(old,field)!=getattr(state,field):
                    slot.view.settings[field]=getattr(state,field)
                    slot.view.command(f"{command} {int(getattr(state,field))}")
            if state.display_options()!=old.display_options() or state.channel!=old.channel:
                slot.debounce.start(140)
        else:self._render_slot(slot.index)

    def _render_slot(self,index: int):
        slot=self._slots[index];slot.debounce.stop()
        if self._dataset is None or not slot.display_enabled:return
        state=slot.state
        try:
            if state.mode=="voxel_3d" and slot.built_mode=="voxel_3d" and hasattr(slot.view,"update_display"):
                slot.view.update_display(channel_name=state.channel,**state.display_options())
            else:
                slot.clear_view()
                options=state.display_options()
                if state.mode=="map_2d":
                    from lem_viewer.views.map_2d import Map2DView
                    widget=Map2DView().create_widget(self._dataset,channel_name=state.channel,**options)
                elif state.mode=="voxel_3d":
                    from lem_viewer.views.voxel_3d import Voxel3DWidget
                    widget=Voxel3DWidget(self._dataset,state.channel,**options,**state.native_options(),
                                         saved_pose=slot.snapshots.get("voxel_3d"))
                    widget.state_changed.connect(lambda message,i=index:self._native_state(i,message))
                    widget.action.connect(lambda message,i=index:self._native_action(i,message))
                else:
                    from lem_viewer.views.surface_3d import Surface3DView
                    widget=Surface3DView().create_widget(self._dataset,channel_name=state.channel,**options)
                    widget.gl_view.camera_changed.connect(lambda i=index:self._sync_surface_camera(i))
                slot.view=widget;slot.built_mode=state.mode;slot.content.addWidget(widget,1)
                saved=slot.snapshots.get(state.mode)
                if saved is not None:
                    if hasattr(widget,"gl_view"):widget.gl_view.apply_camera_state(saved)
                    elif hasattr(widget,"plot"):widget.plot.setRange(xRange=saved[0],yRange=saved[1],padding=0)
                widget.installEventFilter(slot)
                for child in widget.findChildren(QWidget):child.installEventFilter(slot)
        except Exception as exc:
            logger.exception("Could not create view %s",index+1)
            if slot.view is None:
                label=QLabel(str(exc));label.setWordWrap(True);slot.view=label
                slot.built_mode="";slot.content.addWidget(label)
            else:self.statusBar().showMessage(str(exc),15000)
        if index==self._active_slot:self._current_view=slot.view
        self._update_sync()

    def _update_sync(self):
        ready=all(slot.display_enabled and slot.built_mode=="surface_3d" and hasattr(slot.view,"gl_view") for slot in self._slots)
        self._control_panel._sync_check.setEnabled(ready)

    def _sync_surface_camera(self,source: int):
        self.select_slot(source)
        if not self._control_panel._sync_check.isChecked():return
        a,b=self._slots[source],self._slots[1-source]
        if a.built_mode==b.built_mode=="surface_3d" and hasattr(a.view,"gl_view") and hasattr(b.view,"gl_view"):
            b.view.gl_view.apply_camera_state(a.view.gl_view.camera_state())

    def _native_command(self,command):
        view=self._slots[self._active_slot].view
        if hasattr(view,"command"):view.command(command)

    def _native_state(self,index: int,message: dict):
        slot=self._slots[index]
        if not slot.display_enabled:return
        changes={"camera_mode":message["camera"],"show_grid":message["grid"],"show_hud":message["hud"],
                 "show_profiler":message["profiler"],"culling":message["culling"],
                 "fps_limit":{0:0,1:60,2:144}[message["fps_mode"]]}
        changed=any(getattr(slot.state,k)!=v for k,v in changes.items())
        for k,v in changes.items():setattr(slot.state,k,v)
        if changed and index==self._active_slot:self._control_panel.set_state(slot.state,index)

    def _native_action(self,index: int,message: dict):
        if not self._slots[index].display_enabled:return
        kind=message["event"]
        focus=QApplication.focusWidget()
        sidebar_focus=focus is not None and (focus is self._control_panel or self._control_panel.isAncestorOf(focus))
        if kind not in ("activate","drop") and (self._keyboard_slot!=index or sidebar_focus):return
        self.select_slot(index)
        slot=self._slots[index]
        if kind=="fullscreen":self._fullscreen()
        elif kind=="open":self._on_open_file()
        elif kind=="drop":self._load_via_app(message["path"])
        elif kind=="palette":self._open_palette()
        elif kind=="activate":
            self._set_keyboard_target(index)
            # A foreign process gets Windows focus without updating Qt's logical
            # focus widget. Record the container so reactivation returns input
            # to this viewport rather than the last edited sidebar spinbox.
            if getattr(slot.view,"container",None) is not None:
                slot.view.setFocus(Qt.FocusReason.MouseFocusReason)
                slot.view.command("ACTIVE 1")
                slot.view.command("FOCUS")
        elif kind=="color":
            scheme=message["scheme"]
            if scheme=="cycle":slot.state.material=not slot.state.material
            elif scheme=="material":slot.state.material=True
            elif scheme in self._dataset.channels:slot.state.material=False;slot.state.channel=scheme
            else:self.statusBar().showMessage(f"This dataset has no {scheme} channel",5000);return
            self._control_panel.set_state(slot.state,index);self._render_slot(index)

    def _open_palette(self):
        path,_=QFileDialog.getOpenFileName(self,"Load material palette","","INI palette (*.ini)")
        if path:self._native_command("PALETTE "+json.dumps(Path(path).as_posix(),ensure_ascii=False))

    def eventFilter(self, obj, event):
        # Sidebar editors own their keys even if a foreign-window activation
        # left a stale logical keyboard target. Never forward numeric editing.
        event_type=event.type()
        sidebar=isinstance(obj,QWidget) and (obj is self._control_panel or self._control_panel.isAncestorOf(obj))
        if sidebar and event_type in (QEvent.Type.FocusIn,QEvent.Type.MouseButtonPress,
                                      QEvent.Type.KeyPress,QEvent.Type.KeyRelease,QEvent.Type.ShortcutOverride):
            self._set_keyboard_target(None)
            return super().eventFilter(obj,event)
        if event_type==QEvent.Type.MouseButtonPress and isinstance(obj,QWidget) and obj.window() is self:
            inside=False
            for slot in self._slots:
                if slot.built_mode=="voxel_3d" and slot.view is not None:
                    if obj is slot.view or slot.view.isAncestorOf(obj):
                        self._set_keyboard_target(slot.index);inside=True;break
            if not inside:self._set_keyboard_target(None)
        if event_type==QEvent.Type.FocusIn and event.reason() in (Qt.FocusReason.TabFocusReason,Qt.FocusReason.BacktabFocusReason):
            self._set_keyboard_target(None)
        if event_type in (QEvent.Type.KeyPress,QEvent.Type.KeyRelease) and self.isActiveWindow() and self._keyboard_slot is not None:
            view=self._slots[self._keyboard_slot].view
            if hasattr(view,"_native_key") and view._native_key(event) is not None:
                view.command("ACTIVE 1")
                if event_type==QEvent.Type.KeyPress:view.keyPressEvent(event)
                else:view.keyReleaseEvent(event)
                return True
        return super().eventFilter(obj,event)

    def _set_keyboard_target(self,index):
        for slot in self._slots:
            if slot.index!=index and hasattr(slot.view,"command"):slot.view.command("ACTIVE 0")
        self._keyboard_slot=index

    def _fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()
    def _on_open_file(self):
        path,_=QFileDialog.getOpenFileName(self,"Open Terrain File","","Terrain files (*.npy *.flem);;All files (*)")
        if path:self._load_via_app(path)
    def _on_open_directory(self):
        path=QFileDialog.getExistingDirectory(self,"Open Terrain Directory")
        if path:self._load_via_app(path)
    def _load_via_app(self,path):
        from lem_viewer.app import Application
        try:self.set_dataset(Application().load_source(Path(path)))
        except Exception as exc:
            logger.exception("Failed to load %s",path)
            QMessageBox.warning(self,"Cannot open terrain",str(exc))
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
    def dropEvent(self,event):
        urls=event.mimeData().urls()
        if urls and urls[0].isLocalFile():self._load_via_app(urls[0].toLocalFile());event.acceptProposedAction()
    def closeEvent(self,event):
        QApplication.instance().removeEventFilter(self)
        for slot in self._slots:slot.debounce.stop();slot.clear_view()
        super().closeEvent(event)
