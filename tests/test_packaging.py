from pathlib import Path
import re
import shutil
import subprocess
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

    def test_gui_only_looks_up_grub_and_leaves_grub_install_to_the_worker(self):
        # Rule 8: grub-install runs only in the worker, on the validated target.
        for name in ("app.py", "ui_helpers.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            for line in source.splitlines():
                if '"grub-install"' in line:
                    self.assertRegex(line, r'which\("grub-install"\)', msg=f"{name}: {line.strip()}")
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('self.boot_mode_combo.addItem("Legacy BIOS (MBR)", "bios")', app)
        self.assertIn('return "windows-bios" if self.selected_boot_mode() == "bios" else "windows"', app)

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
    # CI cannot rely on "sudo -E" (the runner's sudo drops the step's env:
    # block), so it passes its variables to env after sudo and then runs the
    # same command as the documented one.
    CI_ROOT_ENV = (
        'sudo env BMK_INTEGRATION_REQUIRED=1 BMK_QEMU=1 '
        'BMK_UEFI_NTFS_IMAGE="$RUNNER_TEMP/uefi-ntfs.img" '
    )
    CI_INTEGRATION = CI_ROOT_ENV + INTEGRATION.removeprefix("sudo -E env ")
    DOCUMENTS = ("README.md", "README.hu.md", "CONTRIBUTING.md", "docs/TESTING.md")

    def test_documented_test_commands_match_ci(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        for command in (self.COMPILE, self.SHELL_SYNTAX, self.SHELLCHECK, self.CI_INTEGRATION):
            self.assertIn(command, workflow)
        self.assertTrue(self.INTEGRATION.startswith("sudo -E env BMK_INTEGRATION=1 "))
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

    def test_qemu_integration_command_is_documented_and_matches_ci(self):
        qemu_command = self.INTEGRATION.replace("BMK_INTEGRATION=1 ", "BMK_INTEGRATION=1 BMK_QEMU=1 ", 1)
        self.assertIn("BMK_QEMU=1", self.CI_ROOT_ENV)
        for document in ("CONTRIBUTING.md", "docs/TESTING.md"):
            text = (ROOT / document).read_text(encoding="utf-8")
            self.assertIn(qemu_command, text, msg=f"{document}: hiányzik: {qemu_command}")

    def test_manual_qemu_check_never_writes_to_the_usb_drive(self):
        testing = (ROOT / "docs/TESTING.md").read_text(encoding="utf-8")
        self.assertIn("### Manual QEMU boot check of a finished USB drive", testing)
        device_lines = [line for line in testing.splitlines() if "/dev/sdX" in line]
        qemu_lines = [line for line in device_lines if "qemu-system" in line]
        self.assertTrue(qemu_lines)
        for line in qemu_lines:
            self.assertIn("snapshot=on", line)
            self.assertNotIn("sudo", line, msg="a kézi QEMU-próba ne fusson rootként")
        acl_lines = [line for line in device_lines if "setfacl -m" in line]
        self.assertEqual(len(acl_lines), 1)
        self.assertIn(':r /dev/sdX', acl_lines[0])
        self.assertIn('setfacl -x u:"$USER" /dev/sdX', testing)
        self.assertIn("`disk` group", testing)
        for line in device_lines:
            self.assertNotRegex(line, r"\b(dd|wipefs|mkfs|sfdisk|parted|grub-install)\b", msg=line)

    def test_compile_command_lists_every_application_module(self):
        listed = set(self.COMPILE.split()[2:])
        self.assertEqual(listed, {path.name for path in ROOT.glob("*.py")})

    def test_ci_cannot_pass_the_integration_step_by_skipping(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        # BMK_INTEGRATION_REQUIRED must reach the root process: it is given to
        # env after sudo, both in the test run and in a preceding check step.
        root_lines = [line for line in workflow.splitlines() if "sudo " in line and "BMK_" in line]
        self.assertTrue(root_lines)
        for line in root_lines:
            self.assertNotIn("sudo -E", line)
            self.assertIn(self.CI_ROOT_ENV.strip(), line)
        check = workflow.split("name: Check that the root test process receives the integration variables", 1)
        self.assertEqual(len(check), 2, msg="hiányzik a root környezetet ellenőrző CI-lépés")
        check_step, after = check[1].split("- name:", 1)[0], check[1]
        self.assertIn(self.CI_ROOT_ENV.strip(), check_step)
        self.assertIn("sys.exit(", check_step)
        self.assertLess(after.index("python3 -I -c"), after.index(self.CI_INTEGRATION))

    def test_ci_retries_package_installs_but_still_fails_closed(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"\n    timeout-minutes: \d+\n    steps:")
        install = workflow.split("- name: Install system and Python test dependencies", 1)[1].split("- name:", 1)[0]
        self.assertIn("timeout-minutes:", install)
        self.assertIn("for attempt in 1 2 3; do", install)
        self.assertIn("sudo apt-get update && sudo apt-get install -y $packages", install)
        self.assertIn("exit 1", install)
        # A missing package must fail the step, never be skipped silently.
        self.assertNotIn("--fix-missing", workflow)
        self.assertNotIn("|| true", install)
        for package in ("grub-pc-bin", "grub2-common", "qemu-system-x86", "ntfs-3g", "p7zip-full"):
            self.assertIn(package, install)

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


class LegacyBiosPackagingTests(unittest.TestCase):
    def read(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_installer_installs_the_grub_package(self):
        pacman_lines = [line.split() for line in self.read("install.sh").splitlines() if line.startswith("pacman -S ")]
        self.assertEqual(len(pacman_lines), 1)
        self.assertIn("grub", pacman_lines[0])
        # The installer must never run GRUB against the host itself.
        for line in self.read("install.sh").splitlines():
            if line.lstrip().startswith(("printf", "echo", "#")):
                continue
            self.assertNotRegex(line, r"\b(grub-install|grub-mkconfig|efibootmgr)\b", msg=line)

    def test_installer_is_stored_as_executable(self):
        if not (ROOT / ".git").exists() or shutil.which("git") is None:
            self.skipTest("nem git munkapéldány")
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--stage", "install.sh"],
            capture_output=True, text=True, check=True,
        )
        self.assertTrue(result.stdout.startswith("100755 "), msg=result.stdout)

    def test_readmes_list_grub_with_the_host_boot_loader_note(self):
        english = self.read("README.md")
        hungarian = self.read("README.hu.md")
        self.assertIn("- `grub` — `grub-install` and the i386-pc modules", english)
        self.assertIn("does **not** change your computer's own boot loader", english)
        self.assertIn("runs `grub-install` exclusively on the selected USB drive", english)
        self.assertIn("- `grub` — a `grub-install` és az i386-pc modulok", hungarian)
        self.assertIn("**nem** módosítja a gép saját rendszerbetöltőjét", hungarian)
        self.assertIn("kizárólag a kiválasztott pendrive-ra futtatja", hungarian)

    def test_readmes_document_the_legacy_mode_and_its_limits(self):
        english = self.read("README.md")
        hungarian = self.read("README.hu.md")
        self.assertIn("## Windows Legacy BIOS/MBR workflow", english)
        self.assertIn("## Windows Legacy BIOS/MBR – hogyan működik?", hungarian)
        for text in (english, hungarian):
            self.assertIn("Legacy BIOS (MBR)", text)
            self.assertIn("ntldr /bootmgr", text)
            self.assertIn("--target=i386-pc", text)
        self.assertIn("it does **not** boot in UEFI mode", english)
        self.assertIn("UEFI módban **nem**", hungarian)
        self.assertNotIn("Windows target: **UEFI x64 only**", english)
        self.assertNotIn("Windows Legacy BIOS/CSM, Windows To Go", english)
        self.assertNotIn("Windows Legacy BIOS/CSM, Windows To Go", hungarian)


class SafetyDocumentationTests(unittest.TestCase):
    def test_both_readmes_document_the_partially_written_state(self):
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        hungarian = (ROOT / "README.hu.md").read_text(encoding="utf-8")
        self.assertIn("may be left partially written", english)
        self.assertIn("részlegesen írt állapotban maradhat", hungarian)


if __name__ == "__main__":
    unittest.main()
