from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import version


class PrivilegedPackagingTests(unittest.TestCase):
    def test_polkit_action_is_scoped_to_the_fixed_worker_wrapper(self):
        policy = ET.parse(ROOT / "org.bootmediakit.policy").getroot()
        action = policy.find("./action[@id='org.bootmediakit.write']")
        self.assertIsNotNone(action)
        assert action is not None
        annotation = action.find("./annotate[@key='org.freedesktop.policykit.exec.path']")
        self.assertIsNotNone(annotation)
        assert annotation is not None
        self.assertEqual(
            annotation.text,
            "/usr/libexec/bootmediakit/bootmediakit-worker",
        )
        defaults = action.find("./defaults")
        self.assertIsNotNone(defaults)
        assert defaults is not None
        self.assertEqual(defaults.findtext("allow_any"), "no")
        self.assertEqual(defaults.findtext("allow_active"), "auth_admin")

    def test_root_wrapper_uses_isolated_python_and_installed_worker(self):
        wrapper = (ROOT / "bootmediakit-worker").read_text(encoding="utf-8")
        self.assertIn("/usr/bin/python3 -I /usr/lib/bootmediakit/worker.py", wrapper)
        self.assertNotIn("python3 " + str(ROOT), wrapper)

    def test_installer_places_wrapper_and_policy_in_root_owned_paths(self):
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('install -o root -g root -m 0755 "$SCRIPT_DIR/bootmediakit-worker" "$WRAPPER_PATH"', installer)
        self.assertIn('install -o root -g root -m 0644 "$SCRIPT_DIR/org.bootmediakit.policy" "$POLICY_PATH"', installer)
        self.assertIn('chown -R root:root "$APP_DIR"', installer)
        self.assertIn('chmod -R go-w "$APP_DIR"', installer)

    def test_gui_invokes_the_dedicated_polkit_wrapper_not_python_worker(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('PRIVILEGED_WRAPPER = Path("/usr/libexec/bootmediakit/bootmediakit-worker")', app)
        self.assertIn('self.process.setProgram("/usr/bin/pkexec")', app)
        self.assertNotIn('args = ["/usr/bin/python3", str(WORKER)', app)

    def test_worker_refuses_direct_checkout_or_missing_polkit_context(self):
        worker = (ROOT / "worker.py").read_text(encoding="utf-8")
        self.assertIn('expected_worker = Path("/usr/lib/bootmediakit/worker.py")', worker)
        self.assertIn('expected_wrapper = Path("/usr/libexec/bootmediakit/bootmediakit-worker")', worker)
        self.assertIn('os.environ.get("PKEXEC_UID", "")', worker)
        self.assertIn("Forráskönyvtárból történő közvetlen root indítás tiltott.", worker)

    def test_device_summary_is_compact_and_partition_list_is_in_hover_info_tooltip(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('self.partition_info_label = QLabel("Partíció információk:")', app)
        self.assertIn('self.partition_info_button.setText("i")', app)
        self.assertIn("self.partition_info_button.setToolTip(tooltip)", app)
        self.assertIn("self.partition_info_button.setToolTipDuration(15000)", app)
        self.assertIn('summary = f"Kapacitás: {capacity} • Azonosító: {serial} • Eszköz: {model}"', app)
        self.assertIn('f"Fájlrendszer: {fs}<br>"', app)
        self.assertIn('f"Címke: {label}<br>"', app)
        self.assertIn('f"Méret: {size}<br>"', app)
        self.assertIn('f"Csatolás: {mount_text}"', app)
        self.assertIn("import html", app)
        self.assertIn("html.escape(str(part.get", app)
        self.assertNotIn('lines.append(\n                f"{part.get(\'path\')}', app)

    def test_elapsed_timer_cannot_expand_progress_header_vertically(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("self.elapsed_label.setFixedHeight(30)", app)
        self.assertIn("QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed", app)
        self.assertIn("QLabel#elapsed", app)
        self.assertIn("QToolButton#infoButton", app)

    def test_gui_displays_safety_version_under_title_with_readable_secondary_text(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("from version import __version__", app)
        self.assertIn("APP_VERSION = __version__", app)
        self.assertIn("version = QLabel(APP_VERSION)", app)
        self.assertIn('meta_row.addWidget(version', app)
        self.assertIn('QLabel#version { color: #83bde2;', app)
        self.assertIn('QLabel#muted { color: #b7c1cb; }', app)

    def test_gui_disables_horizontal_scrollbar_and_wraps_long_iso_metadata(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("self.file_info.setWordWrap(False)", app)
        self.assertIn("self.file_info.setSizePolicy(QSizePolicy.Policy.Ignored", app)
        self.assertIn("Qt.ScrollBarPolicy.ScrollBarAlwaysOff", app)
        self.assertIn("root.setSizePolicy(QSizePolicy.Policy.Ignored", app)
        self.assertIn("calculate_window_profile(", app)
        self.assertIn("self._compact_ui = available_height < 850", app)
        self.assertIn("self.setMaximumSize(740, 900)", app)
        self.assertIn("def fit_window_to_screen(self)", app)
        self.assertIn("QTimer.singleShot(0, window.fit_window_to_screen)", app)
        self.assertIn("self.log.setMaximumHeight(56 if self._compact_ui else 76)", app)
        self.assertIn("self.file_info.setWordWrap(False)", app)


class SingleVersionSourceTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def first_heading(self, relative: str, *, skip: tuple[str, ...] = ()) -> str:
        for line in self.read(relative).splitlines():
            if line.startswith("## ") and line[3:].strip() not in skip:
                return line
        self.fail(f"{relative}: nincs '## ' szakaszcím")

    def test_version_module_is_a_single_assignment_of_a_semantic_version(self):
        text = self.read("version.py")
        self.assertRegex(text, r'\A__version__ = "\d+\.\d+\.\d+"\n\Z')
        self.assertEqual(text, f'__version__ = "{version.__version__}"\n')

    def test_gui_and_fetcher_read_the_version_module(self):
        self.assertIn("APP_VERSION = __version__", self.read("app.py"))
        fetcher = self.read("fetch_uefi_ntfs.py")
        self.assertIn("from version import __version__", fetcher)
        self.assertIn('"User-Agent": f"BootMediaKit/{__version__}"', fetcher)

    def test_installer_installs_the_version_module_next_to_the_app(self):
        self.assertIn(
            'install -m 0644 "$SCRIPT_DIR/version.py" "$APP_DIR/version.py"',
            self.read("install.sh"),
        )

    def test_installer_installs_every_module_the_gui_imports(self):
        installer = self.read("install.sh")
        local_modules = {path.stem for path in ROOT.glob("*.py")}
        imported = set(
            re.findall(r"^(?:from|import) (\w+)", self.read("app.py"), flags=re.MULTILINE)
        )
        for module in sorted(imported & local_modules):
            self.assertIn(
                f'"$SCRIPT_DIR/{module}.py" "$APP_DIR/{module}.py"', installer,
                msg=f"az install.sh nem telepíti: {module}.py",
            )

    def test_privileged_worker_does_not_import_the_version_module(self):
        worker = self.read("worker.py")
        self.assertNotRegex(worker, r"(?m)^\s*(from|import)\s+version\b")

    def test_documents_state_the_current_version(self):
        current = version.__version__
        self.assertRegex(
            self.read("README.md"), rf"(?m)^\*\*Version:\*\* `{re.escape(current)}`"
        )
        self.assertRegex(
            self.read("README.hu.md"), rf"(?m)^\*\*Verzió:\*\* `{re.escape(current)}`"
        )
        # During development CHANGELOG.md starts with "## Unreleased"; the
        # topmost released section must then match the current version.
        self.assertIn(current, self.first_heading("CHANGELOG.md", skip=("Unreleased",)))
        self.assertIn(current, self.first_heading("docs/TESTING.md"))

    def test_no_other_python_file_hardcodes_the_version(self):
        current = version.__version__
        offenders = [
            str(path.relative_to(ROOT))
            for path in sorted(ROOT.rglob("*.py"))
            if path.name != "version.py"
            and re.search(rf"(?<![\d.]){re.escape(current)}(?![\d.])", path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [], msg="kódolt verziószöveg a version.py-n kívül")


class TestCommandDocumentationTests(unittest.TestCase):
    COMPILE = "-m py_compile app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py version.py"
    SHELL_SYNTAX = "bash -n install.sh uninstall.sh bootmediakit-worker"
    UNIT = "QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v"
    SHELLCHECK = "shellcheck -S warning install.sh uninstall.sh bootmediakit-worker"
    INTEGRATION = (
        "sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen "
        "python3 -m unittest discover -s tests/integration -v"
    )
    DOCUMENTS = ("README.md", "README.hu.md", "CONTRIBUTING.md", "docs/TESTING.md")

    def test_documented_test_commands_match_ci(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        for command in (self.COMPILE, self.SHELL_SYNTAX, self.SHELLCHECK, self.INTEGRATION):
            self.assertIn(command, workflow)
        self.assertIn("unittest discover -s tests -v", workflow)
        self.assertIn("QT_QPA_PLATFORM: offscreen", workflow)
        for document in self.DOCUMENTS:
            text = (ROOT / document).read_text(encoding="utf-8")
            for command in (
                "python3 " + self.COMPILE, self.SHELL_SYNTAX, self.UNIT,
                self.SHELLCHECK, self.INTEGRATION,
            ):
                self.assertIn(command, text, msg=f"{document}: hiányzik: {command}")
            self.assertIn("PySide6", text)

    def test_compile_command_lists_every_application_module(self):
        listed = set(self.COMPILE.split()[2:])
        self.assertEqual(listed, {path.name for path in ROOT.glob("*.py")})

    def test_ci_cannot_pass_the_integration_step_by_skipping(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        self.assertIn('BMK_INTEGRATION_REQUIRED: "1"', workflow)

    def test_integration_tests_are_opt_in_and_never_run_for_non_root(self):
        helper = (ROOT / "tests/integration/loop_helpers.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("BMK_INTEGRATION") != "1"', helper)
        self.assertIn("os.geteuid() != 0", helper)
        self.assertIn("unittest.SkipTest", helper)
        for program in ("losetup", "sfdisk", "wipefs", "mkfs.ext4", "mkfs.ntfs", "fatlabel"):
            self.assertIn(f'"{program}"', helper)

    def test_loop_stand_in_exists_only_in_the_test_helper(self):
        for name in ("worker.py", "app.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("BMK_INTEGRATION", text)
            self.assertNotIn('"loop"', text)


class SafetyDocumentationTests(unittest.TestCase):
    def test_both_readmes_document_the_partially_written_state(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        hungarian = (ROOT / "README.hu.md").read_text(encoding="utf-8")
        self.assertIn("may be left partially written", english)
        self.assertIn("részlegesen írt állapotban maradhat", hungarian)


if __name__ == "__main__":
    unittest.main()
