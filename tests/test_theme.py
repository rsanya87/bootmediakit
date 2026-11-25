"""Theme tokens, system detection, dark fallback and the manual switch (T2, theme work)."""

import ast
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Never read or write the real user's ~/.config/BootMediaKit in tests.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="bmk-test-config-")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QProcess, QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

import theme

HEX_OR_RGB = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(")


def make_palette(window, text, base, highlight, mid="#808080", highlighted_text=None):
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: window,
        QPalette.ColorRole.WindowText: text,
        QPalette.ColorRole.Base: base,
        QPalette.ColorRole.Text: text,
        QPalette.ColorRole.Button: window,
        QPalette.ColorRole.ButtonText: text,
        QPalette.ColorRole.Highlight: highlight,
        QPalette.ColorRole.Mid: mid,
        QPalette.ColorRole.AlternateBase: window,
    }
    if highlighted_text:
        roles[QPalette.ColorRole.HighlightedText] = highlighted_text
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    return palette


# Representative palettes; values are test inputs, not application colours.
SAMPLE_PALETTES = {
    "fusion light": lambda: theme.light_palette(),
    "fallback dark": lambda: theme.dark_palette(),
    "breeze-like dark": lambda: make_palette("#202326", "#fcfcfc", "#141618", "#3daee9", "#4d5257"),
    "adwaita-like light": lambda: make_palette("#fafafa", "#2e3436", "#ffffff", "#3584e4", "#d6d1cd"),
    "xfce-like grey": lambda: make_palette("#edeceb", "#2e3436", "#ffffff", "#86abd9", "#c0bebc"),
    "high contrast dark": lambda: make_palette("#000000", "#ffffff", "#000000", "#ffff00", "#ffffff", "#000000"),
    "high contrast light": lambda: make_palette("#ffffff", "#000000", "#ffffff", "#0000c0", "#000000", "#ffffff"),
    "low contrast highlight": lambda: make_palette("#f0f0f0", "#202020", "#ffffff", "#c8e0f8", "#e0e0e0"),
}


class QtAppMixin:
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.native_style = cls.qt_app.style().name()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.settings_path = Path(temp.name) / "BootMediaKit.conf"
        self.addCleanup(self.restore_application)

    def settings(self):
        return QSettings(str(self.settings_path), QSettings.Format.IniFormat)

    def restore_application(self):
        self.qt_app.setStyle(self.native_style)
        self.qt_app.setPalette(QPalette())
        unset = getattr(self.qt_app.styleHints(), "unsetColorScheme", None)
        if unset is not None:
            unset()


class ContrastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_contrast_ratio_matches_known_values(self):
        self.assertAlmostEqual(theme.contrast_ratio(QColor("#000000"), QColor("#ffffff")), 21.0, places=2)
        self.assertAlmostEqual(theme.contrast_ratio(QColor("#777777"), QColor("#ffffff")), 4.48, places=2)
        self.assertAlmostEqual(theme.contrast_ratio(QColor("#ffffff"), QColor("#ffffff")), 1.0)

    def test_every_token_pair_meets_its_target_on_every_sample_palette(self):
        for name, factory in SAMPLE_PALETTES.items():
            tokens = theme.compute_tokens(factory())
            for foreground, background, target in theme.CONTRAST_PAIRS:
                with self.subTest(palette=name, pair=(foreground, background)):
                    ratio = theme.contrast_ratio(tokens[foreground], tokens[background])
                    self.assertGreaterEqual(ratio, target, msg=f"{ratio:.2f} < {target}")

    def test_disabled_controls_stay_distinguishable_from_enabled_ones(self):
        for name, factory in SAMPLE_PALETTES.items():
            with self.subTest(palette=name):
                tokens = theme.compute_tokens(factory())
                self.assertNotEqual(tokens["disabled_bg"].name(), tokens["primary_bg"].name())
                self.assertNotEqual(tokens["disabled_text"].name(), tokens["text"].name())

    def test_tokens_follow_the_palette_instead_of_fixed_values(self):
        light = theme.compute_tokens(theme.light_palette())
        dark = theme.compute_tokens(theme.dark_palette())
        for name in ("window", "text", "secondary_text", "border", "warning_bg"):
            self.assertNotEqual(light[name].name(), dark[name].name(), msg=name)
        high = theme.compute_tokens(SAMPLE_PALETTES["high contrast dark"]())
        self.assertEqual(high["window"].name(), "#000000")
        self.assertEqual(high["text"].name(), "#ffffff")

    def test_stylesheet_uses_every_template_token(self):
        tokens = theme.compute_tokens(theme.dark_palette())
        sheet = theme.build_stylesheet(tokens)
        self.assertNotIn("{", sheet.replace("{ ", "").replace(" }", "").replace("{{", ""))
        for name in re.findall(r"\{(\w+)\}", theme.STYLE_TEMPLATE):
            self.assertIn(name, tokens)
        self.assertIn(f"background: {tokens['window'].name()}", sheet)


class ClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_unambiguous_palettes_are_classified(self):
        self.assertEqual(theme.classify_palette(theme.dark_palette()), "dark")
        self.assertEqual(theme.classify_palette(theme.light_palette()), "light")
        self.assertEqual(theme.classify_palette(SAMPLE_PALETTES["high contrast dark"]()), "dark")
        self.assertEqual(theme.classify_palette(SAMPLE_PALETTES["high contrast light"]()), "light")

    def test_mid_grey_or_low_contrast_palettes_are_not_classified(self):
        self.assertIsNone(theme.classify_palette(make_palette("#808080", "#000000", "#808080", "#3daee9")))
        self.assertIsNone(theme.classify_palette(make_palette("#404040", "#707070", "#404040", "#3daee9")))
        self.assertIsNone(theme.classify_palette(make_palette("#999999", "#000000", "#999999", "#3daee9")))

    def test_qt_color_scheme_has_priority_over_the_palette(self):
        with patch.object(theme, "qt_color_scheme", return_value="dark"):
            self.assertEqual(theme.detect_system_scheme(self.qt_app), "dark")
        with patch.object(theme, "qt_color_scheme", return_value=None), patch.object(
            self.qt_app, "palette", return_value=theme.dark_palette()
        ):
            self.assertEqual(theme.detect_system_scheme(self.qt_app), "dark")


class ThemeControllerTests(QtAppMixin, unittest.TestCase):
    def test_new_installation_defaults_to_system_mode(self):
        controller = theme.ThemeController(self.qt_app, self.settings())
        self.assertEqual(controller.mode, "system")

    def test_invalid_stored_value_falls_back_to_system_mode(self):
        settings = self.settings()
        settings.setValue(theme.SETTINGS_KEY, "purple")
        settings.sync()
        self.assertEqual(theme.ThemeController(self.qt_app, self.settings()).mode, "system")

    def test_system_mode_follows_a_detectable_system_and_keeps_the_native_style(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme), patch.object(theme, "qt_color_scheme", return_value=scheme):
                controller = theme.ThemeController(self.qt_app, self.settings())
                controller.apply()
                self.assertEqual((controller.scheme, controller.source), (scheme, "system"))
                self.assertFalse(controller.uses_own_palette())
                self.assertEqual(self.qt_app.style().name(), self.native_style)

    def test_undeterminable_system_scheme_starts_dark(self):
        self.qt_app.setPalette(make_palette("#808080", "#000000", "#808080", "#3daee9"))
        with patch.object(theme, "qt_color_scheme", return_value=None):
            controller = theme.ThemeController(self.qt_app, self.settings())
            controller.apply()
        self.assertEqual((controller.scheme, controller.source), ("dark", "fallback"))
        self.assertEqual(theme.classify_palette(self.qt_app.palette()), "dark")

    def test_manual_switch_is_stored_and_survives_a_restart(self):
        with patch.object(theme, "qt_color_scheme", return_value="light"):
            controller = theme.ThemeController(self.qt_app, self.settings())
            controller.apply()
            self.assertEqual(controller.scheme, "light")
            controller.toggle()
        self.assertEqual((controller.mode, controller.scheme, controller.source), ("dark", "dark", "manual"))
        self.assertEqual(theme.classify_palette(self.qt_app.palette()), "dark")
        self.assertEqual(self.settings().value(theme.SETTINGS_KEY), "dark")

        restarted = theme.ThemeController(self.qt_app, self.settings())
        self.assertEqual(restarted.mode, "dark")
        restarted.toggle()
        self.assertEqual(restarted.scheme, "light")
        self.assertEqual(theme.classify_palette(self.qt_app.palette()), "light")
        self.assertEqual(self.settings().value(theme.SETTINGS_KEY), "light")

    def test_restoring_system_mode_drops_the_own_palette_and_fusion(self):
        controller = theme.ThemeController(self.qt_app, self.settings())
        controller.set_mode("dark")
        if controller.uses_own_palette():
            self.assertEqual(self.qt_app.style().name().lower(), "fusion")
        with patch.object(theme, "qt_color_scheme", return_value="light"):
            controller.set_mode("system")
        self.assertFalse(controller.uses_own_palette())
        self.assertEqual(self.qt_app.style().name(), self.native_style)
        self.assertEqual(self.settings().value(theme.SETTINGS_KEY), "system")
        self.assertEqual((controller.scheme, controller.source), ("light", "system"))

    def test_set_mode_rejects_unknown_values(self):
        controller = theme.ThemeController(self.qt_app, self.settings())
        with self.assertRaises(ValueError):
            controller.set_mode("sepia")


