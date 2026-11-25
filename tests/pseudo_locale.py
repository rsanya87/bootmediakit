"""Pseudo-locale for layout tests (T5); test helper, not installed.

Every user-visible text becomes about 40 % longer, with accented letters,
so a later translation (English is usually longer than the Hungarian
source) cannot break the layout unnoticed. Two routes are covered:

* texts that go through ``tr()`` / ``QCoreApplication.translate`` get the
  pseudo text from an installed ``PseudoTranslator``;
* the older texts that do not use ``tr()`` yet (to be converted later, see ROADMAP.md)
  are replaced on the widgets by ``pseudo_localize_widgets``.

Markup is kept: rich-text tags, ``{placeholders}``, ``&entities;``,
``%1``-style arguments and line breaks are not changed.
"""

from __future__ import annotations

import math
import re

from PySide6.QtCore import QTranslator
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

EXPANSION = 0.4
START, END = "‹", "›"
_ACCENTS = str.maketrans(
    "aeiouyAEIOUYcnszCNSZ",
    "áéíóúýÁÉÍÓÚÝçñšžÇÑŠŽ",
)
_FILLER = ("Őű", "ÉÁő", "Üñé", "Øíä", "Ŵçé", "Ëõ")
_PROTECTED = re.compile(r"(<[^>]*>|\{[^{}]*\}|&[A-Za-z#0-9]+;|%\d+|\n)")


def _visible_length(text: str) -> int:
    return sum(len(part) for part in _PROTECTED.split(text) if part and not _PROTECTED.fullmatch(part))


def pseudo(text: str, expansion: float = EXPANSION) -> str:
    """Return the pseudo-localised form of *text* (idempotent)."""
    if not text or text.startswith(START):
        return text
    letters = sum(ch.isalpha() for ch in text)
    if letters < 2:
        # One-letter or symbol-only texts ("i", "⚠") stay as they are.
        return text
    parts = _PROTECTED.split(text)
    accented = "".join(
        part if _PROTECTED.fullmatch(part) else part.translate(_ACCENTS) for part in parts if part
    )
    target = math.ceil(_visible_length(text) * (1 + expansion))
    filler = []
    length = _visible_length(accented) + 2
    index = 0
    while length < target:
        word = _FILLER[index % len(_FILLER)]
        filler.append(word)
        length += len(word) + 1
        index += 1
    suffix = (" " + " ".join(filler)) if filler else ""
    # Keep a trailing closing tag (rich text) after the filler.
    tail = re.search(r"(</[^>]+>\s*)+$", accented)
    if tail:
        body, end_tags = accented[: tail.start()], accented[tail.start():]
    else:
        body, end_tags = accented, ""
    return f"{START}{body}{suffix}{END}{end_tags}"


class PseudoTranslator(QTranslator):
    """Answers every ``tr()`` lookup with the pseudo text."""

    def isEmpty(self) -> bool:  # noqa: N802 - Qt naming
        return False

    def translate(self, context, source_text, disambiguation=None, n=-1):  # noqa: D401
        return pseudo(source_text)


def pseudo_localize_widgets(root: QWidget) -> int:
    """Replace the texts on *root* and its children; return how many changed."""
    changed = 0

    def swap(getter, setter):
        nonlocal changed
        old = getter()
        new = pseudo(old)
        if new != old:
            setter(new)
            changed += 1

    widgets = [root, *root.findChildren(QWidget)]
    for widget in widgets:
        if isinstance(widget, QLabel):
            swap(widget.text, widget.setText)
        elif isinstance(widget, QAbstractButton):
            swap(widget.text, widget.setText)
        elif isinstance(widget, QGroupBox):
            swap(widget.title, widget.setTitle)
        if isinstance(widget, (QLineEdit, QPlainTextEdit, QTextEdit)):
            swap(widget.placeholderText, widget.setPlaceholderText)
        if isinstance(widget, QComboBox):
            for item in range(widget.count()):
                swap(
                    lambda item=item: widget.itemText(item),
                    lambda value, item=item: widget.setItemText(item, value),
                )
        swap(widget.toolTip, widget.setToolTip)
    swap(root.windowTitle, root.setWindowTitle)
    return changed
