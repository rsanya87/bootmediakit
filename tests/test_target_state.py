"""What the GUI says about the target when the worker ends (offscreen, no root).

Fail-closed (docs/INVARIANTS.md B3): "not modified" only when the worker
reported its end with a closing event (cancelled or failed, carrying the
final target_modified) and exited normally, or never started. Any other
end is "unknown, may be partial". The worker's event order is taken from
the writer fingerprint golden files (read only): the worker is made to die
after every event of the six writer runs, also during the wipefs step,
where the RAW writer's last event still says target_modified false.
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="bmk-test-config-"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QMessageBox

import app as gui

GOLDEN = ROOT / "tests" / "fixtures" / "writer_fingerprints"
MESSAGES = ROOT / "docs" / "MESSAGES.md"
GUI_ROW = re.compile(r"^\| `(gui\.[a-z0-9_.]+)` \| (.+?) \| (.+?) \|$")
# Sentences that claim the target was not changed.
UNCHANGED_CLAIMS = ("nem módosította", "nem nyúltunk", "nem nyúltam", "módosítása előtt")
CRASH = QProcess.ExitStatus.CrashExit
NORMAL = QProcess.ExitStatus.NormalExit


def golden_events(name):
    events = []
    for line in (GOLDEN / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if "emit" in record:
            events.append(record["emit"])
    return events


class FailClosedTargetStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialogs = []
        for name in ("critical", "information", "warning"):
            patcher = patch.object(QMessageBox, name, staticmethod(lambda *a, **k: self.dialogs.append(a[2])))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(QProcess, "start")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.window = gui.MainWindow()
        self.window.refresh_timer.stop()
        self.window.lsblk_timeout_timer.stop()
        self.window.refresh_devices = lambda *a, **k: None
        self.addCleanup(self.window.deleteLater)

    def finish(self, events, exit_code, exit_status):
        """Feed the events as the worker would, then end the process."""
        window = self.window
        window.output_buffer = ""
        window._worker_started = False
        window._target_modified = False
        window._operation_cancelled = False
        window._final_event_received = False
        window._close_after_operation = False
        window.process = None
        window.log.clear()
        self.dialogs.clear()
        for event in events:
            window.handle_worker_line(json.dumps(event))
        before = window.log.toPlainText()
        window.operation_finished(exit_code, exit_status)
        added = window.log.toPlainText()[len(before):]
        return "\n".join([added, window.status_label.text(), *self.dialogs])

    def assert_fail_closed(self, shown, context):
        for claim in UNCHANGED_CLAIMS:
            self.assertNotIn(claim, shown, msg=context)
        self.assertIn(gui.gui_text("gui.result.target_unknown"), shown, msg=context)

    def test_worker_death_after_every_event_of_every_writer(self):
        ends = ((2, CRASH), (9, CRASH), (15, CRASH), (1, NORMAL), (130, NORMAL))
        for name in sorted(path.stem for path in GOLDEN.glob("*.jsonl")):
            events = golden_events(name)
            self.assertTrue(events[0].get("worker_started"), msg=name)
            # Not the last event: after it the worker exits 0 (success).
            for cut in range(1, len(events)):
                for exit_code, exit_status in ends:
                    with self.subTest(writer=name, after_event=cut, exit=(exit_code, exit_status.name)):
                        shown = self.finish(events[:cut], exit_code, exit_status)
                        self.assert_fail_closed(shown, f"{name} {cut} {exit_code} {exit_status.name}: {shown}")
                        self.assertEqual(self.window._last_target_state, "unknown")

    def test_death_during_raw_wipefs_is_not_reported_as_untouched(self):
        # The RAW writer's wiping event goes out before TARGET_MODIFIED is set.
        events = golden_events("raw_verify")
        wiping = next(i for i, e in enumerate(events) if e["message"].startswith("Régi partíciós"))
        self.assertFalse(events[wiping]["target_modified"])
        shown = self.finish(events[: wiping + 1], 2, CRASH)
        self.assert_fail_closed(shown, shown)

    def test_closing_events_are_trusted(self):
        started = golden_events("raw_verify")[:1]
        cancelled_early = {"message": "A művelet biztonságosan megszakítva.", "error": "x", "cancelled": True,
                           "log": "…", "target_modified": False}
        shown = self.finish(started + [cancelled_early], 130, NORMAL)
        self.assertIn("módosítása előtt", shown)
        self.assertEqual(self.window._last_target_state, "not_modified")

        cancelled_late = dict(cancelled_early, target_modified=True)
        shown = self.finish(started + [cancelled_late], 130, NORMAL)
        self.assertIn("részleges állapotban maradhat", shown)
        self.assertEqual(self.window._last_target_state, "modified")

        failed_early = {"message": "A művelet megszakadt.", "error": "x", "log": "…", "target_modified": False}
        shown = self.finish(started + [failed_early], 1, NORMAL)
        self.assertIn("A célmeghajtó tartalmát a worker nem módosította.", shown)
        self.assertEqual(self.window._last_target_state, "not_modified")

        failed_late = dict(failed_early, target_modified=True)
        shown = self.finish(started + [failed_late], 1, NORMAL)
        self.assertIn("részleges lehet", shown)

        # A closing event, then a crash: the end is not regular.
        shown = self.finish(started + [failed_early], 9, CRASH)
        self.assert_fail_closed(shown, shown)

    def test_worker_that_never_started(self):
        for exit_code, exit_status in ((126, NORMAL), (127, NORMAL), (2, CRASH)):
            with self.subTest(exit=exit_code):
                shown = self.finish([], exit_code, exit_status)
                self.assertNotIn(gui.gui_text("gui.result.target_unknown"), shown)
                self.assertEqual(self.window._last_target_state, "untouched")

    def test_success(self):
        events = golden_events("raw_verify")
        shown = self.finish(events, 0, NORMAL)
        self.assertIn("Sikeres befejezés.", shown)
        self.assertEqual(self.window._last_target_state, "complete")


class GuiTextIdentifierTests(unittest.TestCase):
    def documented(self):
        table = {}
        for line in MESSAGES.read_text(encoding="utf-8").splitlines():
            match = GUI_ROW.match(line)
            if match:
                self.assertNotIn(match.group(1), table)
                table[match.group(1)] = match.group(2)
        return table

    def used(self):
        """Identifiers referred to in app.py outside gui_text() itself."""
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        start = source.index("def gui_text(")
        end = source.index("\ndef ", start + 1)
        return set(re.findall(r'"(gui\.[a-z0-9_.]+)"', source[:start] + source[end:]))

    def test_table_and_code_match(self):
        QApplication.instance() or QApplication([])
        table = self.documented()
        self.assertTrue(table)
        self.assertEqual(self.used(), set(table))
        for msg_id, text in table.items():
            with self.subTest(msg_id=msg_id):
                self.assertEqual(gui.gui_text(msg_id), text)


if __name__ == "__main__":
    unittest.main()
