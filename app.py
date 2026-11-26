#!/usr/bin/env python3
"""BootMediaKit - a native Linux bootable USB creator for Arch-based Linux.

The GUI deliberately runs unprivileged. Only the narrowly-scoped worker is
launched via pkexec when the user confirms a destructive operation.
"""

from __future__ import annotations

import html
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QProcess, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QFont, QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QToolButton,
    QWidget,
)

from iso_utils import is_windows_install_iso
from theme import (
    ThemeController,
    build_stylesheet,
    open_settings,
    status_accessible_name,
    status_icon_pixmap,
    theme_icon,
    tr,
)
from ui_helpers import (
    bios_grub_available,
    choose_layout_profile,
    clamp_minimum_size,
    fit_rect_into_area,
    density_for,
    format_elapsed_time,
    initial_window_size,
    usable_work_area,
)
from version import __version__

APP_VERSION = __version__
APP_NAME = "BootMediaKit"
PRIVILEGED_WRAPPER = Path("/usr/libexec/bootmediakit/bootmediakit-worker")
APP_ICON = Path(__file__).with_name("bootmediakit.svg")


def human_size(value: int | float) -> str:
    size = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TiB"


def run_lsblk() -> list[dict[str, Any]]:
    command = [
        "lsblk", "--json", "--bytes", "--paths", "--tree",
        "--output",
        "PATH,NAME,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,RM,RO,MAJ:MIN,"
        "PKNAME,FSTYPE,LABEL,PARTTYPE,PARTLABEL,MOUNTPOINTS",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
    return json.loads(result.stdout).get("blockdevices", [])


def read_diskseq(maj_min: str) -> str:
    try:
        return (Path("/sys/dev/block") / maj_min / "diskseq").read_text(encoding="ascii").strip()
    except OSError:
        return ""


def device_by_id(path: str) -> str:
    wanted = os.path.realpath(path)
    directory = Path("/dev/disk/by-id")
    try:
        matches = sorted(
            str(entry) for entry in directory.iterdir()
            if entry.is_symlink() and os.path.realpath(entry) == wanted
        )
    except OSError:
        return ""
    return next((item for item in matches if "-part" not in Path(item).name), matches[0] if matches else "")


def flatten_partitions(node: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for child in node.get("children") or []:
        result.append(child)
        result.extend(flatten_partitions(child))
    return result


def disk_identity(disk: dict[str, Any]) -> dict[str, Any]:
    path = str(disk.get("path") or "")
    maj_min = str(disk.get("maj:min") or "")
    return {
        "path": path,
        "size": int(disk.get("size") or 0),
        "model": str(disk.get("model") or ""),
        "serial": str(disk.get("serial") or "").strip(),
        "wwn": str(disk.get("wwn") or "").strip(),
        "tran": str(disk.get("tran") or "").strip().lower(),
        "rm": disk.get("rm") is True or str(disk.get("rm")).lower() in {"1", "true"},
        "maj_min": maj_min,
        "diskseq": read_diskseq(maj_min),
        "by_id": device_by_id(path),
    }


def unsafe_layout_reason(disk: dict[str, Any]) -> str:
    unsafe_types = {"crypt", "lvm", "raid", "raid0", "raid1", "raid5", "raid6", "raid10", "mpath"}
    unsafe_fs = {"crypto_luks", "lvm2_member", "swap", "linux_raid_member", "isw_raid_member", "ddf_raid_member"}
    identity = disk_identity(disk)
    if not any(identity.get(key) for key in ("serial", "wwn", "diskseq", "by_id")):
        return "Nem írható cél: a meghajtóhoz nem található stabil fizikai azonosító."
    for part in flatten_partitions(disk):
        kind = str(part.get("type") or "").lower()
        fstype = str(part.get("fstype") or "").lower()
        if kind in unsafe_types or fstype in unsafe_fs:
            return (
                f"Nem írható cél: védett/összetett kötet található "
                f"({part.get('path')}, {fstype or kind}, {part.get('label') or 'nincs címke'}). "
                "A LUKS/LVM/RAID/swap réteget előbb külön kell kezelni."
            )
    return ""


def mounted_paths(node: dict[str, Any]) -> list[str]:
    found: list[str] = []
    values = node.get("mountpoints") or []
    if isinstance(values, str):
        values = [values]
    for item in values:
        if item:
            found.append(str(item))
    for child in node.get("children") or []:
        found.extend(mounted_paths(child))
    return found



# Minimum logical client size (T3, layout work). Measured offscreen with the
# two-column layout at 880 px width in every visible state (RAW, Windows
# without ISO, Windows UEFI, Windows Legacy, and both with the "Legacy nem
# elérhető" hint), with both test fonts (TESTED_FONT_FAMILIES in
# tests/test_layout.py): with the compact spacing tightened in T5, at most
# 524 px high with a 9 pt and a 10 pt font. The first value, 540, was
# measured in the start-up state only and was 8 px short after a mode change
# (548 px needed then). It fits
# the work area of a 1280x800 screen at 100 % and 125 % scaling (1280x800 and
# 1024x640 logical, minus a 44 px panel and a 40 px window frame: at most
# 556 px). Larger fonts can need more; the content then scrolls as a last
# resort. The minimum is never larger than the available area.
MIN_WINDOW_WIDTH = 880
MIN_WINDOW_HEIGHT = 550

# After a work-area change on Wayland the compositor may answer the window's
# new size with its old one: KWin sends xdg_toplevel.configure with the size
# from before the output change in the same batch, and Qt applies it after our
# resize (docs/LESSONS.md, docs/TESTING.md). For this long after fitting the
# window, a resize from outside that is larger than the work area is undone,
# at most COMPOSITOR_RESIZE_CORRECTIONS times per change. Measured on KDE
# Plasma: the old size arrived 1 ms after our resize; the limit leaves room
# for a slow or busy machine (a VM) and is restarted after each correction.
COMPOSITOR_RESIZE_GUARD_MS = 2000
COMPOSITOR_RESIZE_CORRECTIONS = 2

# Ctrl+C in the terminal reaches the GUI and pkexec (one process group). With
# Python's default handler the pending KeyboardInterrupt crashed PySide when
# the QProcess.finished slot ran (SIGSEGV, docs/LESSONS.md). The GUI's own
# handler only sets a flag; this timer lets Python run it while the Qt loop
# idles and does the work on the approved close path. A handler, not SIG_IGN:
# children get the default action back on exec, so pkexec still stops.
TERMINAL_INTERRUPT_POLL_MS = 200
EXIT_INTERRUPTED = 130


class ElidedLabel(QLabel):
    """One-line label that shortens long text with "…" instead of clipping."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._auto_tooltip = False
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full_text = text or ""
        self._elide()

    def text(self) -> str:
        return self._full_text

    def setToolTip(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._auto_tooltip = False
        super().setToolTip(text)

    def is_elided(self) -> bool:
        return super().text() != self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._elide()

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint

    def _elide(self) -> None:
        width = max(0, self.contentsRect().width())
        shown = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideMiddle, width)
        QLabel.setText(self, shown)
        if shown != self._full_text and (self._auto_tooltip or not self.toolTip()):
            QLabel.setToolTip(self, self._full_text)
            self._auto_tooltip = True
        elif shown == self._full_text and self._auto_tooltip:
            QLabel.setToolTip(self, "")
            self._auto_tooltip = False


class CheckBoxLabel(QLabel):
    """Wrapping text of a WrappingCheckBox; a click toggles the check box."""

    def __init__(self, check_box: QCheckBox) -> None:
        super().__init__()
        self.setObjectName("checkBoxLabel")
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setBuddy(check_box)
        self.setProperty("checkFocus", False)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        check_box = self.buddy()
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
            and check_box is not None
            and check_box.isEnabled()
        ):
            check_box.setFocus(Qt.FocusReason.MouseFocusReason)
            check_box.click()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class WrappingCheckBox(QCheckBox):
    """Check box whose text wraps (QCheckBox text never does).

    The QCheckBox itself has no text; ``label`` shows it and must be put next
    to the box in the layout. ``text()``/``setText()`` keep the QCheckBox API,
    the accessible name is the full text, focus and the Space key stay on the
    check box, and the label follows its enabled state (T5, pseudo-locale work).
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = ""
        self.label = CheckBoxLabel(self)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._text = text or ""
        self.label.setText(self._text)
        self.setAccessibleName(self._text)

    def text(self) -> str:
        return self._text

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self.label.setEnabled(self.isEnabled())

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().focusInEvent(event)
        self._show_focus(True)

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().focusOutEvent(event)
        self._show_focus(False)

    def _show_focus(self, focused: bool) -> None:
        # The focus frame of a check box is drawn around its text, which is
        # now in the label: mark the label instead.
        self.label.setProperty("checkFocus", focused)
        self.label.style().unpolish(self.label)
        self.label.style().polish(self.label)
        self.label.update()


class WrappingButton(QPushButton):
    """Checkable push button whose text wraps instead of being cut off.

    QPushButton never wraps, and a checked mode button is drawn bold, which
    its size hint does not account for; at narrow widths the end of the text
    was cut off. The QPushButton itself has no text; ``label`` shows it,
    bold when checked. ``text()``/``setText()`` keep the QPushButton API and
    the accessible name is the full text. Clicks go through the label to the
    button; focus, Space and the focus frame stay on the button.
    """

    CHECKED_WEIGHT = QFont.Weight(650)

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = ""
        self.label = QLabel(self)
        self.label.setObjectName("buttonLabel")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.setProperty("checked", False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.addWidget(self.label)
        self.toggled.connect(self._show_checked)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._text = text or ""
        self.label.setText(self._text)
        self.setAccessibleName(self._text)
        self.updateGeometry()

    def text(self) -> str:
        return self._text

    def label_font(self) -> QFont:
        # From the button's own (inherited) font, so system font changes apply.
        font = self.font()
        font.setWeight(self.CHECKED_WEIGHT if self.isChecked() else QFont.Weight.Normal)
        return font

    def _show_checked(self, checked: bool) -> None:
        self.label.setFont(self.label_font())
        self.label.setProperty("checked", checked)
        self.label.style().unpolish(self.label)
        self.label.style().polish(self.label)
        self.updateGeometry()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self.label.setEnabled(self.isEnabled())
        elif event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.label.setFont(self.label_font())

    def _margins(self) -> tuple[int, int]:
        margins = self.layout().contentsMargins()
        return margins.left() + margins.right(), margins.top() + margins.bottom()

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt naming
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt naming
        horizontal, vertical = self._margins()
        metrics = QFontMetrics(self.label_font())
        text_rect = metrics.boundingRect(
            0, 0, max(1, width - horizontal), 10_000, int(Qt.TextFlag.TextWordWrap), self._text
        )
        return max(self.minimumHeight(), text_rect.height() + vertical)

    def sizeHint(self):  # noqa: N802 - Qt naming
        horizontal, _vertical = self._margins()
        width = QFontMetrics(self.label_font()).horizontalAdvance(self._text) + horizontal
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        # The longest word must fit; the rest may wrap.
        horizontal, _vertical = self._margins()
        metrics = QFontMetrics(self.label_font())
        widest = max((metrics.horizontalAdvance(word) for word in self._text.split()), default=0)
        width = widest + horizontal
        return QSize(width, self.heightForWidth(width))


# pkexec(1), polkit 128: 126 = the user dismissed the authentication dialog;
# 127 = not authorized, no authorization obtained, or an error. Without a
# registered authentication agent pkexec tries its own textual agent, which
# fails without a terminal, so a missing agent also ends with 127. Only the
# exit code is used; pkexec's (possibly translated) text is only logged.
PKEXEC_DISMISSED = 126
PKEXEC_NOT_AUTHORIZED = 127


def describe_privilege_failure(exit_code: int) -> tuple[str, str, str]:
    """(status line, dialog title, dialog text) for a worker that never started.

    BootMediaKit brings no authentication agent of its own, starts none and
    never falls back to sudo (docs/INVARIANTS.md B1).
    """
    if exit_code == PKEXEC_DISMISSED:
        return (
            tr("A jogosultságkérés megszakítva; a célmeghajtóhoz nem nyúltunk."),
            tr("A hitelesítés megszakítva"),
            tr(
                "A jelszókérő ablakot bezártad vagy megszakítottad, ezért a művelet nem indult el. "
                "A célmeghajtóhoz nem nyúltunk.\n\n"
                "Ha folytatnád, indítsd újra a műveletet, és add meg a rendszergazdai jelszót."
            ),
        )
    if exit_code == PKEXEC_NOT_AUTHORIZED:
        return (
            tr("Nem sikerült rendszergazdai jogosultságot kapni; a célmeghajtóhoz nem nyúltunk."),
            tr("A hitelesítés nem sikerült"),
            tr(
                "A rendszer nem adott jogosultságot a lemezíráshoz (pkexec kilépési kód: 127), "
                "ezért a művelet nem indult el. A célmeghajtóhoz nem nyúltunk.\n\n"
                "Lehetséges okok:\n"
                "• Ebben a munkamenetben nem fut polkit hitelesítési ügynök, ezért nem jelent meg "
                "jelszókérő ablak. A legtöbb asztali környezet indít ilyet; minimális ablakkezelő "
                "vagy távoli munkamenet esetén külön kell elindítani.\n"
                "• A jelszó hibás volt, vagy a felhasználód nem jogosult rendszergazdai műveletre.\n"
                "• A polkit szolgáltatás nem fut.\n\n"
                "Mit tegyél: indítsd el a munkamenetedhez tartozó polkit hitelesítési ügynököt, vagy "
                "jelentkezz be egy olyan grafikus munkamenetbe, amely elindítja; ellenőrizd, hogy a "
                "felhasználód rendszergazdai jogosultságú; majd próbáld újra. "
                "A BootMediaKit nem indít saját ügynököt, és nem használ sudo-t."
            ),
        )
    return (
        tr("A jogosultságkérés vagy a worker indítása nem sikerült."),
        tr("A művelet nem indult el"),
        tr(
            "A rendszergazdai jogosultságkérés megszakadt/megtagadásra került, "
            "vagy a biztonságos worker nem indult el. A célmeghajtóhoz nem nyúltunk."
        ),
    )


class LogView(QPlainTextEdit):
    """Process log: asks only for its minimum height and takes the spare
    space; long logs scroll inside the box, never the window."""

    def sizeHint(self):  # noqa: N802 - Qt naming
        hint = super().sizeHint()
        hint.setHeight(self.minimumHeight())
        return hint


class MainWindow(QMainWindow):
    def __init__(self, theme_controller: ThemeController | None = None) -> None:
        super().__init__()
        if theme_controller is None:
            theme_controller = ThemeController(QApplication.instance(), open_settings())
            # Owned by this window, so it cannot outlive it and call into a
            # deleted window when the system palette changes.
            theme_controller.setParent(self)
            theme_controller.apply()
        self.theme = theme_controller
        self._status_state = "idle"
        self.setWindowTitle(f"{APP_NAME} – bootolható USB készítő")
        self._layout_profile = ""
        self._single_column_height = 0
        self._last_viewport: tuple[int, int] | None = None
        if APP_ICON.is_file():
            self.setWindowIcon(QIcon(str(APP_ICON)))
        self.process: QProcess | None = None
        self.output_buffer = ""
        self._worker_started = False
        self._target_modified = False
        self._operation_cancelled = False
        self._close_after_operation = False
        self.current_device: dict[str, Any] | None = None
        self._selected_mode = "raw"
        # Resolved path of the last image recognised as a Windows installer
        # ISO; the boot mode selector is only active for that image.
        self._windows_iso_path: str | None = None
        self._bios_grub_available = bios_grub_available()

        # Start timing on the first worker progress event, not while pkexec
        # is waiting for the user's authentication.
        self._operation_elapsed = QElapsedTimer()
        self._operation_timer_started = False
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self.update_elapsed_display)

        # Device discovery runs asynchronously so a slow USB controller cannot
        # block painting, input handling, or cancellation controls.
        self.lsblk_process = QProcess(self)
        self.lsblk_process.finished.connect(self._lsblk_finished)
        self.lsblk_process.errorOccurred.connect(self._lsblk_process_error)
        self._lsblk_request_active = False
        self._lsblk_preserve_selection = False
        self._lsblk_quiet = False
        self._lsblk_current_selection: dict[str, Any] | None = None
        # Last error logged by a silent (automatic) refresh; used to avoid
        # repeating the same log line every refresh interval.
        self._lsblk_last_quiet_error: str | None = None
        self.lsblk_timeout_timer = QTimer(self)
        self.lsblk_timeout_timer.setSingleShot(True)
        self.lsblk_timeout_timer.setInterval(5000)
        self.lsblk_timeout_timer.timeout.connect(self._lsblk_timed_out)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        self._root_layout = root_layout
        outer_margin = 12
        root_layout.setContentsMargins(
            outer_margin, outer_margin, outer_margin, outer_margin
        )
        root_layout.setSpacing(7)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("BootMediaKit")
        title.setObjectName("appTitle")
        meta_row = QHBoxLayout()
        version = QLabel(APP_VERSION)
        version.setObjectName("version")
        subtitle = QLabel("Bootolható USB-meghajtók készítése Linux alatt")
        subtitle.setObjectName("subtitle")
        meta_row.addWidget(version, 0, Qt.AlignmentFlag.AlignVCenter)
        meta_row.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignVCenter)
        meta_row.addStretch(1)
        title_block.addWidget(title)
        title_block.addLayout(meta_row)
        header.addLayout(title_block)
        header.addStretch(1)
        # Quick light/dark switch: the icon shows the current appearance, a
        # click switches to the other one (manual override), the menu restores
        # the system-following mode.
        self.theme_button = QToolButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setAutoRaise(False)
        self.theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.theme_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.theme_button.clicked.connect(self.theme.toggle)
        theme_menu = QMenu(self.theme_button)
        self.theme_actions: dict[str, QAction] = {}
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for mode, label in (
            ("system", tr("Rendszer / Automatikus")),
            ("light", tr("Világos")),
            ("dark", tr("Sötét")),
        ):
            action = QAction(label, theme_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=mode: self.theme.set_mode(value))
            theme_group.addAction(action)
            theme_menu.addAction(action)
            self.theme_actions[mode] = action
        self.theme_button.setMenu(theme_menu)
        header.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignTop)
        root_layout.addLayout(header)

        warning = QFrame()
        warning.setObjectName("warningPanel")
        warning_layout = QHBoxLayout(warning)
        warning_layout.setContentsMargins(
            10,
            7,
            10,
            7,
        )
        warning_icon = QLabel("⚠")
        warning_icon.setObjectName("warningIcon")
        warning_text = QLabel(
            "A kiválasztott USB-meghajtó teljes tartalma törlődik. "
            "A művelet előtt ellenőrizd a meghajtó típusát és kapacitását."
        )
        warning_text.setWordWrap(True)
        warning_layout.addWidget(warning_icon)
        warning_layout.addWidget(warning_text, 1)
        self._warning_layout = warning_layout
        root_layout.addWidget(warning)

        # Image selection
        image_card = QFrame()
        image_card.setObjectName("panel")
        image_layout = QVBoxLayout(image_card)
        image_layout.setContentsMargins(
            11,
            7,
            11,
            7,
        )
        image_layout.setSpacing(5)
        image_label = QLabel("1. Lemezkép kiválasztása")
        image_label.setObjectName("sectionTitle")
        image_layout.addWidget(image_label)
        image_row = QHBoxLayout()
        self.iso_edit = QLineEdit()
        self.iso_edit.setPlaceholderText("Válassz ISO / IMG / BIN fájlt…")
        self.iso_edit.setClearButtonEnabled(True)
        self.iso_edit.setAccessibleName(tr("Forrás lemezkép"))
        self.iso_edit.setMinimumHeight(32)
        self.iso_edit.setMinimumWidth(0)
        self.iso_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.browse_button = QPushButton("Tallózás…")
        self.browse_button.clicked.connect(self.choose_image)
        self._inspected_image: str | None = None
        self.iso_edit.textChanged.connect(lambda _text: self.update_boot_mode_controls())
        self.iso_edit.editingFinished.connect(self.inspect_typed_image)
        image_row.addWidget(self.iso_edit, 1)
        image_row.addWidget(self.browse_button)
        image_layout.addLayout(image_row)
        self.file_info = ElidedLabel("Támogatott formátumok: ISO, IMG, BIN, RAW")
        self.file_info.setObjectName("muted")
        self.file_info.setWordWrap(False)
        self.file_info.setMinimumWidth(0)
        self.file_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        image_layout.addWidget(self.file_info)
        self.image_card = image_card

        # Device selection
        device_card = QFrame()
        device_card.setObjectName("panel")
        device_layout = QVBoxLayout(device_card)
        device_layout.setContentsMargins(
            11,
            7,
            11,
            7,
        )
        device_layout.setSpacing(5)
        device_header = QHBoxLayout()
        device_title = QLabel("2. Célmeghajtó")
        device_title.setObjectName("sectionTitle")
        self.refresh_button = QPushButton("↻ Frissítés")
        self.refresh_button.clicked.connect(self.refresh_devices)
        device_header.addWidget(device_title)
        device_header.addStretch(1)
        device_header.addWidget(self.refresh_button)
        device_layout.addLayout(device_header)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(33)
        self.device_combo.setMinimumWidth(0)
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device_combo.setMinimumContentsLength(12)
        self.device_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.device_combo.currentIndexChanged.connect(self.device_changed)
        self.device_combo.setAccessibleName(tr("Célmeghajtó"))
        device_layout.addWidget(self.device_combo)
        self.device_detail = ElidedLabel("Csatlakoztass egy USB-meghajtót, majd frissítsd a listát.")
        self.device_detail.setObjectName("muted")
        self.device_detail.setWordWrap(False)
        self.device_detail.setMinimumWidth(0)
        self.device_detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        device_layout.addWidget(self.device_detail)

        partition_info_row = QHBoxLayout()
        partition_info_row.setSpacing(5)
        self.partition_info_label = QLabel("Partíció információk:")
        self.partition_info_label.setObjectName("muted")
        self.partition_info_label.setMinimumWidth(0)
        self.partition_info_button = QToolButton()
        self.partition_info_button.setObjectName("infoButton")
        self.partition_info_button.setText("i")
        self.partition_info_button.setAutoRaise(True)
        self.partition_info_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.partition_info_button.setFixedSize(20, 20)
        self.partition_info_button.setToolTip("A teljes partíciólista megjelenítése.")
        self.partition_info_button.setToolTipDuration(15000)
        self.partition_info_button.setAccessibleName("Partíció információk")
        partition_info_row.addWidget(self.partition_info_label)
        partition_info_row.addWidget(self.partition_info_button)
        partition_info_row.addStretch(1)
        device_layout.addLayout(partition_info_row)
        self.device_card = device_card

        # Mode selection
        mode_card = QFrame()
        mode_card.setObjectName("panel")
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(
            11,
            7,
            11,
            7,
        )
        mode_layout.setSpacing(5)
        mode_title = QLabel("3. Írási mód")
        mode_title.setObjectName("sectionTitle")
        mode_layout.addWidget(mode_title)

        self.raw_button = WrappingButton("Lemezkép közvetlen kiírása")
        self.raw_button.setCheckable(True)
        self.raw_button.setChecked(True)
        self.raw_button.setObjectName("modeButton")
        self.windows_button = WrappingButton("Windows telepítő (NTFS)")
        self.windows_button.setCheckable(True)
        self.windows_button.setObjectName("modeButton")
        self.raw_button.clicked.connect(lambda: self.select_mode("raw"))
        self.windows_button.clicked.connect(lambda: self.select_mode("windows"))
        for button in (self.raw_button, self.windows_button):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
            button.setMinimumHeight(34)
        mode_buttons = QHBoxLayout()
        mode_buttons.setSpacing(8)
        mode_buttons.addWidget(self.raw_button, 1)
        mode_buttons.addWidget(self.windows_button, 1)
        mode_layout.addLayout(mode_buttons)
        boot_mode_row = QHBoxLayout()
        boot_mode_row.setSpacing(8)
        self.boot_mode_label = QLabel("Indítási mód:")
        self.boot_mode_combo = QComboBox()
        self.boot_mode_combo.addItem("UEFI (GPT)", "uefi")
        self.boot_mode_combo.addItem("Legacy BIOS (MBR)", "bios")
        self.boot_mode_combo.setMinimumHeight(30)
        self.boot_mode_combo.currentIndexChanged.connect(self.boot_mode_changed)
        self.boot_mode_label.setBuddy(self.boot_mode_combo)
        self.grub_hint = ElidedLabel()
        self.grub_hint.setObjectName("muted")
        self.grub_hint.setMinimumWidth(0)
        self.grub_hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        boot_mode_row.addWidget(self.boot_mode_label)
        boot_mode_row.addWidget(self.boot_mode_combo)
        boot_mode_row.addWidget(self.grub_hint, 1)
        mode_layout.addLayout(boot_mode_row)
        self.boot_mode_note = QLabel(
            "A Legacy BIOS mód régebbi gépekhez készült. Az újabb Windows telepítők "
            "a hardverkövetelményeik miatt régi gépen megtagadhatják a telepítést."
        )
        self.boot_mode_note.setObjectName("muted")
        self.boot_mode_note.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.boot_mode_note.setWordWrap(True)
        self.boot_mode_note.setMinimumWidth(0)
        self.boot_mode_note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        mode_layout.addWidget(self.boot_mode_note)
        self.apply_grub_availability()
        self.mode_description = QLabel(
            "ISOHybrid Linux- és egyéb lemezképekhez. A teljes lemezkép közvetlenül "
            "az USB-re kerül; minden meglévő adat felülíródik."
        )
        self.mode_description.setObjectName("muted")
        self.mode_description.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.mode_description.setWordWrap(True)
        self.mode_description.setMinimumWidth(0)
        self.mode_description.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        mode_layout.addWidget(self.mode_description)
        self.verify_checkbox = WrappingCheckBox("Kiírás utáni teljes visszaolvasás és ellenőrzés")
        self.verify_checkbox.setChecked(True)
        verify_row = QHBoxLayout()
        verify_row.setSpacing(8)
        verify_row.addWidget(self.verify_checkbox, 0, Qt.AlignmentFlag.AlignTop)
        verify_row.addWidget(self.verify_checkbox.label, 1)
        mode_layout.addLayout(verify_row)
        self.mode_card = mode_card
        self.update_boot_mode_controls()

        # Progress / log
        progress_card = QFrame()
        progress_card.setObjectName("panel")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(
            11,
            7,
            11,
            7,
        )
        progress_layout.setSpacing(5)
        progress_header = QHBoxLayout()
        progress_title = QLabel("Művelet állapota")
        progress_title.setObjectName("sectionTitle")
        self.elapsed_label = QLabel("Eltelt idő: 00:00")
        self.elapsed_label.setObjectName("elapsed")
        self.elapsed_label.setToolTip("A pendrive-készítés tényleges futási ideje")
        self.elapsed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.elapsed_label.setMinimumWidth(120)
        self.elapsed_label.setFixedHeight(30)
        self.elapsed_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        progress_header.addWidget(progress_title)
        progress_header.addStretch(1)
        progress_header.addWidget(self.elapsed_label)
        progress_layout.addLayout(progress_header)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.status_icon = QLabel()
        self.status_icon.setObjectName("statusIcon")
        self.status_icon.setFixedSize(16, 16)
        self.status_label = QLabel("Készen áll.")
        self.status_label.setObjectName("status")
        self.status_label.setProperty("state", "idle")
        status_row.addWidget(self.status_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self.status_label, 1)
        progress_layout.addLayout(status_row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setAccessibleName(tr("Folyamatjelző"))
        progress_layout.addWidget(self.progress)
        self.log = LogView()
        self.log.setReadOnly(True)
        self.log.setAccessibleName(tr("Folyamatnapló"))
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(56)
        self.log.setMinimumWidth(0)
        # The log takes the spare height; it scrolls inside, the window does not.
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.log.setPlaceholderText("A műveletek és az ellenőrzés részletei itt jelennek meg.")
        progress_layout.addWidget(self.log)
        self.progress_card = progress_card
        self._card_layouts = (image_layout, device_layout, mode_layout, progress_layout)
        # The four cards sit in a grid: one column on tall screens, two
        # columns (settings left, progress and log right) on short ones.
        self.cards_widget = QWidget()
        self.cards_grid = QGridLayout(self.cards_widget)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.cards_widget, 1)

        footer = QHBoxLayout()
        self.about_label = ElidedLabel("Linux • helyi, nyílt forráskódú projekt")
        self.about_label.setObjectName("muted")
        self.about_label.setMinimumWidth(0)
        self.about_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.cancel_button = QPushButton("Megszakítás")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_operation)
        self.start_button = QPushButton("USB elkészítése")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumWidth(150)
        self.start_button.setMinimumHeight(38)
        self.cancel_button.setMinimumHeight(38)
        self.start_button.clicked.connect(self.start_operation)
        footer.addWidget(self.about_label, 1)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.start_button)
        root_layout.addLayout(footer)

        # Keep content inside the viewport; long ISO metadata wraps in its card.
        root.setMinimumWidth(0)
        root.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setWidget(root)
        self.setCentralWidget(scroll_area)
        self.scroll_area = scroll_area
        self.theme.changed.connect(self.apply_style)
        self.apply_style()
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(0)
        self._layout_timer.timeout.connect(self.update_layout_profile)
        self._measure_timer = QTimer(self)
        self._measure_timer.setSingleShot(True)
        self._measure_timer.setInterval(0)
        self._measure_timer.timeout.connect(self.measure_layout_profiles)
        self.measure_layout_profiles()
        self._own_resize = False
        self._interrupt_requested = False
        self._interrupt_handled = False
        self._size_guard_corrections = 0
        self._size_guard_timer = QTimer(self)
        self._size_guard_timer.setSingleShot(True)
        self._size_guard_timer.timeout.connect(self.stop_size_guard)
        self.setup_initial_geometry()
        self._watched_screen = None
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(5000)
        self.refresh_timer.timeout.connect(self.refresh_devices_silently)
        self.refresh_timer.start()
        self.refresh_devices()

    # -- responsive layout (T3, layout work) ---------------------------------
    def available_area(self) -> tuple[int, int, int, int]:
        """Logical work area (x, y, width, height) of the window's screen.

        The one place the work area is computed: the minimum size, the first
        size and the fitting after a screen or scale change all use it. On
        Wayland the panels are unknown to Qt, so a reserve is kept free
        (ui_helpers.usable_work_area); after the compositor's answer the
        layout works from the real window size (resizeEvent)."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return 0, 0, 1366, 768
        return usable_work_area(
            screen.geometry().getRect(),
            screen.availableGeometry().getRect(),
            wayland=self.on_wayland(),
        )

    @staticmethod
    def on_wayland() -> bool:
        return QApplication.platformName().lower().startswith("wayland")

    def frame_extra(self) -> tuple[int, int]:
        frame = self.frameGeometry()
        client = self.geometry()
        return max(0, frame.width() - client.width()), max(0, frame.height() - client.height())

    def minimum_client_size(self) -> tuple[int, int]:
        _x, _y, width, height = self.available_area()
        frame_width, frame_height = self.frame_extra()
        return clamp_minimum_size(
            (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT),
            (width - frame_width, height - frame_height),
        )

    def setup_initial_geometry(self) -> None:
        x, y, width, height = self.available_area()
        self.setMinimumSize(*self.minimum_client_size())
        initial_width, initial_height = initial_window_size(
            width, height, self._single_column_height, (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        )
        self.resize_by_program(max(initial_width, self.minimumWidth()), max(initial_height, self.minimumHeight()))
        self.move(
            x + max(0, (width - self.width()) // 2),
            y + max(0, (height - self.height()) // 2),
        )

    def fit_window_to_screen(self) -> None:
        """Fit the outer window frame inside the active screen's work area."""
        x, y, width, height = self.available_area()
        frame_width, frame_height = self.frame_extra()
        self.setMinimumSize(*self.minimum_client_size())
        initial_width, initial_height = initial_window_size(
            width, height, self._single_column_height, (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        )
        self.resize_by_program(
            max(self.minimumWidth(), initial_width - frame_width),
            max(self.minimumHeight(), initial_height - frame_height),
        )
        frame = self.frameGeometry()
        self.move(
            x + max(0, (width - frame.width()) // 2),
            y + max(0, (height - frame.height()) // 2),
        )

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        handle = self.windowHandle()
        if handle is not None and self._watched_screen is None:
            # The window can move to another screen, and a screen's work area
            # can change (undocking, a new resolution or scale) after start-up.
            handle.screenChanged.connect(self.on_screen_changed)
            self.on_screen_changed(self.screen())

    def on_screen_changed(self, screen) -> None:
        if self._watched_screen is not None:
            try:
                self._watched_screen.availableGeometryChanged.disconnect(self.adapt_to_screen)
            except (RuntimeError, TypeError):
                pass  # the old screen is already gone
        self._watched_screen = screen
        if screen is not None:
            screen.availableGeometryChanged.connect(self.adapt_to_screen)
        self.adapt_to_screen()

    def adapt_to_screen(self, *_args) -> None:
        """Keep the minimum and the window inside the current work area."""
        self.setMinimumSize(*self.minimum_client_size())
        frame = self.frameGeometry()
        current = (frame.x(), frame.y(), frame.width(), frame.height())
        x, y, width, height = fit_rect_into_area(current, self.available_area())
        if (width, height) != current[2:]:
            frame_width, frame_height = self.frame_extra()
            self.resize_by_program(width - frame_width, height - frame_height)
        if (x, y) != current[:2]:
            self.move(x, y)
        self.request_relayout()
        if self.on_wayland():
            self.start_size_guard()

    def resize_by_program(self, width: int, height: int) -> None:
        """Resize from our own code; the size guard only judges other resizes."""
        self._own_resize = True
        try:
            self.resize(width, height)
        finally:
            self._own_resize = False

    def start_size_guard(self) -> None:
        """Watch for the compositor's answer to the fitted size (Wayland only)."""
        self._size_guard_corrections = COMPOSITOR_RESIZE_CORRECTIONS
        self._size_guard_timer.start(COMPOSITOR_RESIZE_GUARD_MS)

    def stop_size_guard(self) -> None:
        self._size_guard_timer.stop()
        self._size_guard_corrections = 0

    def size_guard_active(self) -> bool:
        return self._size_guard_timer.isActive()

    def exceeds_work_area(self) -> bool:
        frame = self.frameGeometry()
        _x, _y, width, height = self.available_area()
        return frame.width() > width or frame.height() > height

    def check_outside_resize(self) -> None:
        """A resize not made by our code arrived while the guard watches.

        Larger than the work area: the compositor restored an old size, undo
        it (limited, so a compositor that insists cannot cause a loop). Fits:
        the compositor's answer has arrived, stop watching.
        """
        if not self.size_guard_active():
            return
        states = Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen
        if self.windowState() & states or not self.exceeds_work_area():
            self.stop_size_guard()
            return
        if self._size_guard_corrections <= 0:
            self.stop_size_guard()
            return
        # Later, not inside the resize event the compositor's size came with.
        QTimer.singleShot(0, self.correct_outside_resize)

    def correct_outside_resize(self) -> None:
        if not self.size_guard_active() or self._size_guard_corrections <= 0:
            return
        states = Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen
        if self.windowState() & states or not self.exceeds_work_area():
            return
        self._size_guard_corrections -= 1
        self._size_guard_timer.start(COMPOSITOR_RESIZE_GUARD_MS)
        frame = self.frameGeometry()
        current = (frame.x(), frame.y(), frame.width(), frame.height())
        x, y, width, height = fit_rect_into_area(current, self.available_area())
        frame_width, frame_height = self.frame_extra()
        self.resize_by_program(width - frame_width, height - frame_height)
        if (x, y) != current[:2]:
            self.move(x, y)
        self.request_relayout()

    def apply_layout_profile(self, profile: str) -> None:
        """Arrange the cards and set the density for one layout profile."""
        if profile == self._layout_profile:
            return
        self._layout_profile = profile
        metrics = density_for(profile)
        margin = metrics["outer_margin"]
        self._root_layout.setContentsMargins(margin, margin, margin, margin)
        self._root_layout.setSpacing(metrics["spacing"])
        self.cards_grid.setHorizontalSpacing(metrics["spacing"] + 3)
        self.cards_grid.setVerticalSpacing(metrics["spacing"])
        horizontal, vertical = metrics["card_margin"]
        for layout in self._card_layouts:
            layout.setContentsMargins(horizontal, vertical, horizontal, vertical)
            layout.setSpacing(metrics["card_spacing"])
        horizontal, vertical = metrics["warning_margin"]
        self._warning_layout.setContentsMargins(horizontal, vertical, horizontal, vertical)
        self.iso_edit.setMinimumHeight(metrics["line_edit"])
        self.device_combo.setMinimumHeight(metrics["combo"])
        self.raw_button.setMinimumHeight(metrics["mode_button"])
        self.windows_button.setMinimumHeight(metrics["mode_button"])
        self.boot_mode_combo.setMinimumHeight(metrics["boot_combo"])
        self.start_button.setMinimumHeight(metrics["action_button"])
        self.cancel_button.setMinimumHeight(metrics["action_button"])
        self.log.setMinimumHeight(metrics["log_min"])

        for card in (self.image_card, self.device_card, self.mode_card, self.progress_card):
            self.cards_grid.removeWidget(card)
        for row in range(5):
            self.cards_grid.setRowStretch(row, 0)
        for column in range(2):
            self.cards_grid.setColumnStretch(column, 0)
        if profile == "wide":
            # Two by two, read left to right: 1 | 2, then 3 | progress.
            self.cards_grid.addWidget(self.image_card, 0, 0)
            self.cards_grid.addWidget(self.device_card, 0, 1)
            self.cards_grid.addWidget(self.mode_card, 1, 0)
            self.cards_grid.addWidget(self.progress_card, 1, 1)
            self.cards_grid.setRowStretch(1, 1)
            self.cards_grid.setColumnStretch(0, 1)
            self.cards_grid.setColumnStretch(1, 1)
        else:
            self.cards_grid.addWidget(self.image_card, 0, 0)
            self.cards_grid.addWidget(self.device_card, 1, 0)
            self.cards_grid.addWidget(self.mode_card, 2, 0)
            self.cards_grid.addWidget(self.progress_card, 3, 0)
            self.cards_grid.setRowStretch(3, 1)
            self.cards_grid.setColumnStretch(0, 1)
        # The cards were created without a parent; a re-parented widget stays
        # hidden until shown, and hidden widgets do not count in the layout.
        for card in (self.image_card, self.device_card, self.mode_card, self.progress_card):
            card.setVisible(True)
        self.centralWidget().widget().layout().activate()

    def content_requirement(self, width: int) -> tuple[int, int]:
        """Minimum width and the height the content needs at ``width``."""
        root = self.scroll_area.widget()
        layout = root.layout()
        layout.invalidate()
        layout.activate()
        hint = root.minimumSizeHint()
        height = hint.height()
        if layout.hasHeightForWidth():
            height = max(height, layout.totalHeightForWidth(max(width, hint.width())))
        return hint.width(), height

    def measure_layout_profiles(self) -> None:
        """Measure the single-column height with the current fonts.

        It is taken at the classic 740 px window width and decides the first
        window size; the layout itself is chosen from live measurements.
        """
        self.setUpdatesEnabled(False)
        try:
            self._layout_profile = ""
            self.apply_layout_profile("normal")
            reference = 740 - 2 * density_for("normal")["outer_margin"]
            self._single_column_height = self.content_requirement(reference)[1]
        finally:
            self.setUpdatesEnabled(True)
        self._last_viewport = None
        self.update_layout_profile()

    def update_layout_profile(self) -> None:
        """Choose the first layout that fits the viewport without scrolling."""
        if not self._single_column_height:
            return
        # A text change (e.g. a mode description) posts a layout request; let
        # it run first, or the measurement below still sees the old texts.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        viewport = self.scroll_area.maximumViewportSize()
        key = (viewport.width(), viewport.height())
        if key == self._last_viewport:
            return
        self._last_viewport = key
        requirements: dict[str, tuple[int, int]] = {}
        self.setUpdatesEnabled(False)
        try:
            for profile in ("normal", "wide"):
                self.apply_layout_profile(profile)
                requirements[profile] = self.content_requirement(viewport.width())
                if requirements[profile][0] <= key[0] and requirements[profile][1] <= key[1]:
                    break
            self.apply_layout_profile(choose_layout_profile(key, requirements))
        finally:
            self.setUpdatesEnabled(True)

    def layout_profile(self) -> str:
        return self._layout_profile

    def request_relayout(self) -> None:
        """Choose the layout again although the window size did not change.

        A mode change shows texts of a different length (the Windows Legacy
        and RAW descriptions are longer), so the content may no longer fit
        the current profile while another one would.
        """
        self._last_viewport = None
        if hasattr(self, "_layout_timer"):
            self._layout_timer.start()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        if hasattr(self, "_size_guard_timer") and not self._own_resize:
            self.check_outside_resize()
        if hasattr(self, "_layout_timer"):
            self._layout_timer.start()

    def apply_style(self) -> None:
        """Style sheet from palette-derived tokens (theme.py); no fixed colours here.

        Always complete (docs/INVARIANTS.md C4): the style sheet is set and
        every widget is polished again even when the text is unchanged,
        because the palette or the style under it may have changed (a
        switch between manual dark and a dark automatic mode mixed the
        colours when this step was skipped)."""
        tokens = self.theme.tokens()
        stylesheet = build_stylesheet(tokens)
        self.setStyleSheet(stylesheet)
        for widget in (self, *self.findChildren(QWidget)):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()
        self.update_theme_button(tokens)
        self.set_status_state(self._status_state)

    def update_theme_button(self, tokens=None) -> None:
        tokens = tokens or self.theme.tokens()
        scheme = self.theme.scheme
        ratio = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        self.theme_button.setIcon(theme_icon(scheme, tokens["text"], 20, ratio))
        appearance = tr("Sötét") if scheme == "dark" else tr("Világos")
        source = {
            "system": tr("a rendszer beállítása szerint"),
            "manual": tr("kézi beállítás"),
            "fallback": tr("a rendszer témája nem állapítható meg, ezért sötét"),
        }[self.theme.source]
        target = tr("világos") if scheme == "dark" else tr("sötét")
        tooltip = tr(
            "Megjelenés: {appearance} ({source}).\n"
            "Kattintás: váltás {target} megjelenésre.\n"
            "A gomb menüjében a „Rendszer / Automatikus” visszaállítja a rendszer szerinti módot."
        ).format(appearance=appearance, source=source, target=target)
        self.theme_button.setToolTip(tooltip)
        self.theme_button.setAccessibleName(tr("Megjelenés váltása"))
        self.theme_button.setAccessibleDescription(tooltip)
        for mode, action in self.theme_actions.items():
            action.setChecked(mode == self.theme.mode)

    def set_status_state(self, state: str) -> None:
        """Status icon and colour; the shape and the text tell the state too."""
        self._status_state = state
        ratio = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        self.status_icon.setPixmap(status_icon_pixmap(state, self.theme.tokens(), 16, ratio))
        self.status_icon.setAccessibleName(status_accessible_name(state))
        self.status_icon.setToolTip(status_accessible_name(state))
        if self.status_label.property("state") != state:
            self.status_label.setProperty("state", state)
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

    def changeEvent(self, event) -> None:
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.ApplicationFontChange) and self._single_column_height:
            # A different system font size changes every layout's minimum.
            # The timer belongs to the window, so it dies with it.
            self._measure_timer.start()
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            # A system theme switch while running. The controller applies
            # again only when the application palette itself changed, so the
            # palette events caused by apply_style() do not loop.
            self.theme.palette_changed()
        super().changeEvent(event)

    def choose_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Lemezkép kiválasztása",
            str(Path.home()),
            "Lemezképek (*.iso *.img *.bin *.raw);;Minden fájl (*)",
        )
        if filename:
            self.iso_edit.setText(filename)
            self.inspect_image(filename)

    def inspect_typed_image(self) -> None:
        """Recognise a path typed into the field once, like a browsed file."""
        text = self.iso_edit.text().strip()
        if not text:
            return
        try:
            resolved = str(Path(text).expanduser().resolve())
        except (OSError, RuntimeError):
            return
        if resolved != self._inspected_image and Path(resolved).is_file():
            self.inspect_image(resolved)

    def inspect_image(self, filename: str) -> None:
        try:
            selected = Path(filename).expanduser()
            self._inspected_image = str(selected.resolve())
            size = selected.stat().st_size
            is_windows = (
                selected.suffix.lower() == ".iso"
                and is_windows_install_iso(selected)
            )
            self._windows_iso_path = str(selected.resolve()) if is_windows else None
            self.update_boot_mode_controls()
            description = f"{selected.name} • {human_size(size)}"
            if is_windows:
                description += " • Windows telepítő ISO felismerve"
            short_description = (
                f"{human_size(size)} • "
                + ("Windows telepítő ISO" if is_windows else "Lemezkép")
            )
            self.file_info.setText(short_description)
            self.file_info.setToolTip(description)
        except OSError:
            self._windows_iso_path = None
            self.update_boot_mode_controls()
            self.file_info.setText("A fájl nem olvasható.")
            self.file_info.setToolTip("A kiválasztott fájl nem olvasható.")

    def refresh_devices_silently(self) -> None:
        # Don't replace the list while a privileged operation is running.
        if self.process is None:
            self.refresh_devices(preserve_selection=True, quiet=True)

    def refresh_devices(self, preserve_selection: bool = False, quiet: bool = False) -> None:
        if self.process is not None or self._lsblk_request_active:
            return
        if self.lsblk_process.state() != QProcess.ProcessState.NotRunning:
            return

        self._lsblk_request_active = True
        self._lsblk_preserve_selection = preserve_selection
        self._lsblk_quiet = quiet
        self._lsblk_current_selection = (
            self.device_combo.currentData() if preserve_selection else None
        )
        self.refresh_button.setEnabled(False)
        self.lsblk_process.start(
            "lsblk",
            [
                "--json", "--bytes", "--paths", "--tree",
                "--output",
                "PATH,NAME,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,RM,RO,MAJ:MIN,"
                "PKNAME,FSTYPE,LABEL,PARTTYPE,PARTLABEL,MOUNTPOINTS",
            ],
        )
        self.lsblk_timeout_timer.start()

    def _finish_lsblk_error(self, message: str) -> None:
        if not self._lsblk_request_active:
            return
        self._lsblk_request_active = False
        self.lsblk_timeout_timer.stop()
        if self.lsblk_process.state() != QProcess.ProcessState.NotRunning:
            self.lsblk_process.kill()
        if self.process is None:
            self.refresh_button.setEnabled(True)
        if self._lsblk_quiet:
            # Log an unchanged error only once until a refresh succeeds.
            if message != self._lsblk_last_quiet_error:
                self._lsblk_last_quiet_error = message
                self.append_log(message)
        else:
            QMessageBox.warning(self, "Meghajtók listázása", message)

    def _lsblk_process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finish_lsblk_error("Az lsblk parancs nem indítható el.")
        elif error == QProcess.ProcessError.Crashed:
            self._finish_lsblk_error("Az lsblk parancs váratlanul leállt.")

    def _lsblk_timed_out(self) -> None:
        self._finish_lsblk_error(
            "Az lsblk lekérdezés 5 másodperc után időtúllépéssel leállt. "
            "Ellenőrizd a csatlakoztatott USB-eszközt vagy az USB-vezérlőt."
        )

    def _lsblk_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if not self._lsblk_request_active:
            return
        self.lsblk_timeout_timer.stop()

        stdout = bytes(self.lsblk_process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        stderr = bytes(self.lsblk_process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        ).strip()
        if exit_status != QProcess.ExitStatus.NormalExit or exit_code != 0:
            self._finish_lsblk_error(
                stderr or f"Az lsblk sikertelenül állt le (kilépési kód: {exit_code})."
            )
            return
        try:
            devices = json.loads(stdout).get("blockdevices", [])
            if not isinstance(devices, list):
                raise ValueError("Az lsblk válasza nem tartalmazott eszközlistát.")
        except (json.JSONDecodeError, AttributeError, ValueError) as exc:
            self._finish_lsblk_error(f"Nem sikerült feldolgozni az lsblk válaszát: {exc}")
            return

        self._lsblk_request_active = False
        # State change: after a successful refresh the same error may be logged again.
        self._lsblk_last_quiet_error = None
        if self.process is None:
            self.refresh_button.setEnabled(True)
        self._populate_devices(
            devices,
            self._lsblk_current_selection,
            self._lsblk_quiet,
        )

    def _populate_devices(
        self,
        devices: list[dict[str, Any]],
        current: dict[str, Any] | None,
        quiet: bool,
    ) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for disk in devices:
            if disk.get("type") != "disk":
                continue
            transport = (disk.get("tran") or "").lower()
            removable_value = disk.get("rm")
            removable = removable_value is True or str(removable_value).lower() in {"1", "true", "yes"}
            if transport != "usb" and not removable:
                continue
            ro_value = disk.get("ro")
            readonly = ro_value is True or str(ro_value).lower() in {"1", "true", "yes"}
            if readonly:
                continue
            path = disk.get("path")
            if not path:
                continue
            raw_model = str(disk.get("model") or "")
            model_display = raw_model.strip() or str(disk.get("name") or "USB-meghajtó").strip()
            if not model_display:
                model_display = "USB-meghajtó"
            size = int(disk.get("size") or 0)
            identity = disk_identity(disk)
            partitions = flatten_partitions(disk)
            mounts = mounted_paths(disk)
            unsafe_reason = unsafe_layout_reason(disk)
            tag = "USB" if transport == "usb" else "eltávolítható"
            serial = identity.get("serial") or identity.get("wwn") or identity.get("diskseq") or "nincs sorozatszám"
            label = f"{model_display}   •   {human_size(size)}   •   {path}   [{tag}]"
            if unsafe_reason:
                label += "   [VÉDETT]"
            data = {
                **identity,
                "path": path,
                "size": size,
                "model_display": model_display,
                "mounts": mounts,
                "partitions": partitions,
                "unsafe_reason": unsafe_reason,
                "serial_display": serial,
            }
            self.device_combo.addItem(label, data)
            if unsafe_reason:
                item = self.device_combo.model().item(self.device_combo.count() - 1)
                if item is not None:
                    item.setEnabled(False)
                    item.setToolTip(unsafe_reason)
        if current:
            for index in range(self.device_combo.count()):
                item = self.device_combo.itemData(index)
                if item and item.get("path") == current.get("path"):
                    self.device_combo.setCurrentIndex(index)
                    break
        self.device_combo.blockSignals(False)
        self.device_changed(self.device_combo.currentIndex())
        if not quiet and self.device_combo.count() == 0:
            self.device_detail.setText("Nem található USB / eltávolítható lemez. Csatlakoztass egyet, majd frissítsd a listát.")

    def device_changed(self, index: int) -> None:
        self.current_device = self.device_combo.itemData(index) if index >= 0 else None
        if not self.current_device:
            self.device_detail.setText("Nincs kiválasztott USB-meghajtó.")
            self.device_detail.setToolTip("")
            self.partition_info_label.setText("Partíció információk:")
            self.partition_info_button.setEnabled(False)
            self.partition_info_button.setToolTip("Nincs elérhető partícióinformáció.")
            return

        model = self.current_device.get("model_display") or self.current_device.get("model") or "Ismeretlen eszköz"
        serial = self.current_device.get("serial_display") or "ismeretlen"
        capacity = human_size(self.current_device["size"])
        summary = f"Kapacitás: {capacity} • Azonosító: {serial} • Eszköz: {model}"
        self.device_detail.setText(summary)
        self.device_detail.setToolTip(
            f"{summary}\nEszközútvonal: {self.current_device.get('path') or 'ismeretlen'}"
        )

        partitions = self.current_device.get("partitions") or []
        if not partitions:
            tooltip = "<b>Partíció információk</b><br>Nincs felismert partíció."
        else:
            rows: list[str] = []
            for number, part in enumerate(partitions, start=1):
                path = html.escape(str(part.get("path") or "ismeretlen"))
                fs = html.escape(str(part.get("fstype") or part.get("type") or "ismeretlen").upper())
                label = html.escape(str(part.get("label") or "nincs címke"))
                size = html.escape(human_size(int(part.get("size") or 0)))
                mounts = part.get("mountpoints") or []
                if isinstance(mounts, str):
                    mounts = [mounts]
                mount_text = ", ".join(str(item) for item in mounts if item) or "nincs csatolva"
                mount_text = html.escape(mount_text)
                rows.append(
                    f"<b>{number}. {path}</b><br>"
                    f"Fájlrendszer: {fs}<br>"
                    f"Címke: {label}<br>"
                    f"Méret: {size}<br>"
                    f"Csatolás: {mount_text}"
                )
            tooltip = "<b>Partíció információk</b><br><br>" + "<br><br>".join(rows)

        self.partition_info_button.setEnabled(True)
        self.partition_info_button.setToolTip(tooltip)
        self.partition_info_button.setToolTipDuration(15000)

    
    def select_mode(self, mode: str) -> None:
        raw = mode == "raw"
        self.raw_button.setChecked(raw)
        self.windows_button.setChecked(not raw)
        self.verify_checkbox.setEnabled(True)
        if mode != self._selected_mode:
            # Raw image mode keeps full read-back verification enabled by
            # default. Windows mode defaults to faster writing; SHA-256
            # read-back remains available as an explicit opt-in.
            self.verify_checkbox.setChecked(raw)
            self._selected_mode = mode
        if raw:
            self.verify_checkbox.setText("Kiírás utáni teljes visszaolvasás és ellenőrzés")
            self.mode_description.setText(
                "ISOHybrid Linux- és egyéb lemezképekhez. A teljes lemezkép közvetlenül "
                "az USB-re kerül; minden meglévő adat felülíródik. Opcionális visszaolvasás ellenőrzi a kiírást."
            )
        else:
            self.verify_checkbox.setText("USB-re másolt fájlok teljes SHA-256 visszaellenőrzése")
        self.update_boot_mode_controls()
        self.request_relayout()

    def apply_grub_availability(self) -> None:
        """Enable or disable the Legacy BIOS item from the GRUB i386-pc check."""
        item = self.boot_mode_combo.model().item(1)
        item.setEnabled(self._bios_grub_available)
        if self._bios_grub_available:
            self.grub_hint.setText("")
            self.grub_hint.setToolTip("")
            self.boot_mode_combo.setToolTip(
                "UEFI (GPT): újabb gépekhez. Legacy BIOS (MBR): UEFI nélküli vagy CSM módú gépekhez."
            )
            self.request_relayout()
            return
        if self.boot_mode_combo.currentData() == "bios":
            self.boot_mode_combo.setCurrentIndex(0)
        hint = (
            "A Legacy BIOS módhoz a GRUB (i386-pc) szükséges. "
            "Telepítsd: sudo pacman -S grub, majd indítsd újra a programot."
        )
        self.grub_hint.setText("Legacy nem elérhető: sudo pacman -S grub")
        self.grub_hint.setToolTip(hint)
        item.setToolTip(hint)
        self.boot_mode_combo.setToolTip(hint)
        self.request_relayout()

    def windows_iso_selected(self) -> bool:
        if not self._windows_iso_path:
            return False
        try:
            current = str(Path(self.iso_edit.text().strip()).expanduser().resolve())
        except (OSError, RuntimeError):
            return False
        return current == self._windows_iso_path

    def update_boot_mode_controls(self) -> None:
        """The boot mode selector is active only for a recognised Windows ISO."""
        active = self._selected_mode == "windows" and self.windows_iso_selected()
        if not active and self.boot_mode_combo.currentIndex() != 0:
            # Without a Windows ISO the Windows mode always means UEFI.
            self.boot_mode_combo.setCurrentIndex(0)
        self.boot_mode_combo.setEnabled(active)
        self.boot_mode_label.setEnabled(active)
        if self._selected_mode == "windows":
            self.update_windows_description()
        self.request_relayout()

    def boot_mode_changed(self, _index: int) -> None:
        if self._selected_mode == "windows":
            self.update_windows_description()
            self.request_relayout()

    def update_windows_description(self) -> None:
        if self.selected_boot_mode() == "bios":
            self.mode_description.setText(
                "Windows Legacy BIOS: MBR, egy aktív NTFS partíció, GRUB láncbetöltő a /grub "
                "könyvtárban. Legacy BIOS / CSM indításhoz; UEFI-s géphez az UEFI (GPT) mód kell."
            )
        else:
            self.mode_description.setText(
                "Windows x64 UEFI: nagy NTFS adatpartíció és BMK_EFI UEFI:NTFS segédpartíció. "
                "A nagy install.esd / install.wim fájlok változatlanul másolódnak."
            )

    def selected_boot_mode(self) -> str:
        if self.boot_mode_combo.isEnabled() and self.boot_mode_combo.currentData() == "bios":
            return "bios"
        return "uefi"

    def selected_worker_mode(self) -> str:
        """Worker mode name: raw, windows (UEFI) or windows-bios."""
        if self.raw_button.isChecked():
            return "raw"
        return "windows-bios" if self.selected_boot_mode() == "bios" else "windows"

    def start_operation_clock(self) -> None:
        if self._operation_timer_started:
            return
        self._operation_elapsed.start()
        self._operation_timer_started = True
        self.elapsed_timer.start()
        self.update_elapsed_display()

    def update_elapsed_display(self) -> None:
        if self._operation_timer_started and self._operation_elapsed.isValid():
            elapsed = self._operation_elapsed.elapsed()
            self.elapsed_label.setText(f"Eltelt idő: {format_elapsed_time(elapsed)}")

    def stop_operation_clock(self) -> None:
        self.elapsed_timer.stop()
        self.update_elapsed_display()

    def append_log(self, text: str) -> None:
        if text:
            self.log.appendPlainText(text)

    def start_operation(self) -> None:
        image = Path(self.iso_edit.text().strip()).expanduser()
        if not image.is_file():
            QMessageBox.warning(self, "Hiányzó lemezkép", "Válassz ki egy létező ISO / IMG / BIN fájlt.")
            return
        if image.suffix.lower() not in {".iso", ".img", ".bin", ".raw"}:
            QMessageBox.warning(self, "Nem támogatott formátum", "Ebben a változatban ISO, IMG, BIN és RAW fájl használható.")
            return
        if not self.current_device:
            QMessageBox.warning(self, "Nincs USB-meghajtó", "Csatlakoztass és válassz ki egy USB-meghajtót.")
            return

        worker_mode = self.selected_worker_mode()
        mode = "raw" if worker_mode == "raw" else "windows"
        device = self.current_device
        if device.get("unsafe_reason"):
            QMessageBox.critical(self, "Védett meghajtó", str(device["unsafe_reason"]))
            return
        if mode == "raw" and image.suffix.lower() == ".iso" and is_windows_install_iso(image):
            QMessageBox.warning(
                self,
                "Windows ISO észlelve",
                "Ez Windows telepítő ISO-nak tűnik. Ne nyers lemezképként írd ki, mert így általában nem lesz bootolható. "
                "Válaszd a „Windows telepítő (NTFS)” módot.",
            )
            return
        try:
            image_size = image.stat().st_size
        except OSError as exc:
            QMessageBox.warning(self, "Forrásfájl", f"A forrásfájl nem olvasható:\n{exc}")
            return
        if mode == "raw" and image_size > device["size"]:
            QMessageBox.warning(self, "Kevés tárhely", "A lemezkép nagyobb, mint a kiválasztott USB-meghajtó.")
            return
        if mode == "windows" and image.suffix.lower() != ".iso":
            QMessageBox.warning(self, "Windows ISO szükséges", "A Windows telepítő módhoz ISO fájlt válassz.")
            return
        if worker_mode == "windows-bios" and not bios_grub_available():
            QMessageBox.warning(
                self,
                "Hiányzó GRUB",
                "A Legacy BIOS módhoz szükséges GRUB (i386-pc) nem található a gépen.\n\n"
                "Telepítsd a grub csomagot (sudo pacman -S grub), vagy válaszd az UEFI (GPT) indítási módot.",
            )
            return

        partition_lines = []
        for part in device.get("partitions") or []:
            fs = part.get("fstype") or part.get("type") or "ismeretlen fájlrendszer"
            label = part.get("label") or "nincs címke"
            size = human_size(int(part.get("size") or 0))
            mounts = part.get("mountpoints") or []
            if isinstance(mounts, str):
                mounts = [mounts]
            mount_text = ", ".join(str(x) for x in mounts if x) or "nincs csatolva"
            partition_lines.append(
                f"  {part.get('path')}  |  {fs}  |  {label}  |  {size}  |  {mount_text}"
            )
        partition_text = "\n".join(partition_lines) if partition_lines else "  Nincs felismert partíció."
        mounts = device.get("mounts") or []
        removable = bool(device.get("rm"))
        transport = str(device.get("tran") or "").lower()
        large_or_nonremovable = (
            int(device["size"]) >= 128 * 1024 * 1024 * 1024
            or (transport == "usb" and not removable)
        )
        identity_text = (
            f"Modell: {device.get('model') or 'ismeretlen'}\n"
            f"Sorozatszám/WWN: {device.get('serial') or device.get('wwn') or 'nincs'}\n"
            f"Disk sequence: {device.get('diskseq') or 'nincs'}\n"
            f"By-id: {device.get('by_id') or 'nincs'}\n"
            f"Kapacitás: {human_size(device['size'])}\n"
            f"Eszköz: {device['path']}"
        )
        details = (
            f"Forrás: {image} ({human_size(image_size)})\n\n"
            f"Cél fizikai meghajtó:\n{identity_text}\n\n"
            f"Partíciók és kötetek:\n{partition_text}\n\n"
            "A célmeghajtó MINDEN partíciója, fájlrendszere és adata törlődni fog."
        )
        if mounts:
            details += "\n\nCsatolt útvonalak, amelyeket leválasztunk:\n" + "\n".join(mounts)
        if worker_mode == "windows":
            details += (
                "\n\nÍrási mód: Windows telepítő, indítási mód: UEFI (GPT).\n"
                "A Windows mód GPT-t hoz létre: nagy NTFS telepítőpartíció és "
                "1 MiB BMK_EFI FAT UEFI:NTFS segédpartíció. A Windows ISO eredeti fájljai másolódnak."
            )
        elif worker_mode == "windows-bios":
            details += (
                "\n\nÍrási mód: Windows telepítő, indítási mód: Legacy BIOS (MBR).\n"
                "MBR-t hoz létre egy aktív NTFS partícióval, és a GRUB láncbetöltőt a pendrive "
                "/grub könyvtárába telepíti. A Windows ISO eredeti fájljai másolódnak.\n\n"
                "FIGYELEM: ez a pendrive Legacy BIOS / CSM indításhoz készül. UEFI módban csak "
                "NTFS-t olvasó firmware-en indulhat, erre ne számíts: UEFI-s géphez az "
                "UEFI (GPT) indítási módot használd."
            )
        reply = QMessageBox.warning(
            self,
            "Végleges megerősítés szükséges",
            details,
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if large_or_nonremovable:
            second = QMessageBox.warning(
                self,
                "Második megerősítés – nagy vagy nem-removable meghajtó",
                f"Ez egy {human_size(device['size'])} méretű vagy nem-removable USB-eszköz.\n\n"
                f"Valóban ezt a teljes fizikai meghajtót akarod törölni?\n\n{device['path']} — "
                f"{device.get('model') or 'ismeretlen modell'}",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if second != QMessageBox.StandardButton.Yes:
                return

        if not PRIVILEGED_WRAPPER.is_file():
            QMessageBox.critical(
                self,
                "Hiányzó biztonságos worker",
                f"Nem található a telepített root wrapper:\n{PRIVILEGED_WRAPPER}\n\n"
                "Telepítsd újra a BootMediaKit biztonsági kiadását.",
            )
            return
        if not shutil.which("pkexec"):
            QMessageBox.critical(self, "Hiányzó pkexec", "A pkexec / polkit nem található. Telepítsd a polkit csomagot.")
            return

        identity_json = json.dumps(
            {
                key: device.get(key, "")
                for key in (
                    "path", "size", "model", "serial", "wwn", "tran",
                    "rm", "maj_min", "diskseq", "by_id",
                )
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        # Prefer a persistent /dev/disk/by-id symlink so a hot-unplug/
        # replug cannot redirect the privileged worker to a newly assigned sdX.
        target_path = str(device.get("by_id") or device["path"])
        args = [
            str(PRIVILEGED_WRAPPER),
            worker_mode,
            str(image.resolve()),
            target_path,
            "1" if self.verify_checkbox.isChecked() else "0",
            identity_json,
        ]

        self.progress.setValue(0)
        self.log.clear()
        self.status_label.setText("Rendszergazdai jogosultság kérése…")
        self.set_status_state("progress")
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.refresh_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.device_combo.setEnabled(False)
        self.raw_button.setEnabled(False)
        self.windows_button.setEnabled(False)
        self.boot_mode_combo.setEnabled(False)
        self.iso_edit.setEnabled(False)

        self.output_buffer = ""
        self._worker_started = False
        self._target_modified = False
        self._operation_cancelled = False
        self._close_after_operation = False
        self.cancel_button.setText("Megszakítás")
        self.elapsed_timer.stop()
        self._operation_elapsed = QElapsedTimer()
        self._operation_timer_started = False
        self.elapsed_label.setText("Eltelt idő: 00:00")
        self.process = QProcess(self)
        self.process.setProgram("/usr/bin/pkexec")
        self.process.setArguments(args)
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.operation_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.process.start()

    def _send_cancel_request(self) -> None:
        if not self.process:
            return
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Megszakítás folyamatban…")
        self.status_label.setText("Biztonságos megszakítás kérése…")
        self.process.write(b"cancel\n")
        self.process.closeWriteChannel()

    def cancel_operation(self) -> None:
        if not self.process:
            return
        reply = QMessageBox.warning(
            self,
            "Művelet megszakítása",
            "A műveletet biztonságos írási határon állítjuk le. A pendrive részleges állapotban maradhat, "
            "ha a törlés vagy írás már elkezdődött.\n\nBiztosan megszakítod?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._send_cancel_request()

    def closeEvent(self, event) -> None:
        if self.process is None:
            event.accept()
            return
        reply = QMessageBox.warning(
            self,
            "A BootMediaKit művelete még fut",
            "Bezárás előtt biztonságosan megszakítjuk a pendrive készítését. "
            "A célmeghajtó részleges állapotban maradhat.\n\nMegszakítod és bezárod?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.close_after_cancel()
        event.ignore()

    def close_after_cancel(self) -> None:
        """Cancel cooperatively and close when the worker has finished.

        The path of a confirmed window close; Ctrl+C in the terminal uses it too.
        """
        if self._close_after_operation:
            return
        self._close_after_operation = True
        self._send_cancel_request()

    def poll_terminal_interrupt(self) -> None:
        if self._interrupt_requested and not self._interrupt_handled:
            self._interrupt_handled = True
            if self.process is None:
                self.close()
            else:
                self.close_after_cancel()

    def read_stdout(self) -> None:
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.output_buffer += data
        while "\n" in self.output_buffer:
            line, self.output_buffer = self.output_buffer.split("\n", 1)
            self.handle_worker_line(line)

    def read_stderr(self) -> None:
        if not self.process:
            return
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        if data:
            self.append_log(data)

    def handle_worker_line(self, line: str) -> None:
        if not line.strip():
            return
        # The first worker progress event marks the actual operation start.
        # Time spent waiting for the polkit password is intentionally excluded.
        self.start_operation_clock()
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self.append_log(line)
            return
        if event.get("worker_started"):
            self._worker_started = True
        if "target_modified" in event:
            self._target_modified = bool(event.get("target_modified"))
        if event.get("cancelled"):
            self._operation_cancelled = True
        message = str(event.get("message", ""))
        if message:
            self.status_label.setText(message)
        if event.get("error"):
            self.set_status_state("warning" if event.get("cancelled") else "error")
        if "percent" in event:
            self.progress.setValue(max(0, min(100, int(event["percent"]))))
        if event.get("log"):
            self.append_log(str(event["log"]))
        if event.get("error"):
            self.append_log("HIBA: " + str(event["error"]))

    def process_error(self, error: QProcess.ProcessError) -> None:
        self.append_log(f"A háttérfolyamat indítási hibája: {error}")
        if error == QProcess.ProcessError.FailedToStart:
            self.stop_operation_clock()
            self.set_busy(False)
            self.status_label.setText("A privilegizált háttérfolyamat nem indult el; a céllemezt nem módosítottam.")
            self.set_status_state("error")
            self.process = None
            if self._close_after_operation:
                self.close()

    def operation_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self.read_stdout()
        if self.output_buffer.strip():
            self.handle_worker_line(self.output_buffer.strip())
            self.output_buffer = ""
        self.stop_operation_clock()
        self.set_busy(False)
        # Ctrl+C may have stopped pkexec before the poll timer ran: no dialog then.
        was_closing = self._close_after_operation or self._interrupt_requested
        if self._interrupt_requested:
            self._interrupt_handled = True

        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.progress.setValue(100)
            self.status_label.setText("Sikeres befejezés.")
            self.set_status_state("success")
            self.append_log("Kész. Biztonságosan eltávolíthatod az USB-meghajtót.")
            if not was_closing:
                QMessageBox.information(self, "Elkészült", "Az USB-meghajtó elkészült. Biztonságosan eltávolíthatod.")
        elif self._operation_cancelled or exit_code == 130:
            self.status_label.setText("A művelet biztonságosan megszakítva.")
            self.set_status_state("warning")
            self.append_log(
                "A célmeghajtó részleges állapotban maradhat."
                if self._target_modified
                else "A megszakítás a célmeghajtó módosítása előtt történt; a lemez tartalmához nem nyúltunk."
            )
        elif not self._worker_started:
            # pkexec 126/127 and failures before the worker's first structured
            # event cannot have touched the target disk.
            status, title, text = describe_privilege_failure(exit_code)
            self.status_label.setText(status)
            self.set_status_state("warning" if exit_code == PKEXEC_DISMISSED else "error")
            self.append_log(f"A pkexec kilépési kódja: {exit_code}. A célmeghajtót nem módosítottuk.")
            if not was_closing:
                if exit_code == PKEXEC_NOT_AUTHORIZED:
                    QMessageBox.critical(self, title, text)
                else:
                    QMessageBox.information(self, title, text)
        else:
            self.status_label.setText("A művelet nem fejeződött be.")
            self.set_status_state("error")
            self.append_log(f"A háttérfolyamat kilépési kódja: {exit_code}")
            if not was_closing:
                QMessageBox.critical(
                    self,
                    "Sikertelen művelet",
                    "A művelet nem fejeződött be. A naplóban látható a hiba oka. "
                    + (
                        "A célmeghajtó állapota részleges lehet; újrahasználat előtt készítsd el újra."
                        if self._target_modified
                        else "A célmeghajtó tartalmát a worker nem módosította."
                    ),
                )
        self.process = None
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Megszakítás")
        self.refresh_devices(preserve_selection=True, quiet=True)
        if was_closing:
            self.close()

    def set_busy(self, busy: bool) -> None:
        if busy and self._lsblk_request_active:
            self.lsblk_timeout_timer.stop()
            self._lsblk_request_active = False
            if self.lsblk_process.state() != QProcess.ProcessState.NotRunning:
                self.lsblk_process.kill()
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.refresh_button.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.device_combo.setEnabled(not busy)
        self.raw_button.setEnabled(not busy)
        self.windows_button.setEnabled(not busy)
        if busy:
            self.boot_mode_combo.setEnabled(False)
        else:
            self.update_boot_mode_controls()
        self.iso_edit.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy and not self._lsblk_request_active)
        if not busy:
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()


def shutdown_window(window: MainWindow) -> None:
    """Destroy the GUI object tree before PySide's interpreter-exit cleanup."""
    window.refresh_timer.stop()
    window.elapsed_timer.stop()
    window.lsblk_timeout_timer.stop()

    # Device discovery is non-destructive and may still be running if the
    # window is closed immediately after startup. Reap it before deleting its
    # owning MainWindow; the privileged writer is governed by closeEvent's
    # cooperative-cancellation flow and is deliberately not force-killed here.
    if window.lsblk_process.state() != QProcess.ProcessState.NotRunning:
        window.lsblk_process.kill()
        window.lsblk_process.waitForFinished(1000)

    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


def install_terminal_interrupt_handler(window: MainWindow) -> QTimer:
    """SIGINT only sets a flag; the window acts on it from a Qt timer."""

    def on_sigint(_signum, _frame) -> None:
        window._interrupt_requested = True

    signal.signal(signal.SIGINT, on_sigint)
    timer = QTimer(window)
    timer.setInterval(TERMINAL_INTERRUPT_POLL_MS)
    timer.timeout.connect(window.poll_terminal_interrupt)
    timer.start()
    return timer


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("BootMediaKit")
    theme_controller = ThemeController(app, open_settings())
    theme_controller.apply()
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("bootmediakit")
    if APP_ICON.is_file():
        app.setWindowIcon(QIcon(str(APP_ICON)))
    window = MainWindow(theme_controller)
    install_terminal_interrupt_handler(window)
    window.show()
    QTimer.singleShot(0, window.fit_window_to_screen)
    exit_code = app.exec()
    if window._interrupt_requested:
        exit_code = EXIT_INTERRUPTED

    # Explicitly destroy all widgets and child QObjects while QApplication is
    # still alive. This avoids leaving QObject wrappers for PySide's atexit
    # cleanup to destroy after Python has started finalizing.
    shutdown_window(window)
    del window
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
