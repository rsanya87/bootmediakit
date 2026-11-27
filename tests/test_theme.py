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

from PySide6.QtCore import QEvent, QProcess, QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget
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
        # Controllers are children of the application: delete them, or they
        # stay connected to colorSchemeChanged and react in later tests.
        for controller in self.qt_app.findChildren(theme.ThemeController):
            controller.setParent(None)
            controller.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
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


# Measured: Qt 6 Fusion's standardPalette() on a desktop where Qt reports a
# dark colour scheme (KDE platform theme, gtk3 with adw-gtk3-dark). Test input.
QT_DARK_FUSION_STANDARD = lambda: make_palette("#323232", "#f0f0f0", "#242424", "#308cc6", "#4a4a4a")  # noqa: E731
DARK_DESKTOPS = {
    # The KDE platform theme ignores setColorScheme().
    "KDE-like (Breeze Dark)": lambda: make_palette("#202326", "#fcfcfc", "#141618", "#3daee9", "#4d5257"),
    # gtk3 platform theme with adw-gtk3-dark; after one override and its
    # reset, setColorScheme() no longer changes the palette (measured).
    "GNOME-like (gtk3, adw-gtk3-dark)": lambda: make_palette("#202024", "#ffffff", "#202024", "#3584e4", "#4a4a4e"),
}


def fake_fusion_style():
    class DarkFusion:
        def standardPalette(self):  # noqa: N802 - Qt naming
            return QT_DARK_FUSION_STANDARD()

    return DarkFusion()


class LightPaletteTests(QtAppMixin, unittest.TestCase):
    def test_light_palette_is_fusions_light_standard_palette(self):
        # Offscreen Qt has no colour scheme, so Fusion gives its light
        # palette: the fixed table must match it role by role, so the light
        # look did not change.
        from PySide6.QtWidgets import QStyleFactory

        self.assertNotEqual(theme.qt_color_scheme(self.qt_app), "dark")
        fusion = QStyleFactory.create("Fusion").standardPalette()
        table = theme.light_palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
            for role in QPalette.ColorRole:
                if role.name in ("NoRole", "NColorRoles"):
                    continue
                with self.subTest(group=group.name, role=role.name):
                    self.assertEqual(table.color(group, role).rgba(), fusion.color(group, role).rgba())

    def test_light_palette_does_not_follow_a_dark_colour_scheme(self):
        with patch("PySide6.QtWidgets.QStyleFactory.create", lambda *_args: fake_fusion_style()):
            self.assertEqual(theme.classify_palette(theme.light_palette()), "light")

    def test_manual_light_is_light_on_a_dark_desktop(self):
        from PySide6.QtGui import QStyleHints

        for desktop, system_palette in DARK_DESKTOPS.items():
            with self.subTest(desktop=desktop), patch.object(
                theme, "qt_color_scheme", return_value="dark"
            ), patch("PySide6.QtWidgets.QStyleFactory.create", lambda *_args: fake_fusion_style()), patch.object(
                QStyleHints, "setColorScheme"
            ), patch.object(QStyleHints, "unsetColorScheme", create=True):
                self.qt_app.setPalette(system_palette())
                settings = self.settings()
                settings.setValue(theme.SETTINGS_KEY, "system")
                controller = theme.ThemeController(self.qt_app, settings)
                controller.apply()
                self.assertEqual(controller.scheme, "dark")
                # Back to "system" is covered by the switch matrix (the offscreen
                # platform cannot keep a simulated system palette over a reset).
                for mode in ("light", "dark", "light"):
                    controller.set_mode(mode)
                    expected = mode
                    self.assertEqual(controller.scheme, expected)
                    self.assertEqual(theme.classify_palette(self.qt_app.palette()), expected, msg=f"mode {mode}")
                    tokens = controller.tokens()
                    window = theme.relative_luminance(tokens["window"])
                    if expected == "light":
                        self.assertGreater(window, 0.45, msg=f"mode {mode}")
                    else:
                        self.assertLess(window, 0.18, msg=f"mode {mode}")
                self.restore_application()


