"""Desktop integration and polkit failure handling (T4, desktop integration work).

Proof level: unit/offscreen GUI. pkexec is never run; its exit codes are
simulated. Whether the window, taskbar, menu and switcher show the icon, and
how a session without an authentication agent behaves, is the maintainer's
physical check.
"""

import configparser
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="bmk-test-config-")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QProcess
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

import app as gui

# The polkit action, the root wrapper and the worker path checks must not
# change (docs/INVARIANTS.md B2). These are the files of the last release
# (unchanged since 0.3); a change needs
# a security review and the maintainer's approval.
FROZEN_PRIVILEGED_FILES = {
    "org.bootmediakit.policy": "a229bbeecfd905db8b735290bbfebefbd4a575d460dd82d36b6db1278bc04bae",
    "bootmediakit-worker": "55ff8459047ffd2782002517fde652c499dadb61453d8eb2827280ebd9806023",
}


class PrivilegeFailureMessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def make_window(self):
        patcher = patch.object(QProcess, "start")
        self.start_mock = patcher.start()
        self.addCleanup(patcher.stop)
        window = gui.MainWindow()

        def dispose():
            if isValid(window):
                window.process = None
                window.close()
                window.refresh_timer.stop()
                window.lsblk_timeout_timer.stop()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                QApplication.processEvents()

        self.addCleanup(dispose)
        return window

    def finish_before_worker_start(self, exit_code):
        window = self.make_window()
        window._worker_started = False
        window._operation_cancelled = False
        starts_before = self.start_mock.call_count
        with patch.object(gui.QMessageBox, "critical") as critical, patch.object(
            gui.QMessageBox, "information"
        ) as information:
            window.operation_finished(exit_code, QProcess.ExitStatus.NormalExit)
        # Only the quiet device refresh may start a process; never sudo or an agent.
        for call in self.start_mock.call_args_list[starts_before:]:
            self.assertEqual(call.args[0], "lsblk")
        return window, critical, information

    def test_missing_agent_or_denied_authorization_gives_an_actionable_error(self):
        window, critical, information = self.finish_before_worker_start(127)
        information.assert_not_called()
        critical.assert_called_once()
        _parent, title, text = critical.call_args.args
        self.assertEqual(title, "A hitelesítés nem sikerült")
        for phrase in (
            "pkexec kilépési kód: 127",
            "A célmeghajtóhoz nem nyúltunk.",
            "nem fut polkit hitelesítési ügynök",
            "A jelszó hibás volt",
            "A polkit szolgáltatás nem fut.",
            "Mit tegyél:",
            "nem indít saját ügynököt, és nem használ sudo-t",
        ):
            self.assertIn(phrase, text)
        self.assertIn("Nem sikerült rendszergazdai jogosultságot kapni", window.status_label.text())
        self.assertEqual(window.status_label.property("state"), "error")
        self.assertIn("A pkexec kilépési kódja: 127", window.log.toPlainText())

    def test_dismissed_dialog_is_reported_as_cancelled_by_the_user(self):
        window, critical, information = self.finish_before_worker_start(126)
        critical.assert_not_called()
        information.assert_called_once()
        _parent, title, text = information.call_args.args
        self.assertEqual(title, "A hitelesítés megszakítva")
        self.assertIn("bezártad vagy megszakítottad", text)
        self.assertIn("A célmeghajtóhoz nem nyúltunk.", text)
        self.assertEqual(window.status_label.property("state"), "warning")

    def test_other_start_failures_keep_the_previous_message(self):
        window, critical, information = self.finish_before_worker_start(1)
        critical.assert_not_called()
        _parent, title, text = information.call_args.args
        self.assertEqual(title, "A művelet nem indult el")
        self.assertIn("A célmeghajtóhoz nem nyúltunk.", text)
        self.assertEqual(window.status_label.text(), "A jogosultságkérés vagy a worker indítása nem sikerült.")

    def test_exit_codes_match_the_pkexec_manual(self):
        self.assertEqual((gui.PKEXEC_DISMISSED, gui.PKEXEC_NOT_AUTHORIZED), (126, 127))


