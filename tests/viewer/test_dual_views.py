"""Regression for independent display state and preserved view positions."""
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from lem_viewer.ui.main_window import MainWindow
from lem_viewer.models import TerrainChannel, TerrainDataset

def data():
    ds=TerrainDataset("views",(5,6),spacing=(1000,1000))
    ds.add_channel(TerrainChannel("elevation",units="m",array=np.arange(30).reshape(5,6)-2000))
    ds.add_channel(TerrainChannel("other",array=np.arange(30).reshape(5,6)*2))
    return ds

def test_slots_keep_settings_when_selection_changes(qapp):
    window=MainWindow(data());cp=window._control_panel
    cp._levels_spin.setValue(7)
    window.select_slot(1);cp._levels_spin.setValue(19);cp._channel_combo.setCurrentText("other")
    window.select_slot(0)
    assert cp.levels==7 and cp.primary_channel=="elevation"
    window.select_slot(1)
    assert cp.levels==19 and cp.primary_channel=="other"
    window.close()

def test_surface_camera_survives_colour_change_and_mode_roundtrip(qapp):
    window=MainWindow(data());view=window._slots[0].view.gl_view
    view.setCameraPosition(distance=12345,azimuth=25,elevation=18)
    window._control_panel._levels_spin.setValue(8)
    assert window._slots[0].view.gl_view.opts["distance"]==12345
    window._control_panel.set_view_mode("map_2d")
    window._control_panel.set_view_mode("surface_3d")
    assert window._slots[0].view.gl_view.opts["azimuth"]==25
    window.close()

def test_surface_camera_sync_remains_available(qapp):
    window=MainWindow(data());window._slots[1].mode_combo.setCurrentIndex(0)
    a,b=(slot.view.gl_view for slot in window._slots)
    a.setCameraPosition(azimuth=11,elevation=47);a.camera_changed.emit()
    assert b.opts["azimuth"]==11 and b.opts["elevation"]==47
    window._control_panel._sync_check.setChecked(False)
    a.setCameraPosition(azimuth=28);a.camera_changed.emit()
    assert b.opts["azimuth"]==11
    window.close()

def test_negative_elevation_surface_camera_looks_at_data(qapp):
    window=MainWindow(data())
    assert window._slots[0].view.gl_view.opts["center"].z() < -1900
    window.close()

def test_kilometre_heights_use_same_geometry_scale_in_both_renderers(qapp):
    from lem_viewer.views.surface_3d import build_surface
    from lem_viewer.voxel.adapter import prepare_display
    from lem_viewer.channels.builtins import SlopeProvider
    ds=data();ds.channels["elevation"].units="km"
    surface,_,extent,_,_,_=build_surface(ds,"elevation",vertical_exaggeration=1)
    native=prepare_display(ds,"elevation",vertical_exaggeration=1)
    assert extent[2]==native.maximum-native.minimum==29000
    slope=SlopeProvider().provide(ds)[0].get_array()
    assert np.allclose(slope,np.sqrt(6**2+1**2))

def test_native_camera_snapshot_preserves_physical_position_when_sampling_changes():
    from lem_viewer.views.voxel_3d import rescale_camera_pose
    pose="1 10 20 30 4 5 6 4 5 6 100 0.5 0.6 0.7 0.8 50"
    scaled=rescale_camera_pose(pose,.5).split()
    assert list(map(float,scaled[1:4]))==[5,10,15]
    assert float(scaled[10])==50 and float(scaled[15])==25
    assert scaled[11:15]==["0.5","0.6","0.7","0.8"]
    zoomed=rescale_camera_pose(pose+" 12.5",.5).split()
    assert zoomed[-1]=="12.5" and zoomed[:-1]==scaled


