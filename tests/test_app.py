import os
import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()
