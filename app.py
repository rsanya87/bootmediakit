#!/usr/bin/env python3
"""BootMediaKit - a native Linux bootable USB creator for Arch-based Linux.

The GUI deliberately runs unprivileged. Only the narrowly-scoped worker is
launched via pkexec when the user confirms a destructive operation.
"""

from __future__ import annotations

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
    QWidget,
)

from iso_utils import is_windows_install_iso
from ui_helpers import format_elapsed_time

APP_VERSION = "0.1.3-alpha"
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
        self.setMinimumSize(620, 540)
        self.resize(740, 670)
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
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(8)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("BootMediaKit")
        title.setObjectName("appTitle")
        subtitle = QLabel("Bootolható USB-meghajtók készítése Linux alatt")
        subtitle.setObjectName("subtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch(1)
        version = QLabel(APP_VERSION)
        version.setObjectName("version")
        header.addWidget(version, alignment=Qt.AlignmentFlag.AlignTop)
        root_layout.addLayout(header)

        warning = QFrame()
        warning.setObjectName("warningPanel")
        warning_layout = QHBoxLayout(warning)
        warning_layout.setContentsMargins(10, 7, 10, 7)
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
        image_layout.setContentsMargins(12, 9, 12, 9)
        image_layout.setSpacing(6)
        image_label = QLabel("1. Lemezkép kiválasztása")
        image_label.setObjectName("sectionTitle")
        image_layout.addWidget(image_label)
        image_row = QHBoxLayout()
        self.iso_edit = QLineEdit()
        self.iso_edit.setPlaceholderText("Válassz ISO / IMG / BIN fájlt…")
        self.iso_edit.setClearButtonEnabled(True)
        self.iso_edit.setMinimumHeight(32)
        self.browse_button = QPushButton("Tallózás…")
        self.browse_button.clicked.connect(self.choose_image)
        image_row.addWidget(self.iso_edit, 1)
        image_row.addWidget(self.browse_button)
        image_layout.addLayout(image_row)
        self.file_info = QLabel("Támogatott formátumok: ISO, IMG, BIN, RAW")
        self.file_info.setObjectName("muted")
        image_layout.addWidget(self.file_info)
        root_layout.addWidget(image_card)

        # Device selection
        device_card = QFrame()
        device_card.setObjectName("panel")
        device_layout = QVBoxLayout(device_card)
        device_layout.setContentsMargins(12, 9, 12, 9)
        device_layout.setSpacing(6)
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
        self.device_combo.setMinimumHeight(34)
        self.device_combo.currentIndexChanged.connect(self.device_changed)
        device_layout.addWidget(self.device_combo)
        self.device_detail = QLabel("Csatlakoztass egy USB-meghajtót, majd frissítsd a listát.")
        self.device_detail.setObjectName("muted")
        self.device_detail.setWordWrap(True)
        device_layout.addWidget(self.device_detail)
        root_layout.addWidget(device_card)

        # Mode selection
        mode_card = QFrame()
        mode_card.setObjectName("panel")
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(12, 9, 12, 9)
        mode_layout.setSpacing(6)
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
        mode_layout.addWidget(self.mode_description)
        self.verify_checkbox = QCheckBox("Kiírás utáni teljes visszaolvasás és ellenőrzés")
        self.verify_checkbox.setChecked(True)
        mode_layout.addWidget(self.verify_checkbox)
        root_layout.addWidget(mode_card)

        # Progress / log
        progress_card = QFrame()
        progress_card.setObjectName("panel")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(12, 9, 12, 9)
        progress_layout.setSpacing(6)
        progress_header = QHBoxLayout()
        progress_title = QLabel("Művelet állapota")
        progress_title.setObjectName("sectionTitle")
        self.elapsed_label = QLabel("Eltelt idő: 00:00")
        self.elapsed_label.setObjectName("elapsed")
        self.elapsed_label.setToolTip("A pendrive-készítés tényleges futási ideje")
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
        self.log.setMinimumHeight(68)
        self.log.setMaximumHeight(128)
        self.log.setPlaceholderText("A műveletek és az ellenőrzés részletei itt jelennek meg.")
        progress_layout.addWidget(self.log)
        root_layout.addWidget(progress_card, 1)

        footer = QHBoxLayout()
        self.about_label = QLabel("Linux • helyi, nyílt forráskódú projekt")
        self.about_label.setObjectName("muted")
        self.cancel_button = QPushButton("Megszakítás")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_operation)
        self.start_button = QPushButton("USB elkészítése")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumWidth(168)
        self.start_button.setMinimumHeight(40)
        self.start_button.clicked.connect(self.start_operation)
        footer.addWidget(self.about_label, 1)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.start_button)
        root_layout.addLayout(footer)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setWidget(root)
        self.setCentralWidget(scroll_area)
        self.apply_style()
        self.refresh_devices()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(5000)
        self.refresh_timer.timeout.connect(self.refresh_devices_silently)
        self.refresh_timer.start()

    def apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: palette(window); }
            QLabel#appTitle { font-size: 27px; font-weight: 750; }
            QLabel#subtitle, QLabel#muted, QLabel#version { color: palette(mid); }
            QLabel#version { padding: 5px 9px; border: 1px solid palette(mid); border-radius: 7px; }
            QLabel#sectionTitle { font-size: 15px; font-weight: 650; }
            QLabel#status { font-weight: 600; }
            QLabel#elapsed { color: palette(highlight); font-weight: 650; border: 1px solid palette(mid); border-radius: 7px; padding: 4px 8px; }
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
                description = f"{selected.name}  •  {human_size(size)}"
                if selected.suffix.lower() == ".iso" and is_windows_install_iso(selected):
                    description += "  •  Windows telepítő ISO felismerve"
                self.file_info.setText(description)
            except OSError:
                self.file_info.setText("A fájl nem olvasható.")

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
            return
        mounts = self.current_device.get("mounts") or []
        message = (
            f"Kapacitás: {human_size(self.current_device['size'])}. "
            f"Azonosító: {self.current_device.get('serial_display') or 'ismeretlen'}."
        )
        partitions = self.current_device.get("partitions") or []
        if partitions:
            rows = []
            for part in partitions:
                fs = part.get("fstype") or part.get("type") or "ismeretlen"
                label = part.get("label") or "nincs címke"
                size = human_size(int(part.get("size") or 0))
                part_mounts = part.get("mountpoints") or []
                if isinstance(part_mounts, str):
                    part_mounts = [part_mounts]
                mount_text = ", ".join(str(x) for x in part_mounts if x) or "nincs csatolva"
                rows.append(f"{part.get('path')} • {fs} • {label} • {size} • {mount_text}")
            message += "\nPartíciók:\n" + "\n".join(rows)
        if mounts:
            message += "\nCsatolási pont(ok): " + ", ".join(mounts) + ". A készítés előtt leválasztjuk őket."
        else:
            message += "\nNincs csatolt partíció."
        if self.current_device.get("unsafe_reason"):
            message += "\n" + self.current_device["unsafe_reason"]
        self.device_detail.setText(message)

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
        if mode == "raw" and image.suffix.lower() == ".iso" and is_windows_install_iso(image):
            QMessageBox.warning(
                self,
                "Windows ISO észlelve",
                "Ez Windows telepítő ISO-nak tűnik. Ne nyers lemezképként írd ki, mert így általában nem lesz bootolható. "
                "Válaszd a „Windows telepítő (UEFI / GPT / NTFS)” módot.",
            )
            return
        if mode == "raw" and image.stat().st_size > device["size"]:
            QMessageBox.warning(self, "Kevés tárhely", "A lemezkép nagyobb, mint a kiválasztott USB-meghajtó.")
            return
        if mode == "windows" and image.suffix.lower() != ".iso":
            QMessageBox.warning(self, "Windows ISO szükséges", "A Windows telepítő módhoz ISO fájlt válassz.")
            return

        details = (
            f"Forrás: {image}\n"
            f"Cél: {device['path']}\n"
            f"Meghajtó: {device['model']} ({human_size(device['size'])})\n\n"
            "A célmeghajtó MINDEN partíciója és adata törlődni fog."
        )
        if mode == "windows":
            details += "\n\nA készítő GPT lemezt hoz létre: egy nagy NTFS partíciót az eredeti Windows ISO fájloknak, valamint egy 1 MiB-os FAT BMK_EFI UEFI:NTFS segédpartíciót a lemez végén. A kis FAT partíció Microsoft Basic Data típusú, GUID:63 NoDriveLetter attribútummal; szándékosan nem EFI System Partition, hogy a Windows Setup ne találjon második ESP-t. Az install.esd / install.wim változatlan marad. UEFI x64 szükséges; Secure Boot támogatás a firmware tanúsítványaitól és visszavonási listájától függ.\n\nFontos telepítési tanács: a Windows Setup több belső HDD/SSD mellett néha nem a kiválasztott céllemezt azonosítja rendszerindító lemezként. Ha a telepítés a rendszer/boot kötet előkészítésénél hibázik, próbáld ideiglenesen leválasztani a nem célként használt belső meghajtókat. A lemezek tartalmát ne töröld emiatt."
        reply = QMessageBox.warning(
            self,
            "Végleges megerősítés szükséges",
            details,
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not WORKER.is_file():
            QMessageBox.critical(self, "Hiányzó háttérfolyamat", f"Nem található a háttérfolyamat:\n{WORKER}")
            return
        if not shutil.which("pkexec"):
            QMessageBox.critical(self, "Hiányzó pkexec", "A pkexec / polkit nem található. Telepítsd a polkit csomagot.")
            return

        args = ["/usr/bin/python3", str(WORKER), mode, str(image), str(device["path"])]
        args.append("1" if self.verify_checkbox.isChecked() else "0")

        self.progress.setValue(0)
        self.log.clear()
        self.status_label.setText("Rendszergazdai jogosultság kérése…")
        self.start_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.device_combo.setEnabled(False)
        self.raw_button.setEnabled(False)
        self.windows_button.setEnabled(False)
        self.iso_edit.setEnabled(False)

        self.output_buffer = ""
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
            self.status_label.setText("A háttérfolyamat nem indult el.")
            self.process = None

    def operation_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self.read_stdout()
        if self.output_buffer.strip():
            self.handle_worker_line(self.output_buffer.strip())
            self.output_buffer = ""
        self.stop_operation_clock()
        self.set_busy(False)
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.progress.setValue(100)
            self.status_label.setText("Sikeres befejezés.")
            self.append_log("Kész. Biztonságosan eltávolíthatod az USB-meghajtót.")
            QMessageBox.information(self, "Elkészült", "Az USB-meghajtó elkészült. Biztonságosan eltávolíthatod.")
        else:
            self.status_label.setText("A művelet nem fejeződött be.")
            self.append_log(f"A háttérfolyamat kilépési kódja: {exit_code}")
            QMessageBox.critical(
                self,
                "Sikertelen művelet",
                "A művelet nem fejeződött be. A naplóban látható a hiba oka. "
                "A célmeghajtó állapota részleges lehet; újrahasználat előtt formázd meg vagy készítsd el újra.",
            )
        self.process = None
        self.refresh_devices(preserve_selection=True, quiet=True)

    def set_busy(self, busy: bool) -> None:
        self.start_button.setEnabled(not busy)
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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
