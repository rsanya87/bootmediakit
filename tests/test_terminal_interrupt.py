"""Ctrl+C in the terminal while the program runs (offscreen, no root, no device).

The maintainer's no-agent session (Openbox, pkexec asking for the password
in the terminal) crashed with SIGSEGV on Ctrl+C: the terminal sends SIGINT to
the GUI and to pkexec, and with Python's default handler the pending
KeyboardInterrupt crashed PySide when the QProcess.finished slot ran
(docs/LESSONS.md). Each case runs the real main() in a separate Python
process, so a crash is an exit code, not a dead test runner. pkexec is
replaced by sh, which prints a password prompt and then gets SIGINT
together with the GUI, like a terminal's process group.

Proof level: offscreen Qt with a real child process and real signals.
"""

import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Runs in the child Python process. argv: repo, case.
SCRIPT = textwrap.dedent(
    r"""
    import os, signal, subprocess, sys
    sys.path.insert(0, sys.argv[1])
    case = sys.argv[2]
    from PySide6.QtCore import QProcess, QTimer
    from PySide6.QtWidgets import QMessageBox
    import app as gui

    # No device scan and no dialogs in this test process.
    gui.MainWindow.refresh_devices = lambda self, *a, **k: None
    gui.MainWindow.refresh_devices_silently = lambda self, *a, **k: None
    QMessageBox.information = staticmethod(lambda *a, **k: print("DIALOG information", flush=True))
    QMessageBox.critical = staticmethod(lambda *a, **k: print("DIALOG critical", flush=True))
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    if case == "unprotected":  # only to show the crash without the handler
        gui.install_terminal_interrupt_handler = lambda window: None

    def start_fake_pkexec(window):
        # The same slots as the real start; sh stands in for pkexec.
        window.set_busy(True)
        window.process = QProcess(window)
        window.process.setProgram("sh")
        started = ("echo '{\"message\": \"x\", \"percent\": 0, \"target_modified\": false, "
                   "\"worker_started\": true}'; ") if case == "worker-started" else ""
        window.process.setArguments(["-c", started + "echo 'Password:' >&2; sleep 0.5; "
                                     "kill -INT $PPID; kill -INT $$; sleep 5"])
        window.process.readyReadStandardOutput.connect(window.read_stdout)
        window.process.readyReadStandardError.connect(window.read_stderr)
        window.process.finished.connect(window.operation_finished)
        window.process.errorOccurred.connect(window.process_error)
        window.process.finished.connect(lambda code, status: print("FINISHED", int(code), status.name, flush=True))
        window.process.start()
        if case == "close-too":
            QTimer.singleShot(500, window.close)

    original_show = gui.MainWindow.show

    def show(window):
        original_show(window)
        if case == "idle":
            subprocess.Popen(["sh", "-c", f"sleep 0.5; kill -INT {os.getpid()}"])
        else:
            QTimer.singleShot(0, lambda: start_fake_pkexec(window))
        QTimer.singleShot(8000, lambda: (print("TIMEOUT", flush=True), os._exit(3)))

    gui.MainWindow.show = show
    raise SystemExit(gui.main())
    """
)


