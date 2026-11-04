import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

import app as gui


class GuiStabilitySmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def make_window(self):
        start_patch = patch.object(QProcess, "start")
        start_patch.start()
        self.addCleanup(start_patch.stop)
        window = gui.MainWindow()
        self.addCleanup(window.refresh_timer.stop)
        self.addCleanup(window.lsblk_timeout_timer.stop)
        self.addCleanup(window.close)
        return window, start_patch

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


if __name__ == "__main__":
    unittest.main()
