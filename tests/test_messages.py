"""Stable message identifiers on the worker's events (T6).

Proof level: AST scan of worker.py, unit tests of emit(), the six writer
runs of the fingerprint tests (fake runner, no device, no root) and an
offscreen GUI check.
"""

import ast
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="bmk-test-config-")
ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
for path in (str(ROOT), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import worker
import test_writer_fingerprint as fp

MESSAGES = ROOT / "docs" / "MESSAGES.md"
ROW = re.compile(r"^\| `(worker\.[a-z0-9_.]+)` \| (.+?) \| (.+?) \| (.+?) \|$")
ARG = re.compile(r"`([a-z_]+)` \((int|str)\)")
OLD_FIELDS = {"message", "log", "error", "percent", "target_modified", "worker_started", "cancelled"}


def documented():
    """msg_id -> (message template, {arg: type})."""
    table = {}
    for line in MESSAGES.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if not match:
            continue
        msg_id, message, args, _where = match.groups()
        if msg_id in table:
            raise AssertionError(f"kétszer dokumentált azonosító: {msg_id}")
        table[msg_id] = (message, dict(ARG.findall(args)) if args != "none" else {})
    return table


def template_of(node):
    """A message argument as text with ``{}`` for every inserted value."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in node.values)
    raise AssertionError(f"nem várt üzenetforma: {ast.dump(node)}")


def emit_calls():
    """(line, msg_id, message template, msg_args names or None) per id."""
    tree = ast.parse((ROOT / "worker.py").read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "emit"):
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        msg_id = keywords.get("msg_id")
        args_node = keywords.get("msg_args")
        if args_node is None:
            names = None
        else:
            assert isinstance(args_node, ast.Dict), f"worker.py:{node.lineno}: msg_args nem szótár-literál"
            names = {key.value for key in args_node.keys}
        message = node.args[0]
        if isinstance(msg_id, ast.IfExp):
            # emit("A" if c else "B", msg_id="a" if c else "b"): pair the branches.
            assert isinstance(message, ast.IfExp) and ast.dump(message.test) == ast.dump(msg_id.test), (
                f"worker.py:{node.lineno}: feltételes msg_id csak azonos feltételű üzenettel"
            )
            pairs = [(msg_id.body, message.body), (msg_id.orelse, message.orelse)]
        else:
            pairs = [(msg_id, message)]
        for id_node, message_node in pairs:
            literal = isinstance(id_node, ast.Constant) and isinstance(id_node.value, str)
            calls.append((node.lineno, id_node.value if literal else None, template_of(message_node), names))
    return calls


def doc_template(message):
    return re.sub(r"\{[a-z_]+\}", "{}", message)


def render(message, args):
    """The documented message with the argument values as the worker shows them."""
    def value(match):
        item = args[match.group(1)]
        return f"{item:,}" if isinstance(item, int) and not isinstance(item, bool) else str(item)
    return re.sub(r"\{([a-z_]+)\}", value, message)


class MessageSourceTests(unittest.TestCase):
    def test_every_emit_call_has_a_documented_literal_msg_id(self):
        table = documented()
        calls = emit_calls()
        self.assertGreaterEqual(len(calls), 40)
        for line, msg_id, _template, _names in calls:
            with self.subTest(line=line):
                self.assertIsNotNone(msg_id, msg=f"worker.py:{line}: hiányzó vagy nem literál msg_id")
                self.assertIn(msg_id, table, msg=f"worker.py:{line}: nincs a docs/MESSAGES.md-ben: {msg_id}")

    def test_documentation_lists_only_used_identifiers(self):
        used = {msg_id for _line, msg_id, _template, _names in emit_calls()}
        self.assertEqual(set(documented()) - used, set())

    def test_one_identifier_means_one_message_and_its_documented_arguments(self):
        table = documented()
        for line, msg_id, template, names in emit_calls():
            with self.subTest(line=line, msg_id=msg_id):
                message, args = table[msg_id]
                self.assertEqual(template, doc_template(message))
                self.assertEqual(names or set(), set(args))
        templates = [doc_template(message) for message, _args in table.values()]
        self.assertEqual(len(templates), len(set(templates)), msg="két azonosító ugyanarra az üzenetre")

    def test_identifiers_are_dotted_lowercase_names(self):
        for msg_id in documented():
            self.assertRegex(msg_id, r"^worker(\.[a-z0-9_]+){1,3}$")

    def test_worker_stays_standard_library_only(self):
        tree = ast.parse((ROOT / "worker.py").read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module.split(".")[0])
        self.assertEqual(modules - set(sys.stdlib_module_names), set())


class EmitTests(unittest.TestCase):
    def capture(self, *args, **kwargs):
        stream = io.StringIO()
        with patch.object(worker.sys, "stdout", stream), patch.object(worker, "TARGET_MODIFIED", False):
            self.assertTrue(worker.emit(*args, **kwargs))
        return stream.getvalue()

    def test_old_calls_print_exactly_what_they_printed_before(self):
        self.assertEqual(
            self.capture("Lemezkép kiírása…", 3),
            '{"message": "Lemezkép kiírása…", "target_modified": false, "percent": 3}\n',
        )
        self.assertEqual(
            self.capture("A művelet megszakadt.", error="hiba", log="napló"),
            '{"message": "A művelet megszakadt.", "target_modified": false, "log": "napló", "error": "hiba"}\n',
        )

    def test_new_fields_are_appended_after_the_old_ones(self):
        line = self.capture(
            "Ellenőrzés… 1,024 / 2,048 bájt",
            50,
            msg_id="worker.raw.verify_progress",
            msg_args={"done_bytes": 1024, "total_bytes": 2048},
        )
        self.assertEqual(
            line,
            '{"message": "Ellenőrzés… 1,024 / 2,048 bájt", "target_modified": false, "percent": 50, '
            '"msg_id": "worker.raw.verify_progress", "msg_args": {"done_bytes": 1024, "total_bytes": 2048}}\n',
        )
        event = json.loads(line)
        self.assertEqual(set(event) - OLD_FIELDS, {"msg_id", "msg_args"})

    def test_non_json_argument_values_are_sent_as_text(self):
        event = json.loads(self.capture("x", msg_id="worker.started", msg_args={
            "path": Path("/tmp/a b.iso"), "flag": True, "none": None, "size": 3,
        }))
        self.assertEqual(event["msg_args"], {"path": "/tmp/a b.iso", "flag": True, "none": None, "size": 3})

    def test_msg_args_only_when_given(self):
        event = json.loads(self.capture("x", msg_id="worker.started"))
        self.assertEqual(event["msg_id"], "worker.started")
        self.assertNotIn("msg_args", event)


class WriterMessageTests(fp.FakeSystemTestCase):
    """The identifiers and arguments of every event in the writer runs."""

    def assert_events_documented(self, system):
        table = documented()
        self.assertTrue(system.full_events)
        for event in system.full_events:
            with self.subTest(event=event.get("msg_id")):
                self.assertIn(event.get("msg_id"), table, msg=event)
                message, arg_types = table[event["msg_id"]]
                args = event.get("msg_args", {})
                self.assertEqual(set(args), set(arg_types))
                for name, kind in arg_types.items():
                    self.assertIsInstance(args[name], {"int": int, "str": str}[kind], msg=name)
                    shown = f"{args[name]:,}" if kind == "int" else args[name]
                    self.assertIn(shown, event["message"] + "\n" + event.get("log", ""), msg=name)
                self.assertEqual(event["message"], render(message, args))
        # The golden timeline holds the same events without the new fields.
        self.assertEqual(
            [{key: value for key, value in event.items() if key in OLD_FIELDS} for event in system.full_events],
            system.events(),
        )

    def test_all_writer_runs(self):
        seen = set()
        for name, mode, verify in fp.WriterFingerprintTests.CASES:
            with self.subTest(name=name):
                system = self.make_system()
                code = system.run(mode, self.source_for(system, mode), verify=verify)
                self.assertEqual(code, 0)
                self.assert_events_documented(system)
                seen.update(event["msg_id"] for event in system.full_events)
        for expected in ("worker.started", "worker.raw.write_progress", "worker.raw.done",
                         "worker.raw.done_verified", "worker.copy.progress", "worker.windows.uefi.done",
                         "worker.windows.bios.done", "worker.windows.verify.progress"):
            self.assertIn(expected, seen)

    def test_cancel_and_failure_events(self):
        system = self.make_system()
        fired = []

        def on_step(step):
            if not fired and step.get("call") == "unmount_disk":
                fired.append(step)
                worker.CANCEL_EVENT.set()

        system.on_step = on_step
        self.assertEqual(system.run("raw", self.source_for(system, "raw"), verify=True), 130)
        self.assert_events_documented(system)
        self.assertEqual(system.full_events[-1]["msg_id"], "worker.cancelled")

        system = self.make_system()
        self.assertEqual(system.run("raw", system.source_dir / "missing.iso", verify=True), 1)
        self.assert_events_documented(system)
        self.assertEqual(system.full_events[-1]["msg_id"], "worker.failed")

    def test_golden_files_have_no_identifier_fields(self):
        for path in sorted(fp.GOLDEN_DIR.glob("*.jsonl")):
            with self.subTest(golden=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("msg_id", text)
                self.assertNotIn("msg_args", text)


class GuiIgnoresIdentifierTests(unittest.TestCase):
    def test_gui_shows_the_same_with_and_without_the_new_fields(self):
        from PySide6.QtCore import QEvent, QProcess
        from PySide6.QtWidgets import QApplication
        from shiboken6 import isValid

        import app as gui

        QApplication.instance() or QApplication([])
        events = [
            {"message": "A BootMediaKit biztonságos háttérfolyamata elindult.", "target_modified": False,
             "percent": 0, "worker_started": True, "msg_id": "worker.started"},
            {"message": "Lemezkép kiírása… 1,024 / 2,048 bájt", "target_modified": True, "percent": 30,
             "msg_id": "worker.raw.write_progress", "msg_args": {"done_bytes": 1024, "total_bytes": 2048}},
            {"message": "A művelet megszakadt.", "target_modified": True, "error": "hiba", "log": "napló",
             "msg_id": "worker.failed"},
            {"message": "Ismeretlen esemény", "target_modified": True, "msg_id": "worker.unknown.future"},
        ]

        def shown(with_ids):
            with patch.object(QProcess, "start"):
                window = gui.MainWindow()
            window.refresh_timer.stop()
            window.lsblk_timeout_timer.stop()
            try:
                for event in events:
                    if not with_ids:
                        event = {key: value for key, value in event.items() if key in OLD_FIELDS}
                    window.handle_worker_line(json.dumps(event, ensure_ascii=False))
                return (window.status_label.text(), window.progress.value(), window.log.toPlainText(),
                        window._worker_started, window._target_modified)
            finally:
                if isValid(window):
                    window.close()
                    window.deleteLater()
                    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        with_ids = shown(True)
        self.assertEqual(with_ids, shown(False))
        self.assertIn("HIBA: hiba", with_ids[2])
        self.assertNotIn("worker.", with_ids[2])


if __name__ == "__main__":
    unittest.main()