class TerminalInterruptTests(unittest.TestCase):
    def run_case(self, case):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", LC_ALL="C",
                   XDG_CONFIG_HOME=tempfile.mkdtemp(prefix="bmk-test-config-"), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", SCRIPT, str(ROOT), case],
            capture_output=True, text=True, timeout=60, env=env, start_new_session=True,
        )
        return result.returncode, result.stdout + result.stderr

    def assert_clean_interrupt(self, code, output):
        self.assertNotIn("Segmentation fault", output, msg=output)
        self.assertNotIn("TIMEOUT", output, msg=output)
        self.assertNotIn("KeyboardInterrupt", output, msg=output)
        self.assertEqual(code, 130, msg=output)

    def test_ctrl_c_during_the_password_prompt(self):
        code, output = self.run_case("pkexec")
        self.assert_clean_interrupt(code, output)
        # The finished slot ran, pkexec stopped on SIGINT, no dialog opened.
        self.assertIn(f"FINISHED {int(signal.SIGINT)} CrashExit", output)
        self.assertNotIn("DIALOG", output)
        # The worker never started: the terminal line may say so.
        self.assertIn("A háttérfolyamat nem indult el, a célmeghajtóhoz nem nyúltunk.", output)

    def test_ctrl_c_after_the_worker_started(self):
        code, output = self.run_case("worker-started")
        self.assert_clean_interrupt(code, output)
        # No closing event: fail-closed, never "not changed".
        self.assertIn("BootMediaKit: megszakítva (Ctrl+C). A célmeghajtó részleges állapotban maradhat.", output)
        self.assertNotIn("nem nyúltunk", output)
        self.assertNotIn("nem módosította", output)

    def test_ctrl_c_and_closing_the_window_together(self):
        code, output = self.run_case("close-too")
        self.assert_clean_interrupt(code, output)
        self.assertIn("FINISHED", output)

    def test_ctrl_c_without_an_operation(self):
        code, output = self.run_case("idle")
        self.assert_clean_interrupt(code, output)
        self.assertNotIn("megszakítva (Ctrl+C)", output)  # no line without an operation


class TerminalInterruptPathTests(unittest.TestCase):
    """The flag is acted on from the timer, on the confirmed-close path."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="bmk-test-config-"))
        sys.path.insert(0, str(ROOT))
        from PySide6.QtWidgets import QApplication

        cls.qt_app = QApplication.instance() or QApplication([])

    def make_window(self):
        from unittest.mock import patch

        from PySide6.QtCore import QProcess

        import app as gui

        patcher = patch.object(QProcess, "start")
        patcher.start()
        self.addCleanup(patcher.stop)
        window = gui.MainWindow()
        window.refresh_timer.stop()
        window.lsblk_timeout_timer.stop()
        self.addCleanup(window.deleteLater)
        return gui, window

    def test_running_operation_uses_close_after_cancel(self):
        from unittest.mock import MagicMock

        gui, window = self.make_window()
        window.process = MagicMock()
        calls = []
        window._send_cancel_request = lambda: calls.append("cancel")
        window._interrupt_requested = True
        window.poll_terminal_interrupt()
        window.poll_terminal_interrupt()  # a second Ctrl+C or timer tick
        self.assertEqual(calls, ["cancel"])
        self.assertTrue(window._close_after_operation)
        window.process = None

    def test_terminal_line_says_no_more_than_the_state(self):
        gui, window = self.make_window()
        self.assertIsNone(window.terminal_interrupt_summary())
        window._interrupted_operation = True
        expected = {
            "untouched": "gui.interrupt.untouched",
            "not_modified": "gui.interrupt.not_modified",
            "complete": "gui.interrupt.complete",
            "modified": "gui.interrupt.partial",
            "unknown": "gui.interrupt.partial",
            "": "gui.interrupt.partial",
        }
        for state, msg_id in expected.items():
            with self.subTest(state=state):
                window._last_target_state = state
                self.assertEqual(window.terminal_interrupt_summary(), gui.gui_text(msg_id))

    def test_the_handler_only_sets_the_flag(self):
        gui, window = self.make_window()
        previous = signal.getsignal(signal.SIGINT)
        self.addCleanup(signal.signal, signal.SIGINT, previous)
        timer = gui.install_terminal_interrupt_handler(window)
        self.addCleanup(timer.stop)
        self.assertEqual(timer.interval(), gui.TERMINAL_INTERRUPT_POLL_MS)
        handler = signal.getsignal(signal.SIGINT)
        self.assertNotIn(handler, (signal.SIG_IGN, signal.SIG_DFL, signal.default_int_handler))
        handler(signal.SIGINT, None)
        self.assertTrue(window._interrupt_requested)
        self.assertFalse(window._interrupt_handled)  # nothing done in the handler


if __name__ == "__main__":
    unittest.main()
