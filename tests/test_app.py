import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEvent, QProcess
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

import app as gui
import ui_helpers
import worker


class GuiStabilitySmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def make_window(self):
        start_patcher = patch.object(QProcess, "start")
        start_mock = start_patcher.start()
        self.addCleanup(start_patcher.stop)
        window = gui.MainWindow()

        def dispose_window():
            if isValid(window):
                window.close()
                window.refresh_timer.stop()
                window.lsblk_timeout_timer.stop()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                QApplication.processEvents()

        self.addCleanup(dispose_window)
        return window, start_mock

    def test_window_initializes_and_starts_async_lsblk_without_blocking(self):
        window, start_patch = self.make_window()
        start_patch.assert_called_once()
        self.assertEqual(start_patch.call_args.args[0], "lsblk")
        self.assertTrue(window._lsblk_request_active)
        self.assertTrue(window.lsblk_timeout_timer.isActive())
        self.assertEqual(
            window.lsblk_process.state(),
            QProcess.ProcessState.NotRunning,
        )

    def test_second_refresh_is_ignored_while_lsblk_is_in_progress(self):
        window, start_patch = self.make_window()
        initial_calls = start_patch.call_count
        window.refresh_devices(preserve_selection=True, quiet=True)
        self.assertEqual(start_patch.call_count, initial_calls)

    def test_empty_raw_model_is_kept_separate_from_display_fallback(self):
        window, _ = self.make_window()
        disk = {
            "path": "/dev/sdb",
            "name": "/dev/sdb",
            "type": "disk",
            "size": 1024,
            "model": "   ",
            "serial": "TEST123",
            "wwn": "",
            "tran": "usb",
            "rm": False,
            "ro": False,
            "maj:min": "8:16",
            "children": [],
        }
        with patch.object(gui, "read_diskseq", return_value="17"), patch.object(
            gui, "device_by_id", return_value=""
        ):
            window._populate_devices([disk], None, True)
        data = window.device_combo.currentData()
        self.assertEqual(data["model"], "   ")
        self.assertEqual(data["model_display"], "/dev/sdb")
        self.assertTrue(window.device_combo.currentText().startswith("/dev/sdb"))

    def _silent_timeout(self, window):
        window._lsblk_request_active = False
        window.refresh_devices(preserve_selection=True, quiet=True)
        self.assertTrue(window._lsblk_request_active)
        window._lsblk_timed_out()

    def _successful_silent_refresh(self, window):
        window._lsblk_request_active = False
        window.refresh_devices(preserve_selection=True, quiet=True)
        with patch.object(
            window.lsblk_process, "readAllStandardOutput",
            return_value=b'{"blockdevices": []}',
        ), patch.object(
            window.lsblk_process, "readAllStandardError", return_value=b""
        ):
            window._lsblk_finished(0, QProcess.ExitStatus.NormalExit)

    def test_repeated_silent_lsblk_timeout_is_logged_once_until_a_refresh_succeeds(self):
        window, _ = self.make_window()
        window.log.clear()
        needle = "időtúllépéssel leállt"

        for _ in range(3):
            self._silent_timeout(window)
        self.assertEqual(window.log.toPlainText().count(needle), 1)

        self._successful_silent_refresh(window)
        self._silent_timeout(window)
        self.assertEqual(window.log.toPlainText().count(needle), 2)

    def test_a_different_silent_lsblk_error_is_still_logged(self):
        window, _ = self.make_window()
        window.log.clear()
        self._silent_timeout(window)
        window._lsblk_request_active = False
        window.refresh_devices(preserve_selection=True, quiet=True)
        window._finish_lsblk_error("Az lsblk parancs váratlanul leállt.")
        text = window.log.toPlainText()
        self.assertEqual(text.count("időtúllépéssel leállt"), 1)
        self.assertEqual(text.count("váratlanul leállt"), 1)

    def test_manual_refresh_timeout_always_shows_the_dialog(self):
        window, _ = self.make_window()
        window.log.clear()
        with patch.object(gui.QMessageBox, "warning") as warning:
            for _ in range(2):
                window._lsblk_request_active = False
                window.refresh_devices()
                window._lsblk_timed_out()
        self.assertEqual(warning.call_count, 2)
        self.assertEqual(window.log.toPlainText(), "")

    def test_shutdown_window_explicitly_deletes_the_qobject_tree(self):
        window, _ = self.make_window()
        refresh_timer = window.refresh_timer
        discovery_process = window.lsblk_process
        gui.shutdown_window(window)
        self.assertFalse(isValid(window))
        self.assertFalse(isValid(refresh_timer))
        self.assertFalse(isValid(discovery_process))

    def test_application_subprocess_exits_after_explicit_qt_cleanup(self):
        script = textwrap.dedent(
            """
            import sys
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication
            import app

            qt_app = QApplication([])
            window = app.MainWindow()
            window.show()
            QTimer.singleShot(100, window.close)
            exit_code = qt_app.exec()
            app.shutdown_window(window)
            del window
            raise SystemExit(exit_code)
            """
        )
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"GUI subprocess failed. stdout:\\n{result.stdout}\\nstderr:\\n{result.stderr}",
        )


