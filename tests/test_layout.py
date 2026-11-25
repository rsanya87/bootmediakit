"""Responsive layout, minimum size and scrolling (T3, layout work), offscreen.

Proof level: offscreen Qt (logical pixels, fonts of the test machine). It
does not replace the maintainer's checks on real desktops and screens.
"""

import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="bmk-test-config-")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QPoint, QProcess, QRect, Qt
from PySide6.QtGui import QFontDatabase, QFontInfo
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid

import app as gui
import ui_helpers

# Logical work areas: 1366x768 at 100 %, and 1280x800 at 125 % (1024x640)
# minus a 44 px panel. Window frames are not part of the offscreen platform.
WORK_AREA = (0, 0, 1366, 728)
TESTED_SIZES = ((gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT), (1024, 600), (1280, 720), (1366, 700))
TESTED_FONT_SIZES = (9.0, 10.0)
# Offscreen layout results depend on the font: the CI runner uses DejaVu Sans,
# a desktop often Noto Sans, and DejaVu Sans is wider (docs/LESSONS.md). Both
# must be installed; a missing one is an error, not a skip (CI installs
# fonts-dejavu-core and fonts-noto-core; Arch: ttf-dejavu and noto-fonts).
TESTED_FONT_FAMILIES = ("DejaVu Sans", "Noto Sans")
FONT_MATRIX = tuple((family, size) for family in TESTED_FONT_FAMILIES for size in TESTED_FONT_SIZES)
FONT_HINT = (
    "Az offscreen elrendezési teszt betűtípusfüggő: a CI DejaVu Sanst használ, "
    "a fejlesztői gép gyakran mást (docs/LESSONS.md)."
)


def require_test_fonts():
    families = set(QFontDatabase.families())
    missing = [family for family in TESTED_FONT_FAMILIES if family not in families]
    if missing:
        raise AssertionError(
            f"Hiányzó teszt-betűtípus: {', '.join(missing)}. Telepítsd (Ubuntu: fonts-dejavu-core, "
            "fonts-noto-core; Arch: ttf-dejavu, noto-fonts). " + FONT_HINT
        )
# Every visible state of the mode card (and the always shown danger warning):
# the minimum once failed in Windows mode because only the default state was
# tested (docs/LESSONS.md).
UI_STATES = (
    "raw",
    "raw-grub-missing",
    "windows-no-iso",
    "windows-uefi",
    "windows-legacy",
    "windows-legacy-grub-missing",
)
_ISO_DIR = tempfile.mkdtemp(prefix="bmk-test-iso-")
WINDOWS_ISO = Path(_ISO_DIR) / "Win11_25H2_Hungarian_x64.iso"
WINDOWS_ISO.write_bytes(b"")


def apply_ui_state(window, state):
    """Put the window into one visible state without touching any device."""
    # Do not depend on whether the test machine has GRUB i386-pc installed.
    window._bios_grub_available = not state.endswith("grub-missing")
    window.apply_grub_availability()
    if state.startswith("raw"):
        window.select_mode("raw")
        return
    if state != "windows-no-iso":
        window.iso_edit.setText(str(WINDOWS_ISO))
        window._windows_iso_path = str(WINDOWS_ISO.resolve())
    window.select_mode("windows")
    if state == "windows-legacy" or state == "windows-legacy-grub-missing":
        # With GRUB missing the Legacy item is disabled; the hint is shown
        # next to the selector, which stays on UEFI.
        window.boot_mode_combo.setCurrentIndex(1 if window._bios_grub_available else 0)
    window.update_boot_mode_controls()


# Buttons whose style sheet draws the text bold while the size hint is
# computed with the normal weight (and a checked "modeButton").
BOLD_BUTTON_NAMES = ("primaryButton",)


def _bold(font):
    font.setBold(True)
    return font