# Simulated system palettes for the switch matrix (test inputs). The light
# one differs from LIGHT_PALETTE, so native and own palettes look different.
SYSTEMS = {
    "light (Adwaita-like)": ("light", lambda: make_palette("#fafafa", "#2e3436", "#ffffff", "#3584e4", "#d6d1cd")),
    "dark (Breeze-like)": ("dark", lambda: make_palette("#202326", "#fcfcfc", "#141618", "#3daee9", "#4d5257")),
    # The GNOME case the maintainer saw: gtk3 platform theme, adw-gtk3-dark.
    "dark (adw-gtk3-dark)": ("dark", lambda: make_palette("#202024", "#ffffff", "#202024", "#3584e4", "#4a4a4e")),
}
PALETTE_ROLES = (
    QPalette.ColorRole.Window,
    QPalette.ColorRole.WindowText,
    QPalette.ColorRole.Base,
    QPalette.ColorRole.Text,
    QPalette.ColorRole.Button,
    QPalette.ColorRole.ButtonText,
    QPalette.ColorRole.Highlight,
)


class ThemeSwitchMatrixTests(QtAppMixin, unittest.TestCase):
    """Every switch gives the same window as a fresh start in the same mode
    and system scheme (INVARIANTS C4): one application path, always
    complete. The native style is "Windows", so own palettes really switch
    to Fusion and back. Qt's colour scheme override must never be called."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_layout import TESTED_FONT_FAMILIES, require_test_fonts

        require_test_fonts()
        cls.font_families = TESTED_FONT_FAMILIES
        cls.original_font = cls.qt_app.font()

    def setUp(self):
        super().setUp()
        from PySide6.QtGui import QStyleHints

        self.qt_app.setStyle("Windows")
        self.addCleanup(self.qt_app.setFont, self.original_font)
        self.system = SYSTEMS["light (Adwaita-like)"]
        patchers = [
            patch.object(QProcess, "start"),
            patch.object(theme, "qt_color_scheme", side_effect=lambda _app: self.system[0]),
            patch.object(theme, "restore_system_palette", side_effect=lambda app: app.setPalette(self.system[1]())),
            patch.object(QStyleHints, "setColorScheme"),
            patch.object(QStyleHints, "unsetColorScheme", create=True),
        ]
        mocks = [patcher.start() for patcher in patchers]
        for patcher in patchers:
            self.addCleanup(patcher.stop)
        self.set_scheme_mock, self.unset_scheme_mock = mocks[3], mocks[4]

    def tearDown(self):
        self.assertEqual(self.set_scheme_mock.call_count, 0, "setColorScheme() was called")
        self.assertEqual(self.unset_scheme_mock.call_count, 0, "unsetColorScheme() was called")

    def set_font(self, family):
        from PySide6.QtGui import QFontInfo

        font = self.qt_app.font()
        font.setFamily(family)
        font.setPointSizeF(10.0)
        self.assertEqual(QFontInfo(font).family(), family)
        self.qt_app.setFont(font)

    def start(self, system, mode):
        """A fresh start: system palette and native style, then the window."""
        import app as gui

        self.system = SYSTEMS[system]
        self.qt_app.setStyle("Windows")
        self.qt_app.setPalette(self.system[1]())
        settings = self.settings()
        settings.setValue(theme.SETTINGS_KEY, mode)
        controller = theme.ThemeController(self.qt_app, settings)
        controller.apply()
        window = gui.MainWindow(controller)
        window.refresh_timer.stop()
        window.lsblk_timeout_timer.stop()
        window.resize(1000, 700)
        window.show()
        for _ in range(5):
            QApplication.processEvents()
        return window, controller

    def dispose(self, window, controller):
        window.close()
        window.deleteLater()
        controller.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()

    def snapshot(self, window):
        for _ in range(5):
            QApplication.processEvents()
        palettes = [
            (widget.metaObject().className(), widget.objectName(),
             tuple(widget.palette().color(role).rgba() for role in PALETTE_ROLES))
            for widget in (window, *window.findChildren(QWidget))
            # Popup internals (combo box lists) are created lazily.
            if widget.window() is window
        ]
        return {
            "image": window.grab().toImage(),
            "palettes": palettes,
            "state": (window.theme.mode, window.theme.scheme, window.theme.source,
                      window.theme.uses_own_palette(), self.qt_app.style().name().lower()),
            "sheet": window.styleSheet(),
            "tooltip": window.theme_button.toolTip(),
        }

    def fresh(self, system, mode):
        key = (system, mode, self.qt_app.font().family())
        if key not in self._fresh:
            window, controller = self.start(system, mode)
            self._fresh[key] = self.snapshot(window)
            self.dispose(window, controller)
        return self._fresh[key]

    def assert_same(self, got, expected, context):
        self.assertEqual(got["state"], expected["state"], context)
        self.assertEqual(got["sheet"], expected["sheet"], context)
        self.assertEqual(got["tooltip"], expected["tooltip"], context)
        for got_widget, expected_widget in zip(got["palettes"], expected["palettes"], strict=True):
            self.assertEqual(got_widget, expected_widget, f"{context}: widget palette differs")
        if got["image"] != expected["image"]:
            a, b = got["image"], expected["image"]
            differing = sum(
                1 for y in range(0, min(a.height(), b.height()), 2) for x in range(0, min(a.width(), b.width()), 2)
                if a.pixel(x, y) != b.pixel(x, y)
            )
            self.fail(f"{context}: the window differs from a fresh start ({differing} sampled pixels, "
                      f"sizes {a.size().toTuple()} / {b.size().toTuple()})")

    def test_every_mode_switch_matches_a_fresh_start(self):
        self._fresh = {}
        pairs = (("system", "light"), ("system", "dark"), ("light", "dark"))
        for family in self.font_families:
            self.set_font(family)
            for system in SYSTEMS:
                for first, second in pairs:
                    with self.subTest(font=family, system=system, pair=f"{first}<->{second}"):
                        expected = {mode: self.fresh(system, mode) for mode in (first, second)}
                        window, controller = self.start(system, first)
                        try:
                            self.assert_same(self.snapshot(window), expected[first], f"{system}: start {first}")
                            for step, mode in enumerate((second, first, second, first)):
                                controller.set_mode(mode)
                                self.assert_same(self.snapshot(window), expected[mode],
                                                 f"[{family}] {system}: switch {step + 1} to {mode}")
                        finally:
                            self.dispose(window, controller)

    def test_automatic_dark_and_manual_dark_on_adw_gtk3_dark(self):
        """The maintainer's case: GNOME, adw-gtk3-dark, automatic mode dark,
        switching to manual dark and back mixed the colours."""
        self._fresh = {}
        system = "dark (adw-gtk3-dark)"
        for family in self.font_families:
            self.set_font(family)
            for first, second in (("system", "dark"), ("dark", "system")):
                with self.subTest(font=family, direction=f"{first}->{second}"):
                    expected = {mode: self.fresh(system, mode) for mode in (first, second)}
                    self.assertFalse(expected["dark"]["state"][3], "manual dark on a dark desktop stays native")
                    window, controller = self.start(system, first)
                    try:
                        for mode in (second, first, second, first, second):
                            controller.set_mode(mode)
                            self.assert_same(self.snapshot(window), expected[mode], f"[{family}] to {mode}")
                    finally:
                        self.dispose(window, controller)

    def test_every_widget_is_polished_again_also_when_nothing_changed(self):
        # The pixel matrix cannot show a missing polish offscreen, so the
        # calls are counted: every widget of the window, on every apply,
        # also when the mode, the scheme and the style sheet stay the same.
        self._fresh = {}
        self.set_font(self.font_families[0])
        window, controller = self.start("dark (adw-gtk3-dark)", "system")
        try:
            style_type = type(window.style())
            calls = {"unpolish": [], "polish": []}
            originals = {name: getattr(style_type, name) for name in calls}

            def recorder(name):
                def record(style, target, *args):
                    calls[name].append(target)
                    return originals[name](style, target, *args)

                return record

            for mode in ("dark", "system", "system", "dark"):
                with self.subTest(mode=mode):
                    for name in calls:
                        calls[name].clear()
                    with patch.object(style_type, "unpolish", recorder("unpolish")), patch.object(
                        style_type, "polish", recorder("polish")
                    ):
                        controller.set_mode(mode)
                    widgets = [widget for widget in (window, *window.findChildren(QWidget))
                               if widget.window() is window]
                    for name, targets in calls.items():
                        missing = [f"{widget.metaObject().className()}#{widget.objectName()}"
                                   for widget in widgets if not any(target is widget for target in targets)]
                        self.assertEqual(missing, [], f"{name} missing after switching to {mode}")
        finally:
            self.dispose(window, controller)

    def test_a_system_scheme_change_while_running_matches_a_fresh_start(self):
        self._fresh = {}
        self.set_font(self.font_families[0])
        for mode in theme.THEME_MODES:
            for before, after in (("light (Adwaita-like)", "dark (adw-gtk3-dark)"),
                                  ("dark (Breeze-like)", "light (Adwaita-like)")):
                with self.subTest(mode=mode, change=f"{before} -> {after}"):
                    expected = self.fresh(after, mode)
                    window, controller = self.start(before, mode)
                    try:
                        # What the platform does: a new system palette (an
                        # own palette hides it) and colorSchemeChanged.
                        self.system = SYSTEMS[after]
                        if not controller.uses_own_palette():
                            self.qt_app.setPalette(self.system[1]())
                        self.qt_app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
                        self.assert_same(self.snapshot(window), expected, f"{mode}: {before} -> {after}")
                    finally:
                        self.dispose(window, controller)


class KdeLikePlatformThemeTests(QtAppMixin, unittest.TestCase):
    """The KDE platform theme ignores setColorScheme() (measured), so the
    old path already decided from the system palette alone. The results
    stay the same: manual dark on a dark desktop is native, manual light
    gets Fusion with the light palette, "system" is native."""

    def test_results_are_unchanged_on_a_dark_kde_like_desktop(self):
        system = SYSTEMS["dark (Breeze-like)"][1]
        with patch.object(theme, "qt_color_scheme", return_value="dark"), patch.object(
            theme, "restore_system_palette", side_effect=lambda app: app.setPalette(system())
        ):
            self.qt_app.setStyle("Windows")
            self.qt_app.setPalette(system())
            controller = theme.ThemeController(self.qt_app, self.settings())
            expected = {
                "system": ("dark", "system", False, "windows", "#202326"),
                "dark": ("dark", "manual", False, "windows", "#202326"),
                "light": ("light", "manual", True, "fusion", "#efefef"),
            }
            for mode in ("system", "dark", "light", "system", "light", "dark", "system"):
                controller.set_mode(mode)
                window = self.qt_app.palette().color(QPalette.ColorRole.Window).name()
                self.assertEqual(
                    (controller.scheme, controller.source, controller.uses_own_palette(),
                     self.qt_app.style().name().lower(), window),
                    expected[mode],
                    mode,
                )


class NoColorSchemeOverrideTests(unittest.TestCase):
    def test_theme_code_never_calls_the_qt_colour_scheme_override(self):
        for name in ("theme.py", "app.py"):
            tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
            used = sorted(
                {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
                & {"setColorScheme", "unsetColorScheme"}
            )
            strings = sorted(
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and node.value in ("setColorScheme", "unsetColorScheme")
            )
            self.assertEqual((used, strings), ([], []), name)


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
        # LIGHT_PALETTE(_DISABLED): Fusion's standardPalette() follows Qt's
        # colour scheme in Qt 6 (dark on a dark desktop), so the manual light
        # mode needs a fixed table like the dark fallback (docs/LESSONS.md).
        allowed_names = {
            "STATUS_HUES",
            "DARK_PALETTE",
            "DARK_PALETTE_DISABLED",
            "LIGHT_PALETTE",
            "LIGHT_PALETTE_DISABLED",
        }
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