class BiosGrubAvailabilityTests(unittest.TestCase):
    def make_grub_dir(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        for name in files:
            (directory / name).write_bytes(b"x")
        return directory

    def test_gui_check_uses_the_same_grub_files_as_the_worker(self):
        self.assertEqual(ui_helpers.GRUB_PC_DIRECTORY, worker.GRUB_PC_DIRECTORY)
        self.assertEqual(ui_helpers.GRUB_PC_REQUIRED_FILES, worker.GRUB_PC_REQUIRED_FILES)

    def test_available_when_grub_install_and_all_i386_pc_files_exist(self):
        directory = self.make_grub_dir(ui_helpers.GRUB_PC_REQUIRED_FILES)
        self.assertTrue(
            ui_helpers.bios_grub_available(lambda _name: "/usr/bin/grub-install", directory)
        )

    def test_unavailable_without_grub_install(self):
        directory = self.make_grub_dir(ui_helpers.GRUB_PC_REQUIRED_FILES)
        self.assertFalse(ui_helpers.bios_grub_available(lambda _name: None, directory))

    def test_unavailable_without_i386_pc_directory_or_with_a_missing_module(self):
        which = lambda _name: "/usr/bin/grub-install"
        directory = self.make_grub_dir(ui_helpers.GRUB_PC_REQUIRED_FILES[:-1])
        self.assertFalse(ui_helpers.bios_grub_available(which, directory))
        self.assertFalse(ui_helpers.bios_grub_available(which, directory / "missing"))


class BootModeSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def make_window(self, grub_available=True):
        start_patcher = patch.object(QProcess, "start")
        self.start_mock = start_patcher.start()
        self.addCleanup(start_patcher.stop)
        with patch.object(gui, "bios_grub_available", return_value=grub_available):
            window = gui.MainWindow()

        def dispose_window():
            if isValid(window):
                window.process = None
                window.close()
                window.refresh_timer.stop()
                window.lsblk_timeout_timer.stop()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                QApplication.processEvents()

        self.addCleanup(dispose_window)
        return window

    def make_image(self, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        image = Path(tmp.name) / name
        image.write_bytes(b"\0" * 4096)
        return image

    def select_image(self, window, image, windows_iso):
        with patch.object(gui, "is_windows_install_iso", return_value=windows_iso) as probe:
            window.iso_edit.setText(str(image))
            window.inspect_image(str(image))
        return probe

    def test_selector_defaults_to_uefi_and_is_inactive_in_raw_mode(self):
        window = self.make_window()
        self.select_image(window, self.make_image("win.iso"), True)
        self.assertEqual(window.boot_mode_combo.currentData(), "uefi")
        self.assertEqual(window.boot_mode_combo.itemText(0), "UEFI (GPT)")
        self.assertEqual(window.boot_mode_combo.itemText(1), "Legacy BIOS (MBR)")
        self.assertFalse(window.boot_mode_combo.isEnabled())
        self.assertEqual(window.selected_worker_mode(), "raw")

    def test_selector_is_active_only_for_a_recognised_windows_iso(self):
        window = self.make_window()
        window.select_mode("windows")
        self.assertFalse(window.boot_mode_combo.isEnabled())
        self.select_image(window, self.make_image("linux.iso"), False)
        self.assertFalse(window.boot_mode_combo.isEnabled())
        self.select_image(window, self.make_image("win.iso"), True)
        self.assertTrue(window.boot_mode_combo.isEnabled())

    def test_leaving_the_windows_iso_resets_the_selector_to_uefi(self):
        window = self.make_window()
        window.select_mode("windows")
        self.select_image(window, self.make_image("win.iso"), True)
        window.boot_mode_combo.setCurrentIndex(1)
        self.assertEqual(window.selected_worker_mode(), "windows-bios")
        window.iso_edit.setText(str(self.make_image("other.iso")))
        self.assertFalse(window.boot_mode_combo.isEnabled())
        self.assertEqual(window.boot_mode_combo.currentData(), "uefi")
        self.assertEqual(window.selected_worker_mode(), "windows")

    def test_switching_to_raw_mode_resets_the_selector_to_uefi(self):
        window = self.make_window()
        window.select_mode("windows")
        self.select_image(window, self.make_image("win.iso"), True)
        window.boot_mode_combo.setCurrentIndex(1)
        window.select_mode("raw")
        self.assertFalse(window.boot_mode_combo.isEnabled())
        self.assertEqual(window.boot_mode_combo.currentData(), "uefi")
        window.select_mode("windows")
        self.assertEqual(window.selected_worker_mode(), "windows")

    def test_typed_path_is_inspected_once(self):
        window = self.make_window()
        window.select_mode("windows")
        image = self.make_image("win.iso")
        window.iso_edit.setText(str(image))
        with patch.object(gui, "is_windows_install_iso", return_value=True) as probe:
            window.inspect_typed_image()
            window.inspect_typed_image()
        self.assertEqual(probe.call_count, 1)
        self.assertTrue(window.boot_mode_combo.isEnabled())

    def test_legacy_item_is_disabled_with_install_hint_when_grub_is_missing(self):
        window = self.make_window(grub_available=False)
        window.select_mode("windows")
        self.select_image(window, self.make_image("win.iso"), True)
        self.assertTrue(window.boot_mode_combo.isEnabled())
        legacy = window.boot_mode_combo.model().item(1)
        self.assertFalse(legacy.isEnabled())
        self.assertTrue(window.boot_mode_combo.model().item(0).isEnabled())
        self.assertIn("sudo pacman -S grub", window.grub_hint.text())
        self.assertIn("sudo pacman -S grub", legacy.toolTip())
        self.assertEqual(window.selected_worker_mode(), "windows")

    def test_legacy_item_is_enabled_without_hint_when_grub_is_present(self):
        window = self.make_window(grub_available=True)
        self.assertTrue(window.boot_mode_combo.model().item(1).isEnabled())
        self.assertEqual(window.grub_hint.text(), "")

    def test_permanent_note_about_older_machines_is_shown(self):
        window = self.make_window()
        note = window.boot_mode_note.text()
        self.assertIn("régebbi gépekhez", note)
        self.assertIn("megtagadhatják a telepítést", note)
        self.assertFalse(window.boot_mode_note.isHidden())

    def start_and_capture(self, window, image, grub_available=True):
        wrapper = self.make_image("bootmediakit-worker")
        window.current_device = {
            "path": "/dev/sdz", "size": 16 * 1024**3, "model": "Test", "serial": "S1",
            "wwn": "", "tran": "usb", "rm": True, "maj_min": "8:240", "diskseq": "9",
            "by_id": "/dev/disk/by-id/usb-Test_S1-0:0", "partitions": [], "mounts": [],
        }
        yes = gui.QMessageBox.StandardButton.Yes
        with patch.object(gui, "PRIVILEGED_WRAPPER", wrapper), patch.object(
            gui.shutil, "which", return_value="/usr/bin/pkexec"
        ), patch.object(gui, "bios_grub_available", return_value=grub_available), patch.object(
            gui, "is_windows_install_iso", return_value=True
        ), patch.object(gui.QMessageBox, "warning", return_value=yes) as warning:
            window.start_operation()
        return warning

    def windows_iso_window(self):
        window = self.make_window()
        window.select_mode("windows")
        image = self.make_image("win.iso")
        self.select_image(window, image, True)
        return window, image

    def test_uefi_boot_mode_passes_the_windows_worker_mode(self):
        window, image = self.windows_iso_window()
        warning = self.start_and_capture(window, image)
        args = window.process.arguments()
        self.assertEqual(args[1:4], ["windows", str(image.resolve()), "/dev/disk/by-id/usb-Test_S1-0:0"])
        self.assertEqual(args[4], "0")
        details = warning.call_args_list[0].args[2]
        self.assertIn("indítási mód: UEFI (GPT)", details)
        self.assertNotIn("Legacy", details)
        self.assertFalse(window.boot_mode_combo.isEnabled())

    def test_legacy_boot_mode_passes_windows_bios_and_warns_about_uefi(self):
        window, image = self.windows_iso_window()
        window.boot_mode_combo.setCurrentIndex(1)
        window.verify_checkbox.setChecked(True)
        warning = self.start_and_capture(window, image)
        args = window.process.arguments()
        self.assertEqual(args[1:5], ["windows-bios", str(image.resolve()), "/dev/disk/by-id/usb-Test_S1-0:0", "1"])
        details = warning.call_args_list[0].args[2]
        self.assertIn("indítási mód: Legacy BIOS (MBR)", details)
        self.assertIn("UEFI módban NEM", details)

    def test_legacy_start_is_refused_when_grub_disappeared(self):
        window, image = self.windows_iso_window()
        window.boot_mode_combo.setCurrentIndex(1)
        warning = self.start_and_capture(window, image, grub_available=False)
        self.assertIsNone(window.process)
        self.assertEqual(warning.call_args.args[1], "Hiányzó GRUB")
        self.assertIn("sudo pacman -S grub", warning.call_args.args[2])

    def test_raw_mode_still_passes_the_raw_worker_mode(self):
        window = self.make_window()
        image = self.make_image("linux.img")
        self.select_image(window, image, False)
        self.start_and_capture(window, image)
        self.assertEqual(window.process.arguments()[1], "raw")

    def test_finished_operation_restores_the_selector_state(self):
        window, image = self.windows_iso_window()
        window.boot_mode_combo.setCurrentIndex(1)
        self.start_and_capture(window, image)
        self.assertFalse(window.boot_mode_combo.isEnabled())
        window.set_busy(False)
        self.assertTrue(window.boot_mode_combo.isEnabled())
        self.assertEqual(window.selected_worker_mode(), "windows-bios")


if __name__ == "__main__":
    unittest.main()
