#!/usr/bin/env python3
"""Privileged, narrowly-scoped disk writer for BootMediaKit.

This file accepts only whole USB/removable block devices. It refuses the
physical devices backing /, /boot or /efi before it can unmount or erase them.
All status messages are JSON lines for the unprivileged Qt frontend.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable

CHUNK = 4 * 1024 * 1024
FAT32_MAX_FILE = 4 * 1024 * 1024 * 1024 - 1
TARGET_MODIFIED = False


def emit(message: str, percent: int | None = None, *, log: str | None = None,
         error: str | None = None) -> None:
    event: dict[str, object] = {"message": message}
    if percent is not None:
        event["percent"] = max(0, min(100, int(percent)))
    if log:
        event["log"] = log
    if error:
        event["error"] = error
    print(json.dumps(event, ensure_ascii=False), flush=True)


def command(args: list[str], *, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Hiányzó rendszerprogram: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Időtúllépés: {' '.join(args)}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or f"Sikertelen parancs: {' '.join(args)}")
    return result


def require_programs(programs: Iterable[str]) -> None:
    missing = [name for name in programs if shutil.which(name) is None]
    if missing:
        raise RuntimeError("Hiányzó csomag/program: " + ", ".join(missing))


def canonical(path: str) -> str:
    return os.path.realpath(path)


def lsblk_one(path: str, columns: str) -> list[str]:
    result = command(["lsblk", "-dnro", columns, path])
    return result.stdout.strip().split()


def protected_physical_devices() -> set[str]:
    """Return the selected source disk(s) backing system-critical mounts."""
    protected: set[str] = set()
    for target in ("/", "/boot", "/boot/efi", "/efi"):
        result = command(["findmnt", "-nro", "SOURCE", "--target", target], check=False)
        source = result.stdout.strip().split("[", 1)[0]
        if not source.startswith("/dev/"):
            continue
        ancestors = command(["lsblk", "-s", "-nrpo", "PATH", source], check=False)
        for item in ancestors.stdout.splitlines():
            if item.startswith("/dev/"):
                protected.add(canonical(item.strip()))
        protected.add(canonical(source))
    return protected


def validate_target(device: str) -> int:
    if not device.startswith("/dev/"):
        raise RuntimeError("A cél nem érvényes /dev eszköz.")
    try:
        info = os.stat(device)
    except OSError as exc:
        raise RuntimeError(f"A célmeghajtó nem érhető el: {exc}") from exc
    if not stat.S_ISBLK(info.st_mode):
        raise RuntimeError("A cél csak valódi blokk eszköz lehet; fájlba írás nem engedélyezett.")

    fields = lsblk_one(device, "TYPE,TRAN,RM,RO")
    if len(fields) < 4 or fields[0] != "disk":
        raise RuntimeError("Partíció helyett a teljes USB-lemezt válaszd ki.")
    _, transport, removable, readonly = fields[:4]
    if readonly == "1":
        raise RuntimeError("A célmeghajtó írásvédett.")
    if transport.lower() != "usb" and removable != "1":
        raise RuntimeError("Biztonsági okból csak USB vagy eltávolítható lemezre lehet írni.")
    if canonical(device) in protected_physical_devices():
        raise RuntimeError("A kiválasztott lemez a rendszer (/ vagy /boot) meghajtója. A műveletet leállítottam.")

    size_text = command(["blockdev", "--getsize64", device]).stdout.strip()
    try:
        size = int(size_text)
    except ValueError as exc:
        raise RuntimeError("Nem sikerült lekérdezni a célmeghajtó kapacitását.") from exc
    return size


def unmount_disk(device: str) -> None:
    result = command(["lsblk", "-nrpo", "PATH,TYPE", device])
    partitions = []
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) >= 2 and columns[1] == "part":
            partitions.append(columns[0])
    # Unmount child filesystems from their mount points, deepest mount first.
    for partition in partitions:
        mounts = command(["findmnt", "-rn", "-S", partition, "-o", "TARGET"], check=False).stdout.splitlines()
        for mountpoint in sorted((m.strip() for m in mounts if m.strip()), key=len, reverse=True):
            emit(f"Partíció leválasztása: {mountpoint}", 1)
            command(["umount", "--", mountpoint])
    command(["udevadm", "settle"], check=False, timeout=15)


def wipe_signatures(device: str) -> None:
    # The user already confirmed total erasure in the GUI. Removing stale
    # signatures also prevents an old backup GPT at the end of a larger stick.
    command(["wipefs", "--all", "--force", device])
    command(["sync"])


def write_raw(image: Path, device: str, verify: bool) -> None:
    global TARGET_MODIFIED
    source_size = image.stat().st_size
    target_size = validate_target(device)
    if source_size <= 0:
        raise RuntimeError("A lemezkép üres.")
    if source_size > target_size:
        raise RuntimeError("A lemezkép nagyobb, mint a célmeghajtó.")

    require_programs(("lsblk", "blockdev", "findmnt", "umount", "wipefs", "udevadm", "sync"))
    emit("Célmeghajtó ellenőrzése…", 1, log=f"Forrás: {image} ({source_size:,} bájt); cél: {device} ({target_size:,} bájt)")
    unmount_disk(device)
    emit("Régi partíciós és fájlrendszer-aláírások eltávolítása…", 2)
    TARGET_MODIFIED = True
    wipe_signatures(device)

    emit("Lemezkép kiírása…", 3)
    offset = 0
    fd = os.open(device, os.O_WRONLY)
    try:
        with image.open("rb", buffering=0) as source:
            while True:
                data = source.read(CHUNK)
                if not data:
                    break
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise RuntimeError(f"Nem sikerült tovább írni a célmeghajtót (offset: {offset}).")
                    offset += written
                    view = view[written:]
                percent = 3 + int((offset / source_size) * (57 if verify else 96))
                emit(f"Lemezkép kiírása… {offset:,} / {source_size:,} bájt", percent)
        os.fsync(fd)
    finally:
        os.close(fd)

    command(["sync"])
    if verify:
        emit("Visszaolvasás és adategyezőség ellenőrzése…", 61)
        compared = 0
        with image.open("rb", buffering=0) as source:
            target_fd = os.open(device, os.O_RDONLY)
            try:
                while True:
                    expected = source.read(CHUNK)
                    if not expected:
                        break
                    actual = os.read(target_fd, len(expected))
                    if actual != expected:
                        mismatch = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
                        raise RuntimeError(f"Visszaolvasási hiba a(z) {compared + mismatch:,}. bájtnál. A meghajtó vagy az USB-kapcsolat hibás lehet.")
                    compared += len(expected)
                    percent = 61 + int((compared / source_size) * 38)
                    emit(f"Ellenőrzés… {compared:,} / {source_size:,} bájt", percent)
            finally:
                os.close(target_fd)
    command(["blockdev", "--rereadpt", device], check=False)
    command(["udevadm", "settle"], check=False, timeout=15)
    command(["sync"])
    emit("A lemezkép sikeresen kiírva és ellenőrizve." if verify else "A lemezkép sikeresen kiírva.", 100)


def find_case_insensitive(root: Path, relative: str) -> Path | None:
    current = root
    for component in relative.replace("\\", "/").strip("/").split("/"):
        if not current.is_dir():
            return None
        try:
            match = next((entry for entry in current.iterdir() if entry.name.lower() == component.lower()), None)
        except OSError:
            return None
        if match is None:
            return None
        current = match
    return current


def mount_iso(image: Path, mountpoint: Path) -> None:
    mountpoint.mkdir(parents=True, exist_ok=True)
    command(["mount", "-o", "loop,ro,nosuid,nodev", str(image), str(mountpoint)])


def copy_tree_progress(source_root: Path, destination_root: Path, skipped: set[str], total_bytes: int, *, base_percent: int = 40, span: int = 45) -> None:
    copied = 0
    for current, dirs, files in os.walk(source_root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source_root)
        target_dir = destination_root / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        # Do not follow symlinked directories from ISO content.
        dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
        for filename in files:
            src = current_path / filename
            relative = src.relative_to(source_root).as_posix()
            if relative.lower() in skipped:
                continue
            if src.is_symlink():
                raise RuntimeError(f"A telepítő ISO szimbolikus linket tartalmaz, ezt a FAT32 cél nem tudja biztonságosan kezelni: {relative}")
            dst = destination_root / src.relative_to(source_root)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with src.open("rb") as read_file, dst.open("wb") as write_file:
                while True:
                    data = read_file.read(CHUNK)
                    if not data:
                        break
                    write_file.write(data)
                    copied += len(data)
                    percent = base_percent + int((copied / max(total_bytes, 1)) * span)
                    emit(f"Windows fájlok másolása… {copied:,} / {total_bytes:,} bájt", percent)
            # Windows installer only needs file data; do not carry Unix mode bits.
    emit("Windows telepítőfájlok átmásolva.", base_percent + span)


def run_wimlib(args: list[str], *, title: str, percent: int) -> None:
    """Run wimlib while forwarding its progress output to the GUI."""
    try:
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("A Windows telepítő WIM/ESD feldolgozásához telepítsd a wimlib csomagot.") from exc
    assert proc.stdout is not None
    recent_output: list[str] = []
    for line in proc.stdout:
        cleaned = line.strip()
        if cleaned:
            recent_output.append(cleaned)
            recent_output = recent_output[-6:]
            emit(title, percent, log=cleaned)
    code = proc.wait()
    if code != 0:
        detail = " | ".join(recent_output)
        suffix = f" Részletek: {detail}" if detail else ""
        raise RuntimeError(f"A wimlib művelet hibával leállt (kód: {code}).{suffix}")


def split_wim(wim_path: Path, output_path: Path) -> list[Path]:
    emit("A Windows telepítő WIM feldarabolása…", 29,
         log="A FAT32 fájlméretkorlát miatt legfeljebb 3500 MiB-os .swm részek készülnek.")
    run_wimlib(
        ["wimlib-imagex", "split", str(wim_path), str(output_path), "3500", "--include-integrity"],
        title="WIM feldarabolása…", percent=30,
    )
    # A temporary work directory is newly created for each operation, so no
    # stale files can be mistaken for output from this split operation.
    parts = sorted(
        (p for p in output_path.parent.glob("install*.swm")
         if p.is_file() and re.fullmatch(r"install(?:\d+)?\.swm", p.name, re.IGNORECASE)),
        key=lambda p: (0 if p.name.lower() == "install.swm" else int(''.join(ch for ch in p.stem if ch.isdigit()) or 0)),
    )
    if not parts or not any(p.name.lower() == "install.swm" for p in parts):
        raise RuntimeError("A wimlib nem hozta létre az install.swm fájlokat.")
    too_large = [p.name for p in parts if p.stat().st_size > FAT32_MAX_FILE]
    if too_large:
        raise RuntimeError("A WIM egyetlen belső adatblokkja miatt a bontott fájl is 4 GiB fölé került: " + ", ".join(too_large))
    return parts


def export_esd_to_wim(esd_path: Path, output_wim: Path) -> None:
    """Convert a non-encrypted solid ESD to a regular LZX-compressed WIM."""
    emit("A nagy install.esd átalakítása hagyományos WIM formátumba…", 12,
         log="A wimlib minden telepítőképet megtart; a kimenet a munkatárhelyre kerül.")
    run_wimlib(
        ["wimlib-imagex", "export", str(esd_path), "all", str(output_wim), "--compress=LZX"],
        title="install.esd átalakítása WIM-mé…", percent=14,
    )
    if not output_wim.is_file() or output_wim.stat().st_size == 0:
        raise RuntimeError("A wimlib nem hozta létre az átalakított install.wim fájlt.")
    emit("Az átalakított WIM integritásának ellenőrzése…", 24)
    run_wimlib(
        ["wimlib-imagex", "verify", str(output_wim)],
        title="WIM integritásellenőrzése…", percent=25,
    )


def copy_split_parts(parts: list[Path], destination: Path) -> None:
    total = sum(p.stat().st_size for p in parts)
    copied = 0
    for part in parts:
        target = destination / part.name
        with part.open("rb") as src, target.open("wb") as dst:
            while True:
                data = src.read(CHUNK)
                if not data:
                    break
                dst.write(data)
                copied += len(data)
                percent = 86 + int((copied / max(total, 1)) * 10)
                emit(f"SWM fájlok másolása… {copied:,} / {total:,} bájt", percent)
    emit("A darabolt Windows képfájlok átmásolva.", 96)


def write_windows_uefi(image: Path, device: str) -> None:
    global TARGET_MODIFIED
    target_size = validate_target(device)
    require_programs(("lsblk", "blockdev", "findmnt", "umount", "wipefs", "udevadm", "sync",
                      "mount", "parted", "partprobe", "mkfs.fat"))
    iso_mount: Path | None = None
    usb_mount: Path | None = None
    mounted_iso = False
    mounted_usb = False
    temp_root = Path(tempfile.mkdtemp(prefix="bootmediakit-", dir="/run"))
    work_root: Path | None = None
    try:
        # Keep the target mounted and untouched while all ISO conversion and
        # capacity checks run. It is unmounted only immediately before writing.
        iso_mount = temp_root / "iso"
        usb_mount = temp_root / "usb"
        emit("Windows ISO ellenőrzése…", 1)
        mount_iso(image, iso_mount)
        mounted_iso = True

        efi_loader = find_case_insensitive(iso_mount, "efi/boot/bootx64.efi")
        if efi_loader is None or not efi_loader.is_file():
            raise RuntimeError("Ez az ISO nem tartalmaz szabványos x64 UEFI indítófájlt (EFI/BOOT/BOOTX64.EFI).")
        sources_dir = find_case_insensitive(iso_mount, "sources")
        if sources_dir is None or not sources_dir.is_dir():
            raise RuntimeError("Nem található a Windows ISO sources könyvtára.")
        wim = find_case_insensitive(sources_dir, "install.wim")
        esd = find_case_insensitive(sources_dir, "install.esd")
        if wim is None and esd is None:
            raise RuntimeError("Nem található install.wim vagy install.esd a Windows ISO-ban.")
        if wim is not None and esd is not None:
            raise RuntimeError("Az ISO egyszerre tartalmaz install.wim és install.esd fájlt. A biztonságos automatikus kiválasztás nem lehetséges.")

        oversized_wim: Path | None = None
        oversized_esd: Path | None = None
        copy_bytes = 0
        for current, dirs, files in os.walk(iso_mount):
            current_path = Path(current)
            for directory in list(dirs):
                if (current_path / directory).is_symlink():
                    raise RuntimeError("Az ISO szimbolikus könyvtárlinket tartalmaz, ez a változat nem támogatja.")
            for name in files:
                path = current_path / name
                if path.is_symlink():
                    raise RuntimeError("Az ISO szimbolikus fájllinket tartalmaz, ez a változat nem támogatja.")
                size = path.stat().st_size
                if size > FAT32_MAX_FILE:
                    if wim is not None and path == wim:
                        oversized_wim = wim
                    elif esd is not None and path == esd:
                        oversized_esd = esd
                    else:
                        raise RuntimeError(f"A FAT32 4 GiB fájlkorlátja miatt ez a fájl nem másolható: {path.relative_to(iso_mount)}")
                else:
                    copy_bytes += size

        oversized_source = oversized_wim or oversized_esd
        split_parts: list[Path] = []
        if oversized_source:
            require_programs(("wimlib-imagex",))
            # /var/tmp is used rather than /run: converting an ESD can require
            # several gigabytes and /run is commonly a small RAM-backed tmpfs.
            scratch_base = Path("/var/tmp")
            if not scratch_base.is_dir():
                raise RuntimeError("A /var/tmp munkatárhely nem érhető el a nagy Windows képfájl feldolgozásához.")
            source_size = oversized_source.stat().st_size
            free_space = shutil.disk_usage(scratch_base).free
            # Peak use is the converted WIM plus its split SWM output. A
            # conservative estimate prevents filling the root filesystem.
            required_scratch = source_size * 3 + 1024 * 1024 * 1024
            if free_space < required_scratch:
                raise RuntimeError(
                    "Nincs elég szabad ideiglenes tárhely a nagy Windows képfájl biztonságos feldolgozásához. "
                    f"Becsült szükséglet: {required_scratch / (1024**3):.1f} GiB; "
                    f"szabad hely a /var/tmp fájlrendszeren: {free_space / (1024**3):.1f} GiB."
                )
            work_root = Path(tempfile.mkdtemp(prefix="bootmediakit-wim-", dir=str(scratch_base)))
            if oversized_esd:
                converted_wim = work_root / "install.wim"
                export_esd_to_wim(oversized_esd, converted_wim)
                required_for_split = converted_wim.stat().st_size + 1024 * 1024 * 1024
                remaining = shutil.disk_usage(work_root).free
                if remaining < required_for_split:
                    raise RuntimeError(
                        "Az ESD átalakítása elkészült, de nincs elég szabad hely a daraboláshoz. "
                        f"Szükséges még: {required_for_split / (1024**3):.1f} GiB; "
                        f"szabad hely: {remaining / (1024**3):.1f} GiB. A pendrive-hoz még nem nyúltam."
                    )
                split_parts = split_wim(converted_wim, work_root / "install.swm")
                converted_wim.unlink(missing_ok=True)
            else:
                assert oversized_wim is not None
                split_parts = split_wim(oversized_wim, work_root / "install.swm")

        split_bytes = sum(p.stat().st_size for p in split_parts)
        required = copy_bytes + split_bytes + 128 * 1024 * 1024
        if required > target_size:
            raise RuntimeError(
                "Kevés a pendrive kapacitása az elkészült Windows telepítőhöz. "
                f"Becsült igény tartalékkal: {required / (1024**3):.2f} GiB; "
                f"a meghajtó kapacitása: {target_size / (1024**3):.2f} GiB. "
                "A pendrive tartalmát még nem töröltem."
            )

        emit("USB-meghajtó GPT/FAT32 előkészítése…", 35)
        unmount_disk(device)
        TARGET_MODIFIED = True
        wipe_signatures(device)
        command(["parted", "-s", device, "mklabel", "gpt"])
        command(["parted", "-s", device, "mkpart", "primary", "fat32", "1MiB", "100%"])
        command(["parted", "-s", device, "set", "1", "esp", "on"])
        command(["partprobe", device], check=False)
        command(["udevadm", "settle"], check=False, timeout=15)

        partition = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = command(["lsblk", "-nrpo", "PATH,TYPE", device], check=False)
            for line in result.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 2 and fields[1] == "part":
                    partition = fields[0]
                    break
            if partition:
                break
            time.sleep(0.5)
        if not partition:
            raise RuntimeError("A GPT partíció elkészült, de a kernel nem találja az USB partícióját.")

        emit("FAT32 fájlrendszer létrehozása…", 38)
        command(["mkfs.fat", "-F", "32", "-n", "BOOTMEDIA", partition])
        command(["udevadm", "settle"], check=False, timeout=15)
        unmount_disk(device)
        usb_mount.mkdir(parents=True, exist_ok=True)
        command(["mount", partition, str(usb_mount)])
        mounted_usb = True

        skipped: set[str] = set()
        if oversized_source:
            skipped.add(oversized_source.relative_to(iso_mount).as_posix().lower())
        copy_tree_progress(iso_mount, usb_mount, skipped, copy_bytes, base_percent=40, span=45)

        if split_parts:
            dest_sources = find_case_insensitive(usb_mount, "sources")
            if dest_sources is None:
                raise RuntimeError("A másolás után nem található a cél sources könyvtára.")
            copy_split_parts(split_parts, dest_sources)

        emit("Fájlrendszer kiürítése és leválasztása…", 98)
        command(["sync"])
        command(["umount", "--", str(usb_mount)])
        mounted_usb = False
        command(["sync"])
        emit("A Windows UEFI telepítő USB elkészült.", 100,
             log="GPT + FAT32, x64 UEFI. A célmeghajtó adatai törlődtek.")
    finally:
        if mounted_usb and usb_mount:
            command(["umount", "--", str(usb_mount)], check=False)
        if mounted_iso and iso_mount:
            command(["umount", "--", str(iso_mount)], check=False)
        if TARGET_MODIFIED:
            try:
                unmount_disk(device)
            except Exception:
                pass
        shutil.rmtree(temp_root, ignore_errors=True)
        if work_root:
            shutil.rmtree(work_root, ignore_errors=True)
        command(["udevadm", "settle"], check=False, timeout=15)

def main(argv: list[str]) -> int:
    global TARGET_MODIFIED
    TARGET_MODIFIED = False
    if len(argv) < 4:
        emit("Hibás paraméterezés.", error="Használat: worker.py raw|windows ISO DEVICE [VERIFY]")
        return 2
    mode, image_arg, device = argv[1:4]
    image = Path(image_arg).expanduser()
    if os.geteuid() != 0:
        emit("A háttérfolyamat nem kapott rendszergazdai jogosultságot.", error="A művelethez pkexec szükséges.")
        return 1
    if not image.is_file() or not os.access(image, os.R_OK):
        emit("A forrásfájl nem olvasható.", error=str(image))
        return 1
    try:
        if mode == "raw":
            verify = len(argv) >= 5 and argv[4] == "1"
            write_raw(image, device, verify)
        elif mode == "windows":
            if image.suffix.lower() != ".iso":
                raise RuntimeError("Windows telepítő készítéséhez ISO fájl szükséges.")
            write_windows_uefi(image, device)
        else:
            raise RuntimeError("Ismeretlen írási mód.")
        return 0
    except Exception as exc:  # all failures must reach the GUI as one clean event
        if TARGET_MODIFIED:
            state_log = "A célmeghajtó állapota részleges lehet; ellenőrizd újracsatlakoztatás után."
        else:
            state_log = "A célmeghajtó tartalmának módosítása nem kezdődött el; legfeljebb a csatolási állapota változhatott."
        emit("A művelet megszakadt.", error=str(exc), log=state_log)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