def cut_off_texts(window):
    """Visible texts that do not fit their widget (cut or hidden), with reasons.

    Elided labels (ElidedLabel) are excluded: shortening with "…" and the
    full text in the tooltip is their intended behaviour.
    """
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QLabel

    problems = []

    def wrapped_fits(name, text, font, width, height):
        metrics = QFontMetrics(font)
        widest = max((metrics.horizontalAdvance(word) for word in text.split()), default=0)
        if widest > width:
            problems.append(f"{name}: a leghosszabb szó nem fér el ({widest} > {width}): {text!r}")
        needed = metrics.boundingRect(0, 0, max(1, width), 100_000, int(Qt.TextFlag.TextWordWrap), text).height()
        if needed > height:
            problems.append(f"{name}: a tördelt szöveg nem fér el ({needed} > {height}): {text!r}")

    for widget in window.findChildren(QWidget):
        if not widget.isVisible() or isinstance(widget, gui.ElidedLabel):
            continue
        name = widget.objectName() or type(widget).__name__
        if isinstance(widget, gui.WrappingButton):
            label = widget.label
            wrapped_fits(name, widget.text(), widget.label_font(), label.contentsRect().width(),
                         label.contentsRect().height())
        elif isinstance(widget, QLabel):
            text = widget.text()
            if not text or widget.parent() is not None and isinstance(widget.parent(), gui.WrappingButton):
                continue
            if widget.wordWrap():
                wrapped_fits(name, text, widget.font(), widget.contentsRect().width(), widget.contentsRect().height())
            elif widget.sizeHint().width() > widget.width():
                problems.append(f"{name}: {widget.sizeHint().width()} > {widget.width()}: {text!r}")
        elif isinstance(widget, QAbstractButton) and widget.text():
            need = widget.sizeHint().width()
            bold = widget.objectName() in BOLD_BUTTON_NAMES or (
                widget.objectName() == "modeButton" and widget.isChecked()
            )
            if bold:
                metrics = QFontMetrics(widget.font())
                need += QFontMetrics(_bold(widget.font())).horizontalAdvance(widget.text()) - metrics.horizontalAdvance(widget.text())
            if need > widget.width():
                problems.append(f"{name}: {need} > {widget.width()}: {widget.text()!r}")
        elif isinstance(widget, QComboBox) and widget.currentText():
            if widget.sizeHint().width() > widget.width():
                problems.append(f"{name}: {widget.sizeHint().width()} > {widget.width()}: {widget.currentText()!r}")
    return problems


def describe_state(window):
    return {
        "mode": window.selected_worker_mode(),
        "boot_combo_enabled": window.boot_mode_combo.isEnabled(),
        "grub_hint": window.grub_hint.text(),
        "warning": window.findChild(QWidget, "warningPanel").isVisible(),
    }


def key_controls(window):
    """Controls that must never disappear (docs/INVARIANTS.md C3)."""
    return {
        "forrásfájl": window.iso_edit,
        "tallózás": window.browse_button,
        "célmeghajtó": window.device_combo,
        "frissítés": window.refresh_button,
        "lemezkép mód": window.raw_button,
        "windows mód": window.windows_button,
        "indítási mód": window.boot_mode_combo,
        "ellenőrzés": window.verify_checkbox,
        "megszakítás": window.cancel_button,
        "indítás": window.start_button,
        "figyelmeztetés": window.findChild(QWidget, "warningPanel"),
        "állapot": window.status_label,
        "folyamatjelző": window.progress,
        "napló": window.log,
        "téma": window.theme_button,
    }


class LayoutTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.original_font = cls.qt_app.font()
        require_test_fonts()

    def tearDown(self):
        self.qt_app.setFont(self.original_font)

    def make_window(self, *, font_size=None, font_family=None, work_area=WORK_AREA):
        if font_size is not None or font_family is not None:
            font = self.qt_app.font()
            if font_size is not None:
                font.setPointSizeF(font_size)
            if font_family is not None:
                font.setFamily(font_family)
                # The family must really be used, not silently substituted.
                self.assertEqual(QFontInfo(font).family(), font_family, msg=FONT_HINT)
            self.qt_app.setFont(font)
        patchers = [
            patch.object(QProcess, "start"),
            patch.object(gui.MainWindow, "available_area", lambda _self: work_area),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        window = gui.MainWindow()
        # QProcess.start is patched, so lsblk never answers: without this the
        # 5 s lsblk timeout opens a modal warning in long test runs.
        window.refresh_timer.stop()
        window.lsblk_timeout_timer.stop()
        window.show()

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

    def settle(self, window, width, height):
        window.resize(width, height)
        for _ in range(3):
            QApplication.processEvents()
        window.update_layout_profile()
        QApplication.processEvents()

    def assert_client_size(self, window, width, height):
        """The real client area, not only the requested size, is width x height."""
        self.assertEqual((window.geometry().width(), window.geometry().height()), (width, height))
        central = window.centralWidget()
        self.assertEqual((central.width(), central.height()), (width, height))
        # No scrollbar takes room from the page: the viewport is the whole area.
        frame = window.scroll_area.frameWidth()
        viewport = window.scroll_area.viewport()
        self.assertEqual(
            (viewport.width(), viewport.height()),
            (window.scroll_area.width() - 2 * frame, window.scroll_area.height() - 2 * frame),
        )

    def font_context(self):
        font = self.qt_app.font()
        return f"[{QFontInfo(font).family()} {font.pointSizeF():g} pt] {FONT_HINT}"

    def assert_no_page_scrollbar(self, window):
        context = self.font_context()
        self.assertFalse(window.scroll_area.verticalScrollBar().isVisible(), msg=f"függőleges görgetősáv {context}")
        self.assertFalse(window.scroll_area.horizontalScrollBar().isVisible(), msg=f"vízszintes görgetősáv {context}")

    def window_rect(self, window, widget):
        top_left = widget.mapTo(window, QPoint(0, 0))
        return QRect(top_left, widget.size())

    def assert_controls_usable(self, window, *, must_be_in_viewport):
        controls = key_controls(window)
        rects = {}
        for name, widget in controls.items():
            self.assertIsNotNone(widget, msg=name)
            self.assertTrue(widget.isVisible(), msg=f"nem látható: {name}")
            self.assertGreater(widget.width(), 10, msg=f"túl keskeny: {name}")
            self.assertGreater(widget.height(), 8, msg=f"túl alacsony: {name}")
            rects[name] = self.window_rect(window, widget)
            if must_be_in_viewport:
                viewport = window.scroll_area.viewport()
                inside = QRect(widget.mapTo(viewport, QPoint(0, 0)), widget.size())
                self.assertTrue(viewport.rect().contains(inside), msg=f"kilóg: {name} {inside} {viewport.rect()}")
        names = list(rects)
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                if controls[first].isAncestorOf(controls[second]) or controls[second].isAncestorOf(controls[first]):
                    continue
                self.assertFalse(
                    rects[first].intersects(rects[second]),
                    msg=f"átfedés: {first} {rects[first]} és {second} {rects[second]}",
                )


class ResponsiveLayoutTests(LayoutTestCase):
    def test_tested_sizes_have_no_main_scrollbar_and_keep_every_control(self):
        for family, font_size in FONT_MATRIX:
            for state in UI_STATES:
                window = self.make_window(font_size=font_size, font_family=family)
                apply_ui_state(window, state)
                for width, height in TESTED_SIZES:
                    with self.subTest(font=(family, font_size), state=state, size=(width, height)):
                        self.settle(window, width, height)
                        self.assert_no_page_scrollbar(window)
                        self.assert_client_size(window, width, height)
                        self.assert_controls_usable(window, must_be_in_viewport=True)
                        self.assertEqual(cut_off_texts(window), [], msg=f"levágott felirat {self.font_context()}")

    def test_ui_states_are_what_they_claim(self):
        expected = {
            "raw": ("raw", False, ""),
            "raw-grub-missing": ("raw", False, "Legacy nem elérhető: sudo pacman -S grub"),
            "windows-no-iso": ("windows", False, ""),
            "windows-uefi": ("windows", True, ""),
            "windows-legacy": ("windows-bios", True, ""),
            "windows-legacy-grub-missing": ("windows", True, "Legacy nem elérhető: sudo pacman -S grub"),
        }
        self.assertEqual(set(expected), set(UI_STATES))
        for state in UI_STATES:
            with self.subTest(state=state):
                window = self.make_window(font_size=9.0)
                apply_ui_state(window, state)
                self.settle(window, gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT)
                described = describe_state(window)
                self.assertEqual(
                    (described["mode"], described["boot_combo_enabled"], described["grub_hint"]),
                    expected[state],
                )
                self.assertTrue(described["warning"])

    def test_short_windows_use_two_columns_and_tall_ones_one(self):
        window = self.make_window(font_size=9.0)
        self.settle(window, 1024, 600)
        self.assertEqual(window.layout_profile(), "wide")
        self.assertLess(self.window_rect(window, window.device_card).top(),
                        self.window_rect(window, window.mode_card).top())
        self.assertLess(self.window_rect(window, window.image_card).left(),
                        self.window_rect(window, window.device_card).left())
        self.settle(window, 1600, 1000)
        self.assertEqual(window.layout_profile(), "normal")
        tops = [self.window_rect(window, card).top()
                for card in (window.image_card, window.device_card, window.mode_card, window.progress_card)]
        self.assertEqual(tops, sorted(tops))
        self.assertFalse(window.scroll_area.verticalScrollBar().isVisible())

    def test_the_log_scrolls_inside_its_box(self):
        window = self.make_window(font_size=9.0)
        self.settle(window, gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT)
        for index in range(200):
            window.append_log(f"naplósor {index}")
        QApplication.processEvents()
        self.assertGreater(window.log.verticalScrollBar().maximum(), 0)
        self.assertFalse(window.scroll_area.verticalScrollBar().isVisible())

    def test_below_the_minimum_the_page_scrolls_and_no_control_is_lost(self):
        window = self.make_window(font_size=9.0)
        window.setMinimumSize(0, 0)
        self.settle(window, 620, 420)
        self.assertTrue(window.scroll_area.verticalScrollBar().isVisible())
        self.assertFalse(window.scroll_area.horizontalScrollBar().isVisible())
        self.assert_controls_usable(window, must_be_in_viewport=False)
        for name, widget in key_controls(window).items():
            window.scroll_area.ensureWidgetVisible(widget)
            QApplication.processEvents()
            viewport = window.scroll_area.viewport()
            mapped = QRect(widget.mapTo(viewport, QPoint(0, 0)), widget.size())
            self.assertTrue(viewport.rect().intersects(mapped), msg=f"nem görgethető elő: {name}")

    def test_large_font_at_the_minimum_falls_back_to_scrolling_without_overlap(self):
        window = self.make_window(font_size=14.0)
        self.settle(window, gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT)
        self.assertFalse(window.scroll_area.horizontalScrollBar().isVisible())
        self.assert_controls_usable(window, must_be_in_viewport=False)

    def test_minimum_size_is_the_documented_constant_and_never_exceeds_the_work_area(self):
        window = self.make_window()
        self.assertEqual((window.minimumWidth(), window.minimumHeight()),
                         (gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT))
        small = self.make_window(work_area=(0, 0, 800, 480))
        self.assertLessEqual(small.minimumWidth(), 800)
        self.assertLessEqual(small.minimumHeight(), 480)
        small.fit_window_to_screen()
        self.assertLessEqual(small.width(), 800)
        self.assertLessEqual(small.height(), 480)

    def test_window_has_no_fixed_maximum_size(self):
        window = self.make_window()
        self.assertGreaterEqual(window.maximumWidth(), 10_000)
        self.assertGreaterEqual(window.maximumHeight(), 10_000)

    def test_long_names_are_elided_with_the_full_text_in_the_tooltip(self):
        window = self.make_window(font_size=9.0)
        self.settle(window, gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT)
        before = window.scroll_area.widget().minimumSizeHint().width()
        long_text = "Win11_25H2_Hungarian_x64_" + "nagyon_hosszu_fajlnev_" * 12 + ".iso • 7,2 GiB"
        window.device_detail.setText(long_text)
        window.about_label.setText(long_text)
        QApplication.processEvents()
        self.assertEqual(window.scroll_area.widget().minimumSizeHint().width(), before)
        self.assertTrue(window.device_detail.is_elided())
        self.assertEqual(window.device_detail.text(), long_text)
        self.assertEqual(window.about_label.toolTip(), long_text)
        self.assertFalse(window.scroll_area.horizontalScrollBar().isVisible())

    def test_keyboard_order_and_accessible_names_survive_reflow(self):
        window = self.make_window(font_size=9.0)

        def chain():
            order, widget = [], window.iso_edit
            for _ in range(80):
                order.append(widget)
                widget = widget.nextInFocusChain()
                if widget is window.iso_edit:
                    break
            wanted = [window.iso_edit, window.browse_button, window.refresh_button, window.device_combo,
                      window.raw_button, window.windows_button, window.boot_mode_combo,
                      window.verify_checkbox, window.cancel_button, window.start_button]
            return [item for item in order if item in wanted]

        self.settle(window, 1600, 1000)
        tall = chain()
        self.settle(window, 1024, 600)
        short = chain()
        self.assertEqual(tall, short)
        self.assertEqual(tall[0], window.iso_edit)
        self.assertLess(tall.index(window.device_combo), tall.index(window.raw_button))
        self.assertLess(tall.index(window.verify_checkbox), tall.index(window.start_button))
        for widget in (window.iso_edit, window.device_combo, window.log, window.progress,
                       window.theme_button, window.partition_info_button):
            self.assertTrue(widget.accessibleName(), msg=widget.objectName())
        self.assertEqual(window.boot_mode_label.buddy(), window.boot_mode_combo)


class FontAndDpiTests(unittest.TestCase):
    def test_no_fixed_application_font(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("Noto Sans", source)
        self.assertNotRegex(source, r"app\.setFont\(")
        self.assertNotIn("QFont(", source)

    def test_sizes_are_not_multiplied_by_the_device_pixel_ratio(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8") + (ROOT / "ui_helpers.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"devicePixelRatio\w*\(\)\s*\*|\*\s*[\w.]*devicePixelRatio")
        for name in ("logicalDotsPerInch", "physicalDotsPerInch", "QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS"):
            self.assertNotIn(name, source)

    def test_simulated_125_percent_scale_keeps_the_logical_layout(self):
        """QT_SCALE_FACTOR=1.25: the same logical size still needs no scrollbar."""
        script = textwrap.dedent(f"""
            import os, sys, tempfile
            sys.path.insert(0, {str(ROOT)!r})
            os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
            from unittest.mock import patch
            from PySide6.QtCore import QProcess
            from PySide6.QtWidgets import QApplication
            app = QApplication([])
            font = app.font(); font.setPointSizeF(9.0); app.setFont(font)
            import app as gui
            with patch.object(QProcess, "start"), patch.object(
                gui.MainWindow, "available_area", lambda self: (0, 0, 1024, 596)
            ):
                window = gui.MainWindow()
                window.show()
                window.resize(1024, 560)
                for _ in range(3):
                    app.processEvents()
                window.update_layout_profile()
                app.processEvents()
                print(window.devicePixelRatioF(), window.width(), window.height(),
                      window.scroll_area.verticalScrollBar().isVisible(),
                      window.scroll_area.horizontalScrollBar().isVisible(), flush=True)
            # Measurement done; skip interpreter-exit Qt cleanup.
            os._exit(0)
        """)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="1.25")
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env,
                                timeout=60, cwd=ROOT)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        ratio, width, height, vertical, horizontal = result.stdout.split()[-5:]
        self.assertAlmostEqual(float(ratio), 1.25, places=2)
        self.assertEqual((int(width), int(height)), (1024, 560))
        self.assertEqual((vertical, horizontal), ("False", "False"))