def test_value_box_supports_delete_append_and_select_all_replacement(qapp):
    from lem_viewer.ui.value_edit import ValueEdit
    edit=ValueEdit(2,4096,36);edit.show();edit.setFocus();qapp.processEvents()
    QTest.keyClick(edit,Qt.Key.Key_End);QTest.keyClicks(edit,"11")
    assert edit.text()=="3611" and edit.value()==36
    QTest.keyClick(edit,Qt.Key.Key_Backspace)
    assert edit.text()=="361"
    QTest.keyClick(edit,Qt.Key.Key_Home);QTest.keyClick(edit,Qt.Key.Key_Delete)
    assert edit.text()=="61"
    QTest.keyClick(edit,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(edit,Qt.Key.Key_Backspace)
    assert edit.text()==""
    QTest.keyClicks(edit,"36");QTest.keyClicks(edit,"1")
    assert edit.text()=="361"
    QTest.keyClick(edit,Qt.Key.Key_Return);assert edit.value()==361
    QTest.keyClick(edit,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(edit,"126");QTest.keyClick(edit,Qt.Key.Key_Return)
    assert edit.value()==126
    edit.selectAll();QTest.keyClicks(edit,"99999");QTest.keyClick(edit,Qt.Key.Key_Return)
    assert edit.text()=="99999" and edit.value()==126
    edit.selectAll();QTest.keyClicks(edit,"2");QTest.keyClick(edit,Qt.Key.Key_Return)
    assert edit.value()==2
    edit.close()


def test_partial_number_edit_commits_once_and_survives_status_update(qapp):
    from dataclasses import replace
    from lem_viewer.ui.control_panel import ControlPanel
    from lem_viewer.ui.view_state import ViewState
    panel=ControlPanel();state=ViewState(mode="voxel_3d",height_levels=36,material=True)
    panel.set_state(state,0);panel.show();qapp.processEvents()
    spin=panel._height_spin;spin.setFocus();spin.lineEdit().setSelection(0,1)
    changes=[];panel.settings_changed.connect(lambda:changes.append(panel.state().height_levels))
    QTest.keyClicks(spin,"12")
    assert spin.lineEdit().text()=="126"
    assert spin.value()==36 and not changes
    panel.set_state(replace(state,show_grid=True),0)
    assert spin.lineEdit().text()=="126"
    QTest.keyClick(spin,Qt.Key.Key_Return)
    assert spin.value()==126 and changes==[126] and panel.state().material
    spin.selectAll();QTest.keyClicks(spin,"256")
    panel._camera_combo.setFocus();qapp.processEvents()
    assert spin.value()==256 and changes==[126,256]
    panel.close()


def test_sidebar_digits_override_stale_native_keyboard_target(qapp):
    from lem_viewer.views.voxel_3d import Voxel3DWidget
    class RecordingVoxel(QWidget):
        _native_key=staticmethod(Voxel3DWidget._native_key)
        def __init__(self):
            super().__init__();self.commands=[];self.settings={}
        def command(self,value):self.commands.append(value)
        def keyPressEvent(self,event):self.commands.append(f"KEY {event.key()} 1")
        def keyReleaseEvent(self,event):self.commands.append(f"KEY {event.key()} 0")
    window=MainWindow(data());slot=window._slots[0];slot.clear_view()
    view=RecordingVoxel();slot.view=view;slot.built_mode="voxel_3d"
    slot.state.mode="voxel_3d";slot.state.material=True;slot.content.addWidget(view)
    window.select_slot(0);window.show();qapp.processEvents()
    spin=window._control_panel._height_spin;spin.setFocus();spin.selectAll()
    window._keyboard_slot=0  # A stale foreign-window focus target must not own an editor's keys.
    QTest.keyClicks(spin,"2")
    assert spin.lineEdit().text()=="2"
    assert window._keyboard_slot is None
    assert not any(command.startswith("KEY ") for command in view.commands)
    window._native_action(0,{"event":"color","scheme":"elevation"})
    assert slot.state.material
    QTest.keyClick(spin,Qt.Key.Key_Return)
    assert slot.state.height_levels==2 and slot.state.material
    window.close()


def test_closing_and_restoring_views_preserves_settings_and_camera(qapp):
    window=MainWindow(data());slot=window._slots[0]
    slot.view.gl_view.setCameraPosition(distance=12345,azimuth=31,elevation=27)
    window._control_panel._levels_spin.setValue(9)
    window.set_slot_visible(0,False)
    assert slot.view is None and not slot.display_enabled
    assert window._active_slot==1 and not window.compare_mode
    assert not window._slots[1].close_button.isEnabled()
    window.set_slot_visible(1,False)
    assert window._slots[1].display_enabled
    window._view_actions[0].trigger()
    assert window.compare_mode and slot.state.levels==9
    assert slot.view.gl_view.opts["distance"]==12345 and slot.view.gl_view.opts["azimuth"]==31
    window.set_slot_visible(1,False)
    assert window._active_slot==0 and not window._slots[1].display_enabled
    window.close()


def test_switching_slots_commits_pending_number_to_its_original_slot(qapp):
    window=MainWindow(data());window.show();qapp.processEvents()
    spin=window._control_panel._levels_spin;spin.setFocus();spin.selectAll()
    QTest.keyClicks(spin,"16")
    assert window._slots[0].state.levels==12
    window.select_slot(1)
    assert window._slots[0].state.levels==16
    assert window._slots[1].state.levels==12 and spin.value()==12
    window.close()