class WindowThemeTests(QtAppMixin, unittest.TestCase):
    def make_window(self, controller):
        import app as gui

        start_patcher = patch.object(QProcess, "start")
        start_patcher.start()
        self.addCleanup(start_patcher.stop)
        window = gui.MainWindow(controller)

        def dispose():
            if isValid(window):
                window.close()
                window.refresh_timer.stop()
                window.lsblk_timeout_timer.stop()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                QApplication.processEvents()

        self.addCleanup(dispose)
        return window

    def controller(self, scheme="light"):
        with patch.object(theme, "qt_color_scheme", return_value=scheme):
            controller = theme.ThemeController(self.qt_app, self.settings())
            controller.apply()
        return controller

    def test_theme_button_shows_state_and_has_accessible_text(self):
        window = self.make_window(self.controller("light"))
        button = window.theme_button
        self.assertFalse(button.icon().isNull())
        self.assertEqual(button.accessibleName(), "Megjelenés váltása")
        self.assertIn("Megjelenés: Világos (a rendszer beállítása szerint)", button.toolTip())
        self.assertIn("Kattintás: váltás sötét megjelenésre", button.toolTip())
        self.assertIn("Rendszer / Automatikus", button.toolTip())
        self.assertEqual(button.accessibleDescription(), button.toolTip())
        self.assertEqual(
            [action.text() for action in button.menu().actions()],
            ["Rendszer / Automatikus", "Világos", "Sötét"],
        )
        self.assertTrue(window.theme_actions["system"].isChecked())

    def test_menu_arrow_does_not_cover_the_icon(self):
        # Seen on KDE Plasma (Wayland): the style sheet border made the
        # menu-button part of the MenuButtonPopup button overlap the sun/moon.
        from PySide6.QtGui import QIcon, QPixmap
        from PySide6.QtWidgets import QStyle, QStyleOptionToolButton

        marker = QColor("#ff00ff")
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                window = self.make_window(self.controller(scheme))
                window.show()
                QApplication.processEvents()
                button = window.theme_button
                for focused in (False, True):
                    if focused:
                        button.setFocus()
                        QApplication.processEvents()
                    pixmap = QPixmap(button.iconSize())
                    pixmap.fill(marker)
                    button.setIcon(QIcon(pixmap))
                    option = QStyleOptionToolButton()
                    button.initStyleOption(option)
                    menu_rect = button.style().subControlRect(
                        QStyle.ComplexControl.CC_ToolButton,
                        option,
                        QStyle.SubControl.SC_ToolButtonMenu,
                        button,
                    )
                    self.assertTrue(menu_rect.isValid())
                    image = button.grab().toImage()
                    icon_columns = {
                        x
                        for x in range(image.width())
                        for y in range(image.height())
                        if image.pixelColor(x, y) == marker
                    }
                    # The whole icon is visible (the menu part does not
                    # paint over any of its columns) and lies left of it.
                    self.assertEqual(
                        len(icon_columns),
                        button.iconSize().width(),
                        f"icon partly covered: {len(icon_columns)} visible columns (focused={focused})",
                    )
                    self.assertLess(
                        max(icon_columns),
                        menu_rect.left(),
                        f"menu button {menu_rect} covers the icon (focused={focused})",
                    )

    def test_clicking_the_button_switches_and_the_menu_restores_system_mode(self):
        controller = self.controller("light")
        window = self.make_window(controller)
        window.theme_button.click()
        self.assertEqual((controller.mode, controller.scheme), ("dark", "dark"))
        self.assertTrue(window.theme_actions["dark"].isChecked())
        self.assertIn("Megjelenés: Sötét (kézi beállítás)", window.theme_button.toolTip())
        dark_window = theme.compute_tokens(self.qt_app.palette())["window"].name()
        self.assertIn(f"QMainWindow {{ background: {dark_window}; }}", window.styleSheet())

        with patch.object(theme, "qt_color_scheme", return_value="light"):
            window.theme_actions["system"].trigger()
        self.assertEqual((controller.mode, controller.source), ("system", "system"))
        self.assertTrue(window.theme_actions["system"].isChecked())
        self.assertEqual(self.settings().value(theme.SETTINGS_KEY), "system")

    def test_fallback_is_explained_in_the_tooltip(self):
        self.qt_app.setPalette(make_palette("#808080", "#000000", "#808080", "#3daee9"))
        window = self.make_window(self.controller(None))
        self.assertIn("a rendszer témája nem állapítható meg, ezért sötét", window.theme_button.toolTip())

    def test_system_palette_change_restyles_the_running_window(self):
        controller = self.controller("light")
        window = self.make_window(controller)
        light_sheet = window.styleSheet()
        with patch.object(theme, "qt_color_scheme", return_value=None):
            self.qt_app.setPalette(theme.dark_palette())
            QApplication.processEvents()
        self.assertEqual(controller.scheme, "dark")
        self.assertNotEqual(window.styleSheet(), light_sheet)
        self.assertIn(theme.compute_tokens(theme.dark_palette())["window"].name(), window.styleSheet())

    def test_status_state_has_an_icon_and_accessible_name_not_only_colour(self):
        window = self.make_window(self.controller("light"))
        images = {}
        for state in ("progress", "success", "warning", "error"):
            window.set_status_state(state)
            self.assertEqual(window.status_label.property("state"), state)
            self.assertFalse(window.status_icon.pixmap().isNull())
            self.assertTrue(window.status_icon.accessibleName().startswith("Állapot: "))
            # Same shape in one colour must still differ between states.
            images[state] = theme.status_icon_pixmap(
                state, {key: QColor("#000000") for key in ("focus", "success_icon", "warning_icon", "error_icon")}
            ).toImage()
        for first in images:
            for second in images:
                if first < second:
                    self.assertNotEqual(images[first], images[second], msg=(first, second))

    def test_finished_operation_marks_success_with_the_success_state(self):
        window = self.make_window(self.controller("light"))
        with patch("app.QMessageBox.information"):
            window._worker_started = True
            window.operation_finished(0, QProcess.ExitStatus.NormalExit)
        self.assertEqual(window.status_label.property("state"), "success")
        self.assertEqual(window.status_icon.accessibleName(), "Állapot: sikeres")


