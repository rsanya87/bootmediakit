"""Responsive layout, minimum size and scrolling (0.4.0 T3), offscreen.

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

from PySide6.QtCore import QEvent, QPoint, QProcess, QRect
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid

import app as gui
import ui_helpers

# Logical work areas: 1366x768 at 100 %, and 1280x800 at 125 % (1024x640)
# minus a 44 px panel. Window frames are not part of the offscreen platform.
WORK_AREA = (0, 0, 1366, 728)
TESTED_SIZES = ((gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT), (1024, 600), (1280, 720), (1366, 700))
TESTED_FONT_SIZES = (9.0, 10.0)


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

    def tearDown(self):
        self.qt_app.setFont(self.original_font)

    def make_window(self, *, font_size=None, work_area=WORK_AREA):
        if font_size is not None:
            font = self.qt_app.font()
            font.setPointSizeF(font_size)
            self.qt_app.setFont(font)
        patchers = [
            patch.object(QProcess, "start"),
            patch.object(gui.MainWindow, "available_area", lambda _self: work_area),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        window = gui.MainWindow()
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
        for font_size in TESTED_FONT_SIZES:
            for width, height in TESTED_SIZES:
                with self.subTest(font=font_size, size=(width, height)):
                    window = self.make_window(font_size=font_size)
                    self.settle(window, width, height)
                    self.assertEqual((window.width(), window.height()), (width, height))
                    self.assertFalse(window.scroll_area.verticalScrollBar().isVisible())
                    self.assertFalse(window.scroll_area.horizontalScrollBar().isVisible())
                    self.assert_controls_usable(window, must_be_in_viewport=True)

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
