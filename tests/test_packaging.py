from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


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
        self.assertIn('APP_VERSION = "0.1.3"', app)
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


if __name__ == "__main__":
    unittest.main()
