"""Explicit real-window integration check. Run outside offscreen pytest."""
from __future__ import annotations
import argparse
import ctypes
import itertools
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"viewer"))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QProcess
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from lem_viewer.app import Application
from lem_viewer.ui.main_window import MainWindow

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=ROOT/"bench/results/examples/mountain")
    parser.add_argument("--output",type=Path,default=ROOT/"output/tests/viewer-native")
    parser.add_argument("--display-size",type=int,default=64)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);window=MainWindow();window.resize(1550,900)
    ds=Application().load_source(args.source)
    for slot in window._slots:slot.state.max_display_size=args.display_size
    window.set_dataset(ds);window.show()
    records=[];processes=[];failures=[]
    def wait(predicate,timeout=30):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            time.sleep(.01)
        raise AssertionError("Timed out waiting for native renderer")
    def ready():
        return all(slot.built_mode!="voxel_3d" or hasattr(slot.view,"last_loaded") for slot in window._slots)
    def track():
        for slot in window._slots:
            if hasattr(slot.view,"backend"):
                slot.view.backend.failed.connect(failures.append)
                processes.append(int(slot.view.backend.process.processId()))
    try:
        for left,right in itertools.product(("surface_3d","map_2d","voxel_3d"),repeat=2):
            for slot,mode in zip(window._slots,(left,right)):
                slot.mode_combo.setCurrentIndex(slot.mode_combo.findData(mode))
            wait(ready);track()
            assert not failures,failures
            records.append({"left":left,"right":right,"ready":True})
        a,b=(slot.view for slot in window._slots)
        a.settings["height_levels"]=36
        b.settings["height_levels"]=72
        a.update_display(channel_name="elevation",**a.settings)
        b.update_display(channel_name="elevation",**b.settings)
        wait(lambda:a.last_loaded["levels"]==36 and b.last_loaded["levels"]==72)
        assert abs(a.last_loaded["top_max_scene"]-b.last_loaded["top_max_scene"])<1e-5
        assert abs(a.last_loaded["top_min_scene"]-b.last_loaded["top_min_scene"])<1e-5
        for i,view in enumerate((a,b)):
            view.command("CAPTURE "+json.dumps((args.output/f"native-{i}.png").resolve().as_posix()))
        wait(lambda:all((args.output/f"native-{i}.png").is_file() for i in (0,1)))
        scale_results=[a.last_loaded,b.last_loaded]
        invalid_palette=args.output/"invalid-palette.ini"
        invalid_palette.write_text("[general]\nao_darkness=invalid\n",encoding="utf-8")
        original_pid=int(a.backend.process.processId())
        a.command("PALETTE "+json.dumps(invalid_palette.resolve().as_posix()))
        wait(lambda:bool(failures))
        assert int(a.backend.process.processId())==original_pid
        assert a.backend.process.state()==QProcess.ProcessState.Running
        palette_errors=list(failures);failures.clear()
        # A native failure remains visible and does not close the other display.
        right_pid=int(b.backend.process.processId())
        a.backend.process.kill();wait(lambda:a.backend.process.state()==QProcess.ProcessState.NotRunning)
        wait(lambda:bool(failures))
        assert int(b.backend.process.processId())==right_pid
        assert b.backend.process.state()==QProcess.ProcessState.Running
        expected_failures=list(failures);failures.clear()
        window._slots[0].mode_combo.setCurrentIndex(1)
        window._slots[0].mode_combo.setCurrentIndex(2)
        wait(ready);track();assert not failures
        # Qt's proxy must preserve a short key press and stop held movement
        # when the user moves back to the sidebar.
        view=window._slots[0].view
        window._native_action(0,{"event":"activate"})
        QTest.keyClick(view,Qt.Key.Key_M)
        wait(lambda:window._slots[0].state.camera_mode==1)
        QTest.keyPress(view,Qt.Key.Key_W)
        wait(lambda:view.pose is not None)
        QTest.qWait(120)
        QTest.mouseClick(window._control_panel._levels_spin,Qt.MouseButton.LeftButton)
        wait(lambda:window._keyboard_slot is None)
        QTest.keyRelease(window._control_panel._levels_spin,Qt.Key.Key_W)
        QTest.qWait(300)
        stopped_pose=view.pose
        QTest.qWait(350)
        assert view.pose==stopped_pose,"Movement continued after sidebar focus"
        fly_zoom_pose=view.pose.split();fly_zoom_pose[16]="12.5"
        view.command("POSE "+" ".join(fly_zoom_pose))
        wait(lambda:float(view.pose.split()[16])==12.5)
        # Editing a number must neither dispatch digit shortcuts nor rebuild
        # the mesh until the edit is committed.
        cp=window._control_panel
        cp._material_check.setChecked(True);cp._height_spin.setValue(36)
        wait(lambda:not window._slots[0].debounce.isActive() and not view.backend._loading
             and view.last_loaded["levels"]==36 and view.display.material)
        spin=cp._height_spin;spin.setFocus();spin.lineEdit().setSelection(0,1)
        revision=view.last_loaded["revision"]
        QTest.keyClicks(spin,"12");QTest.qWait(300)
        assert spin.lineEdit().text()=="126" and view.last_loaded["revision"]==revision, {
            "text":spin.lineEdit().text(),"value":spin.value(),"before_revision":revision,
            "after_revision":view.last_loaded["revision"],"keyboard_slot":window._keyboard_slot}
        assert window._slots[0].state.material
        QTest.keyClick(spin,Qt.Key.Key_Return)
        wait(lambda:view.last_loaded["levels"]==126)
        spin.selectAll();QTest.keyClicks(spin,"36");QTest.keyClicks(spin,"11")
        assert spin.text()=="3611"
        QTest.keyClick(spin,Qt.Key.Key_Return)
        wait(lambda:view.last_loaded["levels"]==3611)
        window.activateWindow();spin.setFocus();QTest.qWait(100)
        assert app.focusWidget() is spin, {"active":window.isActiveWindow(),
            "focus":str(app.focusWidget()),"window_focus":str(window.focusWidget()),
            "enabled":spin.isEnabled(),"visible":spin.isVisible()}
        QTest.keyClick(app.focusWidget(),Qt.Key.Key_End)
        QTest.keyClick(app.focusWidget(),Qt.Key.Key_Backspace)
        assert spin.text()=="361"
        QTest.keyClick(app.focusWidget(),Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(app.focusWidget(),Qt.Key.Key_Delete)
        assert spin.text()==""
        QTest.keyClicks(app.focusWidget(),"36");QTest.keyClicks(app.focusWidget(),"1")
        assert spin.text()=="361"
        QTest.keyClick(app.focusWidget(),Qt.Key.Key_Return)
        wait(lambda:view.last_loaded["levels"]==361)
        assert float(view.pose.split()[16])==12.5,"Mesh rebuilding discarded fly zoom"
        spin.selectAll();QTest.keyClicks(spin,"2");QTest.keyClick(spin,Qt.Key.Key_Return)
        wait(lambda:view.last_loaded["levels"]==2)
        assert window._slots[0].state.material and cp._material_check.isChecked()
        cp._height_spin.setValue(36);wait(lambda:view.last_loaded["levels"]==36)
        QTest.qWait(300)
        remembered_pose=view.pose
        closed_process=view.backend.process
        window.set_slot_visible(0,False);app.processEvents()
        assert closed_process.state()==QProcess.ProcessState.NotRunning
        assert window._active_slot==1 and not window._slots[1].close_button.isEnabled()
        assert int(b.backend.process.processId())==right_pid
        window.grab().save(str(args.output/"single-view-layout.png"))
        window.set_slot_visible(0,True);wait(ready);track()
        view=window._slots[0].view
        wait(lambda:view.pose is not None and all(math.isclose(float(a),float(b),rel_tol=1e-6,abs_tol=1e-6)
             for a,b in zip(view.pose.split(),remembered_pose.split())))
        restored_pose=view.pose
        window.resize(1250,760);QTest.qWait(250)
        window.showMinimized();QTest.qWait(200);window.showNormal();QTest.qWait(350)
        capture_path=args.output/"resized.png"
        capture_path.unlink(missing_ok=True)
        view.command("CAPTURE "+json.dumps(capture_path.resolve().as_posix()))
        wait(capture_path.is_file)
        from PySide6.QtGui import QImage
        captured=QImage(str(capture_path))
        expected_width=round(view.container.width()*view.container.devicePixelRatioF())
        expected_height=round(view.container.height()*view.container.devicePixelRatioF())
        resize_result={"device_pixel_ratio":view.container.devicePixelRatioF(),
                       "captured_pixels":[captured.width(),captured.height()],
                       "expected_pixels":[expected_width,expected_height],
                       "container_size":[view.container.width(),view.container.height()],
                       "foreign_size":[view.foreign_window.width(),view.foreign_window.height()],
                       "foreign_dpr":view.foreign_window.devicePixelRatio()}
        (args.output/"resize.json").write_text(json.dumps(resize_result,indent=2))
        assert abs(captured.width()-expected_width)<=1,resize_result
        assert abs(captured.height()-expected_height)<=1,resize_result
        window.grab().save(str(args.output/"dual-view-layout.png"))
        legend_widths=[slot.view.legend.width() if hasattr(slot.view,"legend") else None for slot in window._slots]
        window.close();app.processEvents()
        live=[]
        if os.name=="nt":
            kernel=ctypes.WinDLL("kernel32",use_last_error=True)
            kernel.OpenProcess.restype=ctypes.c_void_p
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
            for pid in set(processes):
                if not pid:continue
                handle=kernel.OpenProcess(0x1000,False,pid)
                if handle:
                    code=ctypes.c_ulong();kernel.GetExitCodeProcess(handle,ctypes.byref(code));kernel.CloseHandle(handle)
                    if code.value==259:live.append(pid)
        assert not live,live
        result={"combinations":records,"scale_invariance":scale_results,
                "expected_backend_failure":expected_failures,"remaining_processes":live,"errors":failures,
                "expected_palette_error":palette_errors,"keyboard_and_focus":"passed","resize_and_restore":resize_result,
                "numeric_editing":"passed","close_restore_native_view":"passed",
                "plain_value_editing":"passed","fly_zoom_restore":"passed",
                "saved_pose":remembered_pose,"restored_pose":restored_pose,"legend_widths":legend_widths}
        (args.output/"results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps(result))
    finally:
        window.close();app.processEvents()

if __name__=="__main__":main()
