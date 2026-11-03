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
import subprocess
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QElapsedTimer, QProcess, Qt, QTimer
from PySide6.QtGui import QFont, QIcon
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
from ui_helpers import calculate_window_profile, format_elapsed_time

APP_VERSION = "0.1.3-safety-alpha"
APP_NAME = "BootMediaKit"
WORKER = Path("/usr/lib/bootmediakit/worker.py")
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
    result = subprocess.run(command, capture_output=True, text=True, check=True)
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
        "model": str(disk.get("model") or "").strip(),
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



class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} – bootolható USB készítő")
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        available_width = available.width() if available else 1366
        available_height = available.height() if available else 900
        self._compact_ui = available_height < 850
        initial_width, initial_height, _ = calculate_window_profile(
            available_width, available_height
        )
        self.setMinimumSize(560, 520)
        self.setMaximumSize(740, 900)
        self.resize(initial_width, initial_height)
        if available:
            self.move(
                available.x() + max(0, (available_width - initial_width) // 2),
                available.y() + max(0, (available_height - initial_height) // 2),
            )
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

        # Start timing on the first worker progress event, not while pkexec
        # is waiting for the user's authentication.
        self._operation_elapsed = QElapsedTimer()
        self._operation_timer_started = False
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self.update_elapsed_display)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        outer_margin = 8 if self._compact_ui else 12
        root_layout.setContentsMargins(
            outer_margin, outer_margin, outer_margin, outer_margin
        )
        root_layout.setSpacing(5 if self._compact_ui else 7)

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
        root_layout.addLayout(header)

        warning = QFrame()
        warning.setObjectName("warningPanel")
        warning_layout = QHBoxLayout(warning)
        warning_layout.setContentsMargins(
            8 if self._compact_ui else 10,
            5 if self._compact_ui else 7,
            8 if self._compact_ui else 10,
            5 if self._compact_ui else 7,
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
        root_layout.addWidget(warning)

        # Image selection
        image_card = QFrame()
        image_card.setObjectName("panel")
        image_layout = QVBoxLayout(image_card)
        image_layout.setContentsMargins(
            9 if self._compact_ui else 11,
            5 if self._compact_ui else 7,
            9 if self._compact_ui else 11,
            5 if self._compact_ui else 7,
        )
        image_layout.setSpacing(3 if self._compact_ui else 5)
        image_label = QLabel("1. Lemezkép kiválasztása")
        image_label.setObjectName("sectionTitle")
        image_layout.addWidget(image_label)
        image_row = QHBoxLayout()
        self.iso_edit = QLineEdit()
        self.iso_edit.setPlaceholderText("Válassz ISO / IMG / BIN fájlt…")
        self.iso_edit.setClearButtonEnabled(True)
        self.iso_edit.setMinimumHeight(29 if self._compact_ui else 32)
        self.iso_edit.setMinimumWidth(0)
        self.iso_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.browse_button = QPushButton("Tallózás…")
        self.browse_button.clicked.connect(self.choose_image)
        image_row.addWidget(self.iso_edit, 1)
        image_row.addWidget(self.browse_button)
        image_layout.addLayout(image_row)
        self.file_info = QLabel("Támogatott formátumok: ISO, IMG, BIN, RAW")
        self.file_info.setObjectName("muted")
        self.file_info.setWordWrap(False)
        self.file_info.setMinimumWidth(0)
        self.file_info.setMaximumHeight(21)
        self.file_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        image_layout.addWidget(self.file_info)
        root_layout.addWidget(image_card)

        # Device selection
        device_card = QFrame()
        device_card.setObjectName("panel")
        device_layout = QVBoxLayout(device_card)
        device_layout.setContentsMargins(
            9 if self._compact_ui else 11,
            5 if self._compact_ui else 7,
            9 if self._compact_ui else 11,
            5 if self._compact_ui else 7,
        )
        device_layout.setSpacing(3 if self._compact_ui else 5)
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
        self.device_combo.setMinimumHeight(29 if self._compact_ui else 33)
        self.device_combo.setMinimumWidth(0)
        self.device_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.device_combo.currentIndexChanged.connect(self.device_changed)
        device_layout.addWidget(self.device_combo)
        self.device_detail = QLabel("Csatlakoztass egy USB-meghajtót, majd frissítsd a listát.")
        self.device_detail.setObjectName("muted")
        self.device_detail.setWordWrap(False)
        self.device_detail.setMinimumWidth(0)
        self.device_detail.setMaximumHeight(24)
        self.device_detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        device_layout.addWidget(self.device_detail)

        partition_info_row = QHBoxLayout()
        partition_info_row.setSpacing(5)
        self.partition_info_label = QLabel("Partíció információk:")
        self.partition_info_label.setObjectName("muted")
        self.partition_info_label.setMinimumWidth(0)
        self.partition_info_row = partition_info_row
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
        root_layout.addWidget(device_card)

        # Mode selection
        mode_card = QFrame()
        mode_card.setObjectName("panel")
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(
            9 if self._compact_ui else 11,
            5 if self._compact_ui else 7,
            9 if self._compact_ui else 11,
            5 if self._compact_ui else 7,
        )
        mode_layout.setSpacing(3 if self._compact_ui else 5)
        mode_title = QLabel("3. Írási mód")
        mode_title.setObjectName("sectionTitle")
        mode_layout.addWidget(mode_title)

        self.raw_button = QPushButton("Lemezkép közvetlen kiírása")
        self.raw_button.setCheckable(True)
        self.raw_button.setChecked(True)
        self.raw_button.setObjectName("modeButton")
        self.windows_button = QPushButton("Windows telepítő (UEFI / GPT / NTFS)")
        self.windows_button.setCheckable(True)
        self.windows_button.setObjectName("modeButton")
        self.raw_button.clicked.connect(lambda: self.select_mode("raw"))
        self.windows_button.clicked.connect(lambda: self.select_mode("windows"))
        for button in (self.raw_button, self.windows_button):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            button.setMinimumHeight(30 if self._compact_ui else 34)
        mode_buttons = QHBoxLayout()
        mode_buttons.setSpacing(8)
        mode_buttons.addWidget(self.raw_button, 1)
        mode_buttons.addWidget(self.windows_button, 1)
        mode_layout.addLayout(mode_buttons)
        self.mode_description = QLabel(
            "ISOHybrid Linux- és egyéb lemezképekhez. A teljes lemezkép közvetlenül "
            "az USB-re kerül; minden meglévő adat felülíródik."
        )
        self.mode_description.setObjectName("muted")
        self.mode_description.setWordWrap(True)
        self.mode_description.setMinimumWidth(0)
        self.mode_description.setMaximumHeight(34 if self._compact_ui else 42)
        self.mode_description.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        mode_layout.addWidget(self.mode_description)
        self.verify_checkbox = QCheckBox("Kiírás utáni teljes visszaolvasás és ellenőrzés")
        self.verify_checkbox.setChecked(True)
        mode_layout.addWidget(self.verify_checkbox)
        root_layout.addWidget(mode_card)

        # Progress / log
        progress_card = QFrame()
        progress_card.setObjectName("panel")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(
            9 if self._compact_ui else 11,
            5 if self._compact_ui else 7,
            9 if self._compact_ui else 11,
            5 if self._compact_ui else 7,
        )
        progress_layout.setSpacing(3 if self._compact_ui else 5)
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
        self.status_label = QLabel("Készen áll.")
        self.status_label.setObjectName("status")
        progress_layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        progress_layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(44 if self._compact_ui else 56)
        self.log.setMinimumWidth(0)
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.log.setMaximumHeight(56 if self._compact_ui else 76)
        self.log.setPlaceholderText("A műveletek és az ellenőrzés részletei itt jelennek meg.")
        progress_layout.addWidget(self.log)
        root_layout.addWidget(progress_card, 1)

        footer = QHBoxLayout()
        self.about_label = QLabel("Linux • helyi, nyílt forráskódú projekt")
        self.about_label.setObjectName("muted")
        self.about_label.setMinimumWidth(0)
        self.about_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.cancel_button = QPushButton("Megszakítás")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_operation)
        self.start_button = QPushButton("USB elkészítése")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumWidth(150)
        self.start_button.setMinimumHeight(34 if self._compact_ui else 38)
        self.cancel_button.setMinimumHeight(34 if self._compact_ui else 38)
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
        self.apply_style()
        self.refresh_devices()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(5000)
        self.refresh_timer.timeout.connect(self.refresh_devices_silently)
        self.refresh_timer.start()

    def fit_window_to_screen(self) -> None:
        """Fit the outer window frame inside the active screen's work area."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        client = self.geometry()
        frame_width = max(0, frame.width() - client.width())
        frame_height = max(0, frame.height() - client.height())

        outer_width = max(560, min(740, available.width() - 24))
        outer_height = max(520, min(900, available.height() - 24))
        client_width = max(560, outer_width - frame_width)
        client_height = max(520, outer_height - frame_height)

        self.setMaximumSize(
            max(560, 740 - frame_width),
            max(520, 900 - frame_height),
        )
        self.resize(client_width, client_height)
        frame = self.frameGeometry()
        self.move(
            available.x() + max(0, (available.width() - frame.width()) // 2),
            available.y() + max(0, (available.height() - frame.height()) // 2),
        )

    def apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: palette(window); }
            QLabel#appTitle { font-size: 27px; font-weight: 750; }
            QLabel#subtitle { color: #aeb9c4; font-size: 9pt; }
            QLabel#muted { color: #b7c1cb; }
            QLabel#version { color: #83bde2; font-size: 9pt; font-weight: 650; padding-right: 10px; }
            QLabel#sectionTitle { font-size: 15px; font-weight: 650; }
            QLabel#status { font-weight: 600; }
            QLabel#elapsed { color: palette(highlight); font-weight: 650; border: 1px solid palette(mid); border-radius: 7px; padding: 3px 8px; min-height: 24px; max-height: 24px; }
            QToolButton#infoButton { color: palette(highlight); border: 1px solid palette(highlight); border-radius: 10px; font-weight: 750; font-size: 10pt; padding: 0; }
            QToolButton#infoButton:hover { background: palette(alternate-base); }
            QToolButton#infoButton:disabled { color: palette(mid); border-color: palette(mid); }
            QFrame#panel { border: 1px solid palette(mid); border-radius: 11px; }
            QFrame#warningPanel { border: 1px solid #b58136; border-radius: 10px; background: rgba(181,129,54,0.10); }
            QLabel#warningIcon { font-size: 21px; font-weight: 700; color: #d19a48; }
            QLineEdit, QComboBox, QPlainTextEdit { border: 1px solid palette(mid); border-radius: 7px; padding: 5px 7px; }
            QComboBox { min-height: 20px; }
            QPushButton { border: 1px solid palette(mid); border-radius: 7px; padding: 6px 10px; }
            QPushButton:hover { border-color: palette(highlight); }
            QPushButton#modeButton { text-align: left; padding: 7px 10px; min-height: 32px; }
            QPushButton#modeButton:checked { border: 2px solid palette(highlight); background: palette(alternate-base); font-weight: 650; }
            QPushButton#primaryButton { background: palette(highlight); color: palette(highlighted-text); font-weight: 700; border: none; padding: 8px 16px; }
            QPushButton#primaryButton:disabled { background: palette(mid); color: palette(window); }
            QProgressBar { border: 1px solid palette(mid); border-radius: 6px; text-align: center; min-height: 18px; }
            QProgressBar::chunk { background: palette(highlight); border-radius: 5px; }
            QCheckBox { spacing: 8px; }
        """)

    def choose_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Lemezkép kiválasztása",
            str(Path.home()),
            "Lemezképek (*.iso *.img *.bin *.raw);;Minden fájl (*)",
        )
        if filename:
            self.iso_edit.setText(filename)
            try:
                selected = Path(filename)
                size = selected.stat().st_size
                is_windows = (
                    selected.suffix.lower() == ".iso"
                    and is_windows_install_iso(selected)
                )
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
                self.file_info.setText("A fájl nem olvasható.")
                self.file_info.setToolTip("A kiválasztott fájl nem olvasható.")

    def refresh_devices_silently(self) -> None:
        # Don't replace the list while a privileged operation is running.
        if self.process is None:
            self.refresh_devices(preserve_selection=True, quiet=True)

    def refresh_devices(self, preserve_selection: bool = False, quiet: bool = False) -> None:
        current = self.device_combo.currentData() if preserve_selection else None
        try:
            devices = run_lsblk()
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as exc:
            if not quiet:
                QMessageBox.warning(self, "Meghajtók listázása", f"Nem sikerült lekérdezni az USB-meghajtókat.\n\n{exc}")
            return

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
            model = (disk.get("model") or disk.get("name") or "USB-meghajtó").strip()
            size = int(disk.get("size") or 0)
            identity = disk_identity(disk)
            partitions = flatten_partitions(disk)
            mounts = mounted_paths(disk)
            unsafe_reason = unsafe_layout_reason(disk)
            tag = "USB" if transport == "usb" else "eltávolítható"
            serial = identity.get("serial") or identity.get("wwn") or identity.get("diskseq") or "nincs sorozatszám"
            label = f"{model}   •   {human_size(size)}   •   {path}   [{tag}]"
            if unsafe_reason:
                label += "   [VÉDETT]"
            data = {
                **identity,
                "path": path,
                "size": size,
                "model": model,
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

        model = self.current_device.get("model") or "Ismeretlen eszköz"
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
            self.mode_description.setText(
                "Windows x64 UEFI: nagy NTFS adatpartíció és BMK_EFI UEFI:NTFS segédpartíció. "
                "A nagy install.esd / install.wim fájlok változatlanul másolódnak. "
                "A teljes SHA-256 visszaellenőrzés opcionális."
            )

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

        mode = "raw" if self.raw_button.isChecked() else "windows"
        device = self.current_device
        if device.get("unsafe_reason"):
            QMessageBox.critical(self, "Védett meghajtó", str(device["unsafe_reason"]))
            return
        if mode == "raw" and image.suffix.lower() == ".iso" and is_windows_install_iso(image):
            QMessageBox.warning(
                self,
                "Windows ISO észlelve",
                "Ez Windows telepítő ISO-nak tűnik. Ne nyers lemezképként írd ki, mert így általában nem lesz bootolható. "
                "Válaszd a „Windows telepítő (UEFI / GPT / NTFS)” módot.",
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
        if mode == "windows":
            details += (
                "\n\nA Windows mód GPT-t hoz létre: nagy NTFS telepítőpartíció és "
                "1 MiB BMK_EFI FAT UEFI:NTFS segédpartíció. A Windows ISO eredeti fájljai másolódnak."
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
            mode,
            str(image.resolve()),
            target_path,
            "1" if self.verify_checkbox.isChecked() else "0",
            identity_json,
        ]

        self.progress.setValue(0)
        self.log.clear()
        self.status_label.setText("Rendszergazdai jogosultság kérése…")
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.refresh_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.device_combo.setEnabled(False)
        self.raw_button.setEnabled(False)
        self.windows_button.setEnabled(False)
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
            self._close_after_operation = True
            self._send_cancel_request()
        event.ignore()

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
        was_closing = self._close_after_operation

        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.progress.setValue(100)
            self.status_label.setText("Sikeres befejezés.")
            self.append_log("Kész. Biztonságosan eltávolíthatod az USB-meghajtót.")
            if not was_closing:
                QMessageBox.information(self, "Elkészült", "Az USB-meghajtó elkészült. Biztonságosan eltávolíthatod.")
        elif self._operation_cancelled or exit_code == 130:
            self.status_label.setText("A művelet biztonságosan megszakítva.")
            self.append_log(
                "A célmeghajtó részleges állapotban maradhat."
                if self._target_modified
                else "A megszakítás a célmeghajtó módosítása előtt történt; a lemez tartalmához nem nyúltunk."
            )
        elif not self._worker_started:
            # pkexec 126/127 and failures before the worker's first structured
            # event cannot have touched the target disk.
            self.status_label.setText("A jogosultságkérés vagy a worker indítása nem sikerült.")
            self.append_log(f"A pkexec kilépési kódja: {exit_code}. A célmeghajtót nem módosítottuk.")
            if not was_closing:
                QMessageBox.information(
                    self,
                    "A művelet nem indult el",
                    "A rendszergazdai jogosultságkérés megszakadt/megtagadásra került, "
                    "vagy a biztonságos worker nem indult el. A célmeghajtóhoz nem nyúltunk.",
                )
        else:
            self.status_label.setText("A művelet nem fejeződött be.")
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
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.refresh_button.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.device_combo.setEnabled(not busy)
        self.raw_button.setEnabled(not busy)
        self.windows_button.setEnabled(not busy)
        self.iso_edit.setEnabled(not busy)
        if not busy:
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("BootMediaKit")
    app.setFont(QFont("Noto Sans", 10))
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("bootmediakit")
    if APP_ICON.is_file():
        app.setWindowIcon(QIcon(str(APP_ICON)))
    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.fit_window_to_screen)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
