"""tr() for the new GUI texts and the pseudo-locale layout check (T5, see docs/progress.md).

Proof level: source scan and offscreen Qt. The pseudo-locale is a
deliberate exaggeration (+40 % length, accented letters); it does not
replace a real translation or a check on a real desktop.
"""

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="bmk-test-config-")
ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
for path in (str(ROOT), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

import app as gui
import test_layout as layout
import theme
from pseudo_locale import END, START, PseudoTranslator, pseudo, pseudo_localize_widgets
from text_scan import text_literals, tr_calls_without_literal

GUI_SOURCES = ("app.py", "theme.py", "ui_helpers.py")
LEGACY_FILE = TESTS / "fixtures" / "legacy_untranslated_texts.json"
# Number of older texts without tr() when the list was made (T5).
# The list may only shrink; a later release converts them (ROADMAP.md).
LEGACY_LIMIT = 145


def legacy_texts():
    return set(json.loads(LEGACY_FILE.read_text(encoding="utf-8"))["texts"])


def untranslated_texts():
    found = {}
    for name in GUI_SOURCES:
        source = (ROOT / name).read_text(encoding="utf-8")
        for literal in text_literals(source):
            if not literal.in_tr:
                found.setdefault(literal.text, []).append(f"{name}:{literal.line}")
    return found


class TrSourceTests(unittest.TestCase):
    def test_new_gui_texts_use_tr(self):
        legacy = legacy_texts()
        new = {text: places for text, places in untranslated_texts().items() if text not in legacy}
        self.assertEqual(
            new,
            {},
            msg="Új felhasználói szöveg tr() nélkül. Minden új szöveg "
            "tr()/QCoreApplication.translate(\"BootMediaKit\", …) hívással készül.",
        )

    def test_legacy_list_only_shrinks(self):
        legacy = legacy_texts()
        self.assertLessEqual(len(legacy), LEGACY_LIMIT, msg="A régi szövegek listája nem bővíthető.")
        stale = legacy - set(untranslated_texts())
        self.assertEqual(stale, set(), msg="Már nem létező vagy tr()-re átírt szöveg: töröld a listából.")

    def test_tr_arguments_are_plain_literals(self):
        for name in GUI_SOURCES:
            with self.subTest(source=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                self.assertEqual(tr_calls_without_literal(source), [])

    def test_new_texts_are_found_in_tr(self):
        literals = {item.text: item.in_tr for name in GUI_SOURCES
                    for item in text_literals((ROOT / name).read_text(encoding="utf-8"))}
        for text in ("Rendszer / Automatikus", "Megjelenés váltása", "A hitelesítés nem sikerült",
                     "Állapot: készen áll", "Forrás lemezkép",
                     # Fallback of describe_privilege_failure (review finding).
                     "A jogosultságkérés vagy a worker indítása nem sikerült.", "A művelet nem indult el"):
            with self.subTest(text=text):
                self.assertIs(literals.get(text), True)

    def test_without_a_catalogue_tr_returns_the_hungarian_source(self):
        self.assertEqual(theme.tr("Világos"), "Világos")
        self.assertIs(gui.tr, theme.tr)

    def test_the_scanner_itself(self):
        source = '\n'.join([
            'def f(label):',
            '    """Docstring is ignored."""',
            '    label.setText("Új szöveg")',
            '    label.setToolTip(tr("Lefordítható szöveg"))',
            '    label.setObjectName("statusLabel")',
            '    raise ValueError("fejlesztői hiba")',
            '    tr(f"nem {label}")',
        ])
        found = {item.text: item.in_tr for item in text_literals(source)}
        self.assertEqual(found, {"Új szöveg": False, "Lefordítható szöveg": True, "nem ": True})
        self.assertEqual(tr_calls_without_literal(source), [7])


class PseudoHelperTests(unittest.TestCase):
    def visible(self, text):
        import re
        return re.sub(r"<[^>]*>", "", text)

    def test_texts_get_40_percent_longer_and_accented(self):
        for text in ("Megszakítás", "USB elkészítése", "Kiírás utáni teljes visszaolvasás és ellenőrzés"):
            with self.subTest(text=text):
                result = pseudo(text)
                self.assertTrue(result.startswith(START) and result.endswith(END))
                self.assertGreaterEqual(len(result), math.ceil(len(text) * 1.4))
                self.assertNotEqual(result.strip(START + END), text)

    def test_markup_placeholders_and_line_breaks_are_kept(self):
        text = "<b>{name}</b> &amp; %1\nmásodik sor</p>"
        result = pseudo(text)
        for part in ("<b>", "{name}", "</b>", "&amp;", "%1", "\n"):
            self.assertIn(part, result)
        self.assertTrue(result.endswith("</p>"))
        self.assertIn("X", pseudo("Megjelenés: {appearance}").format(appearance="X"))

    def test_idempotent_and_short_symbols_unchanged(self):
        once = pseudo("Frissítés")
        self.assertEqual(pseudo(once), once)
        for text in ("i", "⚠", "", "↻"):
            self.assertEqual(pseudo(text), text)


class PseudoLocaleLayoutTests(layout.LayoutTestCase):
    """The T3 layout checks with every text about 40 % longer."""

    def setUp(self):
        self.translator = PseudoTranslator()
        self.qt_app.installTranslator(self.translator)
        self.addCleanup(self.qt_app.removeTranslator, self.translator)

    def pseudo_window(self, font_size, state, family=None):
        window = self.make_window(font_size=font_size, font_family=family)
        layout.apply_ui_state(window, state)
        changed = pseudo_localize_widgets(window)
        self.assertGreater(changed, 20)
        return window

    def test_both_routes_replace_the_texts(self):
        window = self.pseudo_window(9.0, "windows-uefi")
        # tr() texts through the translator ...
        self.assertTrue(window.theme_button.accessibleName().startswith(START))
        self.assertTrue(window.theme_button.toolTip().startswith(START))
        # ... and the older texts on the widgets.
        for widget in (window.start_button, window.cancel_button, window.raw_button, window.verify_checkbox.label):
            with self.subTest(widget=widget.objectName() or type(widget).__name__):
                self.assertTrue(widget.text().startswith(START), msg=widget.text())

    def test_at_the_minimum_the_page_may_scroll_but_no_control_is_lost(self):
        # Approved deviation (maintainer, T5; docs/progress.md): +40 % text needs more
        # height than 880x550 offers; the vertical scroll fallback is allowed
        # there, but no horizontal scrollbar, no overlap and every control must
        # be reachable by scrolling.
        for family, font_size in layout.FONT_MATRIX:
            for state in layout.UI_STATES:
                with self.subTest(font=(family, font_size), state=state):
                    window = self.pseudo_window(font_size, state, family)
                    self.settle(window, gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT)
                    self.assertEqual(
                        (window.geometry().width(), window.geometry().height()),
                        (gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT),
                    )
                    self.assertFalse(window.scroll_area.horizontalScrollBar().isVisible(), msg=self.font_context())
                    # Longer texts wrap instead of forcing the single column
                    # (a QCheckBox text did, see WrappingCheckBox).
                    self.assertEqual(window.layout_profile(), "wide", msg=self.font_context())
                    self.assert_controls_usable(window, must_be_in_viewport=False)
                    viewport = window.scroll_area.viewport()
                    for name, widget in layout.key_controls(window).items():
                        window.scroll_area.ensureWidgetVisible(widget, 0, 0)
                        QApplication.processEvents()
                        mapped = QRect(widget.mapTo(viewport, QPoint(0, 0)), widget.size())
                        self.assertTrue(viewport.rect().contains(mapped),
                                        msg=f"nem görgethető elő: {name} {mapped} {viewport.rect()}")

    def test_1024x600_keeps_at_least_10_px_to_spare(self):
        # The compact spacing was tightened so that the pseudo-locale fits
        # 1024x600 with the wider DejaVu Sans with a margin (measured worst
        # case: 578 px of height); 1024x590 must not scroll either.
        for family, font_size in layout.FONT_MATRIX:
            for state in layout.UI_STATES:
                with self.subTest(font=(family, font_size), state=state):
                    window = self.pseudo_window(font_size, state, family)
                    self.settle(window, 1024, 590)
                    self.assert_no_page_scrollbar(window)

    def test_from_1024x600_up_there_is_no_scrollbar(self):
        sizes = [size for size in layout.TESTED_SIZES
                 if size != (gui.MIN_WINDOW_WIDTH, gui.MIN_WINDOW_HEIGHT)]
        self.assertIn((1024, 600), sizes)
        for family, font_size in layout.FONT_MATRIX:
            for state in layout.UI_STATES:
                window = self.pseudo_window(font_size, state, family)
                for width, height in sizes:
                    with self.subTest(font=(family, font_size), state=state, size=(width, height)):
                        self.settle(window, width, height)
                        self.assert_no_page_scrollbar(window)
                        self.assert_client_size(window, width, height)
                        self.assertEqual(layout.cut_off_texts(window), [], msg=self.font_context())
                        self.assert_controls_usable(window, must_be_in_viewport=True)


if __name__ == "__main__":
    unittest.main()
