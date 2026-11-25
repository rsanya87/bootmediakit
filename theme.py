"""Light/dark appearance for the BootMediaKit GUI (0.4.0 T2).

Rules (roadmap/0.4.0.md T2, docs/INVARIANTS.md C1):

* Colours in the style sheet are semantic tokens computed from the active
  QPalette, so a light, dark or high-contrast system palette is followed.
  The only fixed colours are the hues in ``STATUS_HUES`` (warning, error,
  success; adjusted for contrast against the palette at runtime) and the
  fallback ``DARK_PALETTE``; tests keep this list closed.
* No desktop-specific code: the system scheme comes from Qt
  (``QStyleHints.colorScheme``), else from an unambiguous palette. When the
  scheme cannot be determined, the window starts dark.
* A forced light/dark appearance first asks Qt
  (``QStyleHints.setColorScheme``); only if the palette does not follow is
  the Fusion style with an own palette used. In "system" mode the native
  style stays.
* The choice ("system", "light", "dark") is stored with QSettings on the
  GUI side only; the root worker never reads user settings.

The contrast targets (4.5:1 for normal text, 3:1 for large text and
non-text indicators) are engineering goals taken from WCAG 2.x AA, not a
claim of legal conformance.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QObject, QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QStyleFactory

THEME_MODES = ("system", "light", "dark")
SETTINGS_KEY = "appearance/theme"
DEFAULT_MODE = "system"

TEXT_CONTRAST = 4.5
LARGE_TEXT_CONTRAST = 3.0
NON_TEXT_CONTRAST = 3.0

# Allowed fixed colours (the exception list of the "no fixed colour" test).
STATUS_HUES = {
    "warning": "#c27c0e",
    "error": "#d03b3b",
    "success": "#2e9b4f",
}
DARK_PALETTE = {
    "Window": "#202326",
    "WindowText": "#eceff1",
    "Base": "#17191b",
    "AlternateBase": "#2a2e32",
    "ToolTipBase": "#2a2e32",
    "ToolTipText": "#eceff1",
    "PlaceholderText": "#a3abb3",
    "Text": "#eceff1",
    "Button": "#2a2e32",
    "ButtonText": "#eceff1",
    "BrightText": "#ff6b6b",
    "Light": "#3a3f44",
    "Midlight": "#30353a",
    "Mid": "#5c646c",
    "Dark": "#121416",
    "Shadow": "#000000",
    "Highlight": "#3d8fd6",
    "HighlightedText": "#ffffff",
    "Link": "#6cb4f0",
    "LinkVisited": "#b48ef0",
}
DARK_PALETTE_DISABLED = {
    "WindowText": "#80878e",
    "Text": "#80878e",
    "ButtonText": "#80878e",
    "Highlight": "#3a4148",
    "HighlightedText": "#a3abb3",
}


def tr(text: str) -> str:
    """Translatable GUI text; the Hungarian source text is the key (0.4.0 T5)."""
    return QCoreApplication.translate("BootMediaKit", text)


# -- colour arithmetic ----------------------------------------------------

def _channel(value: float) -> float:
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: QColor) -> float:
    """WCAG 2.x relative luminance of an sRGB colour (alpha ignored)."""
    return (
        0.2126 * _channel(color.redF())
        + 0.7152 * _channel(color.greenF())
        + 0.0722 * _channel(color.blueF())
    )


def contrast_ratio(first: QColor, second: QColor) -> float:
    a, b = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def blend(first: QColor, second: QColor, amount: float) -> QColor:
    """Mix ``amount`` (0..1) of ``second`` into ``first``."""
    amount = max(0.0, min(1.0, amount))
    return QColor.fromRgbF(
        first.redF() + (second.redF() - first.redF()) * amount,
        first.greenF() + (second.greenF() - first.greenF()) * amount,
        first.blueF() + (second.blueF() - first.blueF()) * amount,
    )


def ensure_contrast(color: QColor, background: QColor, target: float) -> QColor:
    """Move ``color`` towards black or white until it reaches ``target``."""
    if contrast_ratio(color, background) >= target:
        return QColor(color)
    candidates = []
    for extreme in (QColor(0, 0, 0), QColor(255, 255, 255)):
        for step in range(1, 21):
            mixed = blend(color, extreme, step / 20)
            if contrast_ratio(mixed, background) >= target:
                candidates.append((step, mixed))
                break
    if candidates:
        return min(candidates, key=lambda item: item[0])[1]
    black, white = QColor(0, 0, 0), QColor(255, 255, 255)
    return black if contrast_ratio(black, background) >= contrast_ratio(white, background) else white


def best_text_on(background: QColor) -> QColor:
    black, white = QColor(0, 0, 0), QColor(255, 255, 255)
    return black if contrast_ratio(black, background) >= contrast_ratio(white, background) else white


# -- palettes and detection -----------------------------------------------

def classify_palette(palette: QPalette) -> str | None:
    """'dark' or 'light' only when the palette is unambiguous, else None."""
    window = relative_luminance(palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window))
    text = relative_luminance(palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText))
    ratio = (max(window, text) + 0.05) / (min(window, text) + 0.05)
    if ratio < TEXT_CONTRAST:
        return None
    if window <= 0.18 and text >= 0.4:
        return "dark"
    if window >= 0.45 and text <= 0.2:
        return "light"
    return None


def qt_color_scheme(app: QApplication) -> str | None:
    """The scheme Qt reports (Qt 6.5+), or None when unknown/unavailable."""
    hints = app.styleHints()
    getter = getattr(hints, "colorScheme", None)
    scheme_enum = getattr(Qt, "ColorScheme", None)
    if getter is None or scheme_enum is None:
        return None
    try:
        scheme = getter()
    except (RuntimeError, TypeError):
        return None
    if scheme == scheme_enum.Dark:
        return "dark"
    if scheme == scheme_enum.Light:
        return "light"
    return None


def detect_system_scheme(app: QApplication) -> str | None:
    return qt_color_scheme(app) or classify_palette(app.palette())


def dark_palette() -> QPalette:
    palette = QPalette()
    for role_name, value in DARK_PALETTE.items():
        role = getattr(QPalette.ColorRole, role_name)
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
            palette.setColor(group, role, QColor(value))
    for role_name, value in DARK_PALETTE_DISABLED.items():
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role_name), QColor(value))
    return palette


def light_palette() -> QPalette:
    style = QStyleFactory.create("Fusion")
    return style.standardPalette() if style is not None else QPalette()


# -- tokens and style sheet ------------------------------------------------

def _role(palette: QPalette, role: QPalette.ColorRole) -> QColor:
    return palette.color(QPalette.ColorGroup.Active, role)


def compute_tokens(palette: QPalette) -> dict[str, QColor]:
    """Semantic colours derived from the palette, adjusted for contrast."""
    window = _role(palette, QPalette.ColorRole.Window)
    text = _role(palette, QPalette.ColorRole.WindowText)
    base = _role(palette, QPalette.ColorRole.Base)
    base_text = _role(palette, QPalette.ColorRole.Text)
    highlight = _role(palette, QPalette.ColorRole.Highlight)
    mid = _role(palette, QPalette.ColorRole.Mid)
    dark = classify_palette(palette) == "dark" or relative_luminance(window) < 0.18

    tokens: dict[str, QColor] = {
        "window": window,
        "text": ensure_contrast(text, window, TEXT_CONTRAST),
        "base": base,
        "base_text": ensure_contrast(base_text, base, TEXT_CONTRAST),
    }
    secondary = blend(text, window, 0.3)
    tokens["secondary_text"] = ensure_contrast(ensure_contrast(secondary, window, TEXT_CONTRAST), base, TEXT_CONTRAST)
    tokens["accent_text"] = ensure_contrast(highlight, window, TEXT_CONTRAST)
    border = ensure_contrast(mid, window, NON_TEXT_CONTRAST)
    tokens["border"] = ensure_contrast(border, base, NON_TEXT_CONTRAST)
    tokens["focus"] = ensure_contrast(ensure_contrast(highlight, window, NON_TEXT_CONTRAST), base, NON_TEXT_CONTRAST)
    tokens["selected_bg"] = blend(window, highlight, 0.18)
    tokens["selected_text"] = ensure_contrast(text, tokens["selected_bg"], TEXT_CONTRAST)
    tokens["hover_bg"] = blend(window, text, 0.06)

    primary_text = best_text_on(highlight)
    tokens["primary_text"] = primary_text
    tokens["primary_bg"] = ensure_contrast(highlight, primary_text, TEXT_CONTRAST)
    tokens["progress_chunk"] = ensure_contrast(highlight, base, NON_TEXT_CONTRAST)
    tokens["disabled_bg"] = blend(window, text, 0.14)
    tokens["disabled_text"] = ensure_contrast(blend(text, window, 0.5), tokens["disabled_bg"], NON_TEXT_CONTRAST)

    for name, hue in STATUS_HUES.items():
        color = QColor(hue)
        if dark:
            color = blend(color, QColor(255, 255, 255), 0.25)
        tokens[f"{name}_text"] = ensure_contrast(color, window, TEXT_CONTRAST)
        tokens[f"{name}_icon"] = ensure_contrast(color, window, NON_TEXT_CONTRAST)
    tokens["warning_bg"] = blend(window, QColor(STATUS_HUES["warning"]), 0.12)
    tokens["warning_border"] = ensure_contrast(tokens["warning_icon"], tokens["warning_bg"], NON_TEXT_CONTRAST)
    tokens["warning_panel_text"] = ensure_contrast(text, tokens["warning_bg"], TEXT_CONTRAST)
    tokens["warning_panel_icon"] = ensure_contrast(tokens["warning_icon"], tokens["warning_bg"], LARGE_TEXT_CONTRAST)
    return tokens


# Token pairs whose contrast the tests check: (foreground, background, target).
CONTRAST_PAIRS = (
    ("text", "window", TEXT_CONTRAST),
    ("base_text", "base", TEXT_CONTRAST),
    ("secondary_text", "window", TEXT_CONTRAST),
    ("secondary_text", "base", TEXT_CONTRAST),
    ("accent_text", "window", TEXT_CONTRAST),
    ("selected_text", "selected_bg", TEXT_CONTRAST),
    ("primary_text", "primary_bg", TEXT_CONTRAST),
    ("border", "window", NON_TEXT_CONTRAST),
    ("border", "base", NON_TEXT_CONTRAST),
    ("focus", "window", NON_TEXT_CONTRAST),
    ("focus", "base", NON_TEXT_CONTRAST),
    ("progress_chunk", "base", NON_TEXT_CONTRAST),
    ("disabled_text", "disabled_bg", NON_TEXT_CONTRAST),
    ("warning_text", "window", TEXT_CONTRAST),
    ("error_text", "window", TEXT_CONTRAST),
    ("success_text", "window", TEXT_CONTRAST),
    ("warning_icon", "window", NON_TEXT_CONTRAST),
    ("error_icon", "window", NON_TEXT_CONTRAST),
    ("success_icon", "window", NON_TEXT_CONTRAST),
    ("warning_panel_text", "warning_bg", TEXT_CONTRAST),
    ("warning_panel_icon", "warning_bg", LARGE_TEXT_CONTRAST),
    ("warning_border", "warning_bg", NON_TEXT_CONTRAST),
)

STYLE_TEMPLATE = """
QMainWindow {{ background: {window}; }}
QLabel#appTitle {{ font-size: 27px; font-weight: 750; }}
QLabel#subtitle {{ color: {secondary_text}; font-size: 9pt; }}
QLabel#muted {{ color: {secondary_text}; }}
QLabel#version {{ color: {accent_text}; font-size: 9pt; font-weight: 650; padding-right: 10px; }}
QLabel#sectionTitle {{ font-size: 15px; font-weight: 650; }}
QLabel#status {{ font-weight: 600; }}
QLabel#status[state="success"] {{ color: {success_text}; }}
QLabel#status[state="error"] {{ color: {error_text}; }}
QLabel#status[state="warning"] {{ color: {warning_text}; }}
QLabel#elapsed {{ color: {accent_text}; font-weight: 650; border: 1px solid {border}; border-radius: 7px; padding: 3px 8px; min-height: 24px; max-height: 24px; }}
QToolButton#infoButton {{ color: {accent_text}; border: 1px solid {focus}; border-radius: 10px; font-weight: 750; font-size: 10pt; padding: 0; }}
QToolButton#infoButton:hover {{ background: {hover_bg}; }}
QToolButton#infoButton:disabled {{ color: {disabled_text}; border-color: {disabled_text}; }}
QToolButton#themeButton {{ border: 1px solid {border}; border-radius: 7px; padding: 3px 21px 3px 3px; }}
QToolButton#themeButton::menu-button {{ width: 16px; border-left: 1px solid {border}; }}
QToolButton#themeButton:hover {{ background: {hover_bg}; border-color: {focus}; }}
QToolButton#themeButton:focus {{ border: 2px solid {focus}; }}
QFrame#panel {{ border: 1px solid {border}; border-radius: 11px; }}
QFrame#warningPanel {{ border: 1px solid {warning_border}; border-radius: 10px; background: {warning_bg}; }}
QFrame#warningPanel QLabel {{ color: {warning_panel_text}; }}
QLabel#warningIcon {{ font-size: 21px; font-weight: 700; color: {warning_panel_icon}; }}
QLineEdit, QComboBox, QPlainTextEdit {{ border: 1px solid {border}; border-radius: 7px; padding: 5px 7px; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 2px solid {focus}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {disabled_text}; }}
QComboBox {{ min-height: 20px; }}
QPushButton {{ border: 1px solid {border}; border-radius: 7px; padding: 6px 10px; }}
QPushButton:hover {{ border-color: {focus}; }}
QPushButton:focus {{ border: 2px solid {focus}; }}
QPushButton:disabled {{ color: {disabled_text}; }}
QPushButton#modeButton {{ text-align: left; padding: 7px 10px; min-height: 32px; }}
QPushButton#modeButton:checked {{ border: 2px solid {focus}; background: {selected_bg}; color: {selected_text}; font-weight: 650; }}
QPushButton#primaryButton {{ background: {primary_bg}; color: {primary_text}; font-weight: 700; border: none; padding: 8px 16px; }}
QPushButton#primaryButton:focus {{ border: 2px solid {focus}; }}
QPushButton#primaryButton:disabled {{ background: {disabled_bg}; color: {disabled_text}; }}
QProgressBar {{ border: 1px solid {border}; border-radius: 6px; text-align: center; min-height: 18px; }}
QProgressBar::chunk {{ background: {progress_chunk}; border-radius: 5px; }}
QCheckBox {{ spacing: 8px; }}
"""


def build_stylesheet(tokens: dict[str, QColor]) -> str:
    return STYLE_TEMPLATE.format(**{name: color.name() for name, color in tokens.items()})


# -- icons -------------------------------------------------------------------

def _pixmap(size: int, ratio: float) -> QPixmap:
    pixmap = QPixmap(max(1, round(size * ratio)), max(1, round(size * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def theme_icon(scheme: str, color: QColor, size: int = 20, ratio: float = 1.0) -> QIcon:
    """Drawn sun (light) or moon (dark) icon; independent of icon themes and fonts."""
    pixmap = _pixmap(size, ratio)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    centre = QPointF(size / 2, size / 2)
    if scheme == "light":
        painter.setPen(QPen(color, max(1.5, size / 12), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(color)
        painter.drawEllipse(centre, size * 0.2, size * 0.2)
        for index in range(8):
            painter.save()
            painter.translate(centre)
            painter.rotate(index * 45)
            painter.drawLine(QPointF(0, -size * 0.32), QPointF(0, -size * 0.44))
            painter.restore()
    else:
        outer = QPainterPath()
        outer.addEllipse(centre, size * 0.38, size * 0.38)
        bite = QPainterPath()
        bite.addEllipse(QPointF(size * 0.66, size * 0.36), size * 0.32, size * 0.32)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(outer.subtracted(bite))
    painter.end()
    return QIcon(pixmap)


STATUS_STATES = ("idle", "progress", "success", "warning", "error")


def status_icon_pixmap(state: str, tokens: dict[str, QColor], size: int = 16, ratio: float = 1.0) -> QPixmap:
    """Shape-coded status icon: the state is not told by colour alone."""
    pixmap = _pixmap(size, ratio)
    if state == "idle":
        return pixmap
    color = {
        "progress": tokens["focus"],
        "success": tokens["success_icon"],
        "warning": tokens["warning_icon"],
        "error": tokens["error_icon"],
    }[state]
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, max(1.6, size / 9), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    inset = size * 0.1
    box = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    if state == "progress":
        painter.drawArc(box, 90 * 16, -270 * 16)
    elif state == "success":
        painter.drawEllipse(box)
        path = QPainterPath(QPointF(size * 0.3, size * 0.52))
        path.lineTo(size * 0.45, size * 0.67)
        path.lineTo(size * 0.71, size * 0.36)
        painter.drawPath(path)
    elif state == "error":
        painter.drawEllipse(box)
        painter.drawLine(QPointF(size * 0.35, size * 0.35), QPointF(size * 0.65, size * 0.65))
        painter.drawLine(QPointF(size * 0.65, size * 0.35), QPointF(size * 0.35, size * 0.65))
    elif state == "warning":
        path = QPainterPath(QPointF(size / 2, inset))
        path.lineTo(size - inset, size - inset)
        path.lineTo(inset, size - inset)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(size / 2, size * 0.4), QPointF(size / 2, size * 0.62))
        painter.drawPoint(QPointF(size / 2, size * 0.76))
    painter.end()
    return pixmap


def status_accessible_name(state: str) -> str:
    return {
        "idle": tr("Állapot: készen áll"),
        "progress": tr("Állapot: folyamatban"),
        "success": tr("Állapot: sikeres"),
        "warning": tr("Állapot: figyelmeztetés"),
        "error": tr("Állapot: hiba"),
    }[state]


# -- controller ---------------------------------------------------------------

def open_settings() -> QSettings:
    """Per-user GUI settings (~/.config/BootMediaKit/BootMediaKit.conf)."""
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "BootMediaKit", "BootMediaKit")


class ThemeController(QObject):
    """Owns the appearance mode and applies it to the QApplication."""

    changed = Signal()

    def __init__(self, app: QApplication, settings: QSettings) -> None:
        super().__init__(app)
        self.app = app
        self.settings = settings
        stored = str(settings.value(SETTINGS_KEY, DEFAULT_MODE) or DEFAULT_MODE)
        self.mode = stored if stored in THEME_MODES else DEFAULT_MODE
        self.scheme = "dark"
        # "system": follows the system; "manual": user override;
        # "fallback": the system scheme could not be determined.
        self.source = "system"
        self._native_style = app.style().name()
        self._own_palette = False
        self._native_forced = False
        self._applying = False
        hints = app.styleHints()
        signal = getattr(hints, "colorSchemeChanged", None)
        if signal is not None:
            signal.connect(self._system_scheme_changed)

    # -- public API --------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        if mode not in THEME_MODES:
            raise ValueError(f"ismeretlen megjelenési mód: {mode!r}")
        self.mode = mode
        self.settings.setValue(SETTINGS_KEY, mode)
        self.settings.sync()
        self.apply()

    def toggle(self) -> None:
        """The quick switch: flip the current appearance as a manual override."""
        self.set_mode("light" if self.scheme == "dark" else "dark")

    def apply(self) -> None:
        if self._applying:
            return
        self._applying = True
        try:
            if self.mode == "system":
                self._release()
                detected = detect_system_scheme(self.app)
                if detected is None:
                    self.source = "fallback"
                    self._force("dark")
                    self.scheme = "dark"
                else:
                    self.source = "system"
                    self.scheme = detected
            else:
                self.source = "manual"
                self._force(self.mode)
                self.scheme = self.mode
        finally:
            self._applying = False
        self.changed.emit()

    def palette_changed(self) -> None:
        """The application palette changed (system theme switch)."""
        if self._applying or self.mode != "system" or self.source == "fallback":
            return
        detected = detect_system_scheme(self.app)
        if detected is not None and detected != self.scheme:
            self.scheme = detected
        self.changed.emit()

    def tokens(self) -> dict[str, QColor]:
        return compute_tokens(self.app.palette())

    def uses_own_palette(self) -> bool:
        return self._own_palette

    # -- internals ---------------------------------------------------------
    def _system_scheme_changed(self, *_args) -> None:
        if self.mode == "system" and not self._applying:
            self.apply()

    def _force(self, scheme: str) -> None:
        hints = self.app.styleHints()
        setter = getattr(hints, "setColorScheme", None)
        scheme_enum = getattr(Qt, "ColorScheme", None)
        if setter is not None and scheme_enum is not None and not self._own_palette:
            setter(scheme_enum.Dark if scheme == "dark" else scheme_enum.Light)
            self._native_forced = True
            QCoreApplication.processEvents()
            if classify_palette(self.app.palette()) == scheme:
                return
        # The platform did not follow: Fusion with an own palette.
        if self.app.style().name().lower() != "fusion":
            self.app.setStyle("Fusion")
        self.app.setPalette(dark_palette() if scheme == "dark" else light_palette())
        self._own_palette = True

    def _release(self) -> None:
        if self._native_forced:
            unset = getattr(self.app.styleHints(), "unsetColorScheme", None)
            if unset is not None:
                unset()
            self._native_forced = False
        if self._own_palette:
            self.app.setStyle(self._native_style)
            self.app.setPalette(QPalette())
            self._own_palette = False