class FixedColourTests(unittest.TestCase):
    def test_app_py_has_no_fixed_colours(self):
        text = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertEqual(HEX_OR_RGB.findall(text), [])

    def test_theme_template_has_no_fixed_colours(self):
        self.assertEqual(HEX_OR_RGB.findall(theme.STYLE_TEMPLATE), [])

    def test_fixed_colours_in_theme_py_are_only_the_allowed_exceptions(self):
        tree = ast.parse((ROOT / "theme.py").read_text(encoding="utf-8"))
        allowed_names = {"STATUS_HUES", "DARK_PALETTE", "DARK_PALETTE_DISABLED"}
        allowed_nodes = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in allowed_names for target in node.targets
            ):
                allowed_nodes.update(id(child) for child in ast.walk(node.value))
        offenders = [
            (node.lineno, node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and HEX_OR_RGB.search(node.value)
            and id(node) not in allowed_nodes
        ]
        self.assertEqual(offenders, [])

    def test_gui_settings_stay_on_the_gui_side(self):
        worker = (ROOT / "worker.py").read_text(encoding="utf-8")
        self.assertNotIn("QSettings", worker)
        self.assertNotIn("theme", re.findall(r"^(?:from|import) (\w+)", worker, flags=re.MULTILINE))

    def test_no_desktop_specific_branching(self):
        source = (ROOT / "theme.py").read_text(encoding="utf-8") + (ROOT / "app.py").read_text(encoding="utf-8")
        for name in ("XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "KDE_FULL_SESSION", "GNOME_DESKTOP_SESSION_ID",
                     "GTK_THEME", "gsettings", "kreadconfig"):
            self.assertNotIn(name, source)


if __name__ == "__main__":
    unittest.main()