class NoPrivilegeFallbackTests(unittest.TestCase):
    def test_gui_runs_only_pkexec_with_the_fixed_wrapper_and_lsblk(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"setProgram\(([^)]*)\)", source), ['"/usr/bin/pkexec"'])
        self.assertEqual(re.findall(r"[\"'](?:sudo|su|doas|run0)[\"']", source), [])
        # The only synchronous subprocess is run_lsblk() (read-only lsblk).
        self.assertEqual(re.findall(r"subprocess\.(?:Popen|call|check_call|check_output)\(", source), [])
        self.assertEqual(len(re.findall(r"subprocess\.run\(", source)), 1)
        self.assertIn('def run_lsblk()', source)
        self.assertRegex(source, r'command = \[\s*"lsblk"')
        for agent in ("polkit-kde-authentication-agent", "polkit-gnome-authentication-agent",
                      "lxpolkit", "lxqt-policykit-agent", "polkit-mate-authentication-agent"):
            self.assertNotIn(agent, source)
        self.assertNotIn("--disable-internal-agent", source)

    def test_polkit_action_and_wrapper_are_unchanged(self):
        for name, digest in FROZEN_PRIVILEGED_FILES.items():
            actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            self.assertEqual(actual, digest, msg=f"{name} megváltozott (INVARIANTS B2): biztonsági felülvizsgálat kell")

    def test_readmes_and_installer_explain_the_agent_without_a_single_desktop(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        hungarian = (ROOT / "README.hu.md").read_text(encoding="utf-8")
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("polkit authentication agent", english)
        self.assertIn("never falls back to `sudo`", english)
        self.assertIn("polkit hitelesítési ügynök", hungarian)
        self.assertIn("soha nem tér át `sudo`-ra", hungarian)
        self.assertIn("polkit hitelesítési ügynök", installer)
        self.assertNotIn("KDE users need", english)
        self.assertNotIn("KDE alatt aktív polkit", hungarian)


class DesktopEntryTests(unittest.TestCase):
    def entry(self):
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str
        parser.read(ROOT / "bootmediakit.desktop", encoding="utf-8")
        return parser["Desktop Entry"]

    def test_standard_keys_only(self):
        entry = self.entry()
        self.assertEqual(entry["Type"], "Application")
        self.assertEqual(entry["Name"], "BootMediaKit")
        self.assertEqual(entry["Exec"], "bootmediakit")
        self.assertEqual(entry["Icon"], "bootmediakit")
        self.assertEqual(entry["Terminal"], "false")
        self.assertTrue(entry["Categories"].endswith(";"))
        for key in entry:
            self.assertNotRegex(key, r"^(X-KDE|X-GNOME|X-Cinnamon|X-MATE|X-XFCE|OnlyShowIn|NotShowIn)", msg=key)

    def test_window_class_and_icon_match_the_application(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('app.setDesktopFileName("bootmediakit")', source)
        self.assertEqual(self.entry()["StartupWMClass"], "bootmediakit")
        self.assertTrue((ROOT / "bootmediakit.svg").is_file())
        self.assertIn('APP_ICON = Path(__file__).with_name("bootmediakit.svg")', source)

    def test_ci_installs_the_desktop_file_validator(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        self.assertIn("desktop-file-utils", workflow)

    @unittest.skipUnless(shutil.which("desktop-file-validate"), "desktop-file-validate nincs telepítve")
    def test_desktop_file_validate_reports_no_error(self):
        result = subprocess.run(
            ["desktop-file-validate", str(ROOT / "bootmediakit.desktop")],
            capture_output=True, text=True, env=dict(os.environ, LC_ALL="C"), timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertNotIn("error:", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