class MeasuredMinimumTests(unittest.TestCase):
    def test_minimum_fits_1280x800_at_100_and_125_percent(self):
        # 1280x800 at 125 % is 1024x640 logical; leave a 44 px panel and a
        # 40 px title bar/frame for the window manager.
        self.assertLessEqual(gui.MIN_WINDOW_WIDTH, 1024 - 2 * 8)
        self.assertLessEqual(gui.MIN_WINDOW_HEIGHT, 640 - 44 - 40)

    def test_minimum_is_documented(self):
        testing = (ROOT / "docs" / "TESTING.md").read_text(encoding="utf-8")
        size = f"{gui.MIN_WINDOW_WIDTH}×{gui.MIN_WINDOW_HEIGHT}"
        self.assertTrue(size in testing, msg=f"docs/TESTING.md nem említi: {size}")
        for readme in ("README.md", "README.hu.md"):
            text = (ROOT / readme).read_text(encoding="utf-8")
            self.assertTrue(size in text, msg=f"{readme} nem említi: {size}")


class TestFontRequirementTests(unittest.TestCase):
    def test_ci_installs_and_checks_both_fonts(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        for package in ("fontconfig", "fonts-dejavu-core", "fonts-noto-core"):
            self.assertIn(package, workflow)
        quoted = " ".join(f'"{family}"' for family in TESTED_FONT_FAMILIES)
        self.assertIn(f"for family in {quoted}; do", workflow)
        self.assertIn('echo "::error::Missing layout test font: $family"', workflow)

    def test_a_missing_font_is_an_error_not_a_skip(self):
        QApplication.instance() or QApplication([])
        with patch.object(QFontDatabase, "families", return_value=["DejaVu Sans"]):
            with self.assertRaises(AssertionError) as raised:
                require_test_fonts()
        self.assertIn("Noto Sans", str(raised.exception))
        self.assertIn("betűtípusfüggő", str(raised.exception))


class LayoutHelperTests(unittest.TestCase):
    def test_choose_layout_profile(self):
        choose = ui_helpers.choose_layout_profile
        self.assertEqual(choose((900, 900), {"normal": (400, 850)}), "normal")
        self.assertEqual(choose((900, 600), {"normal": (400, 850), "wide": (600, 540)}), "wide")
        self.assertEqual(choose((900, 500), {"normal": (400, 850), "wide": (600, 540)}), "wide")
        self.assertEqual(choose((500, 500), {"normal": (400, 850), "wide": (600, 540)}), "narrow")

    def test_density_profiles(self):
        self.assertIs(ui_helpers.density_for("wide"), ui_helpers.density_for("narrow"))
        self.assertLess(ui_helpers.density_for("wide")["spacing"], ui_helpers.density_for("normal")["spacing"])
        with self.assertRaises(ValueError):
            ui_helpers.density_for("tiny")

    def test_initial_window_size(self):
        size = ui_helpers.initial_window_size
        self.assertEqual(size(2560, 1400, 860, (880, 540)), (740, 900))
        self.assertEqual(size(1366, 728, 860, (880, 540)), (960, 704))
        self.assertEqual(size(1024, 596, 860, (880, 540)), (960, 572))
        self.assertEqual(size(800, 480, 860, (880, 540)), (776, 456))

    def test_clamp_minimum_size(self):
        self.assertEqual(ui_helpers.clamp_minimum_size((880, 540), (1366, 700)), (880, 540))
        self.assertEqual(ui_helpers.clamp_minimum_size((880, 540), (800, 480)), (800, 480))


if __name__ == "__main__":
    unittest.main()
