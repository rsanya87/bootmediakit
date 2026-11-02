#!/usr/bin/env python3
"""Privileged disk writer for BootMediaKit.

The Qt front-end stays unprivileged. This worker is started with pkexec only
after a destructive-operation confirmation. It validates the target twice
and keeps Windows ISO inspection/capacity checks ahead of all disk writes.
"""

from __future__ import annotations

import errno
import hashlib
import json
import struct
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable

CHUNK = 8 * 1024 * 1024
UEFI_NTFS_IMAGE = Path("/usr/share/bootmediakit/uefi/uefi-ntfs.img")
UEFI_NTFS_IMAGE_SIZE = 1_048_576
UEFI_NTFS_GIT_BLOB_SHA1 = "ac50eed9730af847c43c145a5c17678f54128b33"
UEFI_NTFS_SHA256 = "72683fa1250eeea772d3399277b434d4e55ba8dd0dc926e52d817e701fc2eb9e"
GPT_ESP_GUID = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
GPT_BASIC_DATA_GUID = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
GPT_ALIGNMENT_SECTORS = 2048
GPT_RESERVED_SECTORS = 34
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


def command(
    args: list[str],
    *,
    check: bool = True,
    timeout: int | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
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
        raise RuntimeError("Hiányzó rendszerprogram/csomag: " + ", ".join(missing))


def canonical(path: str) -> str:
    return os.path.realpath(path)


def lsblk_one(path: str, columns: str) -> list[str]:
    result = command(["lsblk", "-dnro", columns, path])
    return result.stdout.strip().split()


def protected_physical_devices() -> set[str]:
    """Return devices backing critical system mountpoints and their parents."""
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
    """Validate the whole target disk and return its byte capacity."""
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
        return int(size_text)
    except ValueError as exc:
        raise RuntimeError("Nem sikerült lekérdezni a célmeghajtó kapacitását.") from exc


def unmount_disk(device: str) -> None:
    result = command(["lsblk", "-nrpo", "PATH,TYPE", device])
    partitions: list[str] = []
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) >= 2 and columns[1] == "part":
            partitions.append(columns[0])
    for partition in partitions:
        mounts = command(
            ["findmnt", "-rn", "-S", partition, "-o", "TARGET"], check=False
        ).stdout.splitlines()
        for mountpoint in sorted((m.strip() for m in mounts if m.strip()), key=len, reverse=True):
            emit(f"Partíció leválasztása: {mountpoint}", 1)
            command(["umount", "--", mountpoint])
    command(["udevadm", "settle"], check=False, timeout=15)


def find_case_insensitive(root: Path, relative: str) -> Path | None:
    current = root
    for component in relative.replace("\\", "/").strip("/").split("/"):
        if not current.is_dir():
            return None
        try:
            match = next(
                (entry for entry in current.iterdir() if entry.name.lower() == component.lower()),
                None,
            )
        except OSError:
            return None
        if match is None:
            return None
        current = match
    return current


def git_blob_sha1(path: Path) -> str:
    """Compute the Git object SHA-1 used to pin the upstream UEFI helper image."""
    size = path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as source:
        while True:
            data = source.read(CHUNK)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()


def verify_uefi_ntfs_image(path: Path = UEFI_NTFS_IMAGE) -> None:
    if not path.is_file():
        raise RuntimeError(
            "Hiányzik az UEFI:NTFS indítópartíció képfájlja. "
            "Telepítsd újra a BootMediaKit-et, hogy letöltse és ellenőrizze a hivatalos fájlt."
        )
    actual_size = path.stat().st_size
    if actual_size != UEFI_NTFS_IMAGE_SIZE:
        raise RuntimeError(
            f"Hibás UEFI:NTFS képméret: {actual_size} bájt; "
            f"elvárt: {UEFI_NTFS_IMAGE_SIZE} bájt."
        )
    actual_hash = git_blob_sha1(path)
    if actual_hash != UEFI_NTFS_GIT_BLOB_SHA1:
        raise RuntimeError(
            "Az UEFI:NTFS segédkép Git-blob azonosítója nem egyezik a rögzített hivatalos verzióval. "
            "A biztonság kedvéért nem írok a pendrive-ra."
        )
    sha256 = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(CHUNK), b""):
            sha256.update(block)
    if sha256.hexdigest() != UEFI_NTFS_SHA256:
        raise RuntimeError(
            "Az UEFI:NTFS segédkép SHA-256 ellenőrzőösszege nem egyezik a rögzített hivatalos verzióval. "
            "A biztonság kedvéért nem írok a pendrive-ra."
        )


def calculate_gpt_layout(total_sectors: int, image_size: int = UEFI_NTFS_IMAGE_SIZE) -> dict[str, int]:
    """Calculate aligned GPT partitions in 512-byte logical sectors.

    Partition 1 is Microsoft Basic Data (NTFS); partition 2 is the EFI System
    Partition containing the exact 1 MiB upstream UEFI:NTFS FAT image.
    """
    sector_size = 512
    if total_sectors <= 0 or image_size <= 0:
        raise ValueError("A lemez- és képméretnek pozitívnak kell lennie.")
    if image_size % sector_size:
        raise ValueError("Az UEFI:NTFS kép mérete nem egész szektorszám.")
    image_sectors = image_size // sector_size
    last_usable = total_sectors - GPT_RESERVED_SECTORS
    latest_start = last_usable - image_sectors + 1
    second_start = (latest_start // GPT_ALIGNMENT_SECTORS) * GPT_ALIGNMENT_SECTORS
    first_start = GPT_ALIGNMENT_SECTORS
    first_size = second_start - first_start
    if first_size <= 0 or second_start + image_sectors - 1 > last_usable:
        raise ValueError("A meghajtó túl kicsi az UEFI:NTFS kétpartíciós elrendezéshez.")
    return {
        "first_start": first_start,
        "first_size": first_size,
        "second_start": second_start,
        "second_size": image_sectors,
        "first_bytes": first_size * sector_size,
        "second_bytes": image_sectors * sector_size,
    }


def partition_path(device: str, number: int) -> str:
    """Resolve /dev/sdX1 and /dev/nvme0n1p1 style partition names."""
    base = os.path.basename(device)
    separator = "p" if base and base[-1].isdigit() else ""
    return f"{device}{separator}{number}"


def make_sfdisk_script(layout: dict[str, int]) -> str:
    return (
        "label: gpt\n"
        "unit: sectors\n"
        f"first-lba: {GPT_ALIGNMENT_SECTORS}\n"
        f"start={layout['first_start']}, size={layout['first_size']}, "
        f"type={GPT_BASIC_DATA_GUID}, name=\"BOOTMEDIA\"\n"
        f"start={layout['second_start']}, size={layout['second_size']}, "
        f"type={GPT_ESP_GUID}, name=\"BOOTMEDIA_EFI\"\n"
    )


def mount_iso(image: Path, mountpoint: Path) -> None:
    mountpoint.mkdir(parents=True, exist_ok=True)
    command(["mount", "-o", "loop,ro,nosuid,nodev", str(image), str(mountpoint)])


def scan_windows_iso(iso_root: Path) -> tuple[Path, Path, int]:
    """Validate essential x64 Windows Setup files and return install image + size."""
    efi_loader = find_case_insensitive(iso_root, "efi/boot/bootx64.efi")
    if efi_loader is None or not efi_loader.is_file():
        raise RuntimeError("Az ISO nem tartalmazza az EFI/BOOT/BOOTX64.EFI x64 UEFI indítófájlt.")
    boot_wim = find_case_insensitive(iso_root, "sources/boot.wim")
    if boot_wim is None or not boot_wim.is_file():
        raise RuntimeError("Nem található a sources/boot.wim Windows PE indítókép.")
    install_image: Path | None = None
    for name in ("sources/install.wim", "sources/install.esd", "sources/install.swm"):
        candidate = find_case_insensitive(iso_root, name)
        if candidate is not None and candidate.is_file():
            install_image = candidate
            break
    if install_image is None:
        raise RuntimeError("Nem található install.wim, install.esd vagy install.swm a sources könyvtárban.")
    total_bytes = 0
    for current, dirs, files in os.walk(iso_root):
        current_path = Path(current)
        for name in list(dirs):
            if (current_path / name).is_symlink():
                raise RuntimeError("Az ISO szimbolikus könyvtárlinket tartalmaz; ez az alpha verzió nem másolja át biztonságosan.")
        for name in files:
            file_path = current_path / name
            if file_path.is_symlink():
                raise RuntimeError("Az ISO szimbolikus fájllinket tartalmaz; ez az alpha verzió nem másolja át biztonságosan.")
            if not file_path.is_file():
                raise RuntimeError(f"Nem szabályos fájl található az ISO-ban: {file_path.relative_to(iso_root)}")
            total_bytes += file_path.stat().st_size
    return install_image, boot_wim, total_bytes


def windows_copy_progress_span(verify: bool) -> int:
    """Reserve the second pass only when full file verification is enabled."""
    return 43 if verify else 54


def copy_tree_progress(
    source_root: Path,
    destination_root: Path,
    total_bytes: int,
    *,
    base_percent: int = 42,
    span: int = 43,
    hash_files: bool = True,
) -> list[tuple[str, int, str]]:
    """Copy ISO files, using in-kernel copy_file_range when hashing is disabled.

    copy_file_range is best-effort: cross-filesystem or unsupported NTFS3/ISO9660
    combinations transparently fall back to the buffered streaming path.
    Progress messages are throttled to at most one per percentage point.
    """
    copied_total = 0
    manifest: list[tuple[str, int, str]] = []
    last_percent = -1
    fast_copy_enabled = not hash_files and hasattr(os, "copy_file_range")
    unsupported_copy_range = {
        errno.EXDEV,
        errno.EINVAL,
        errno.ENOSYS,
        errno.EOPNOTSUPP,
        getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
    }

    def report_progress() -> None:
        nonlocal last_percent
        percent = base_percent + int(
            (copied_total / max(total_bytes, 1)) * span
        )
        percent = min(base_percent + span, percent)
        if percent > last_percent:
            last_percent = percent
            emit(
                f"Windows fájlok másolása… {copied_total:,} / {total_bytes:,} bájt",
                percent,
            )

    for current, dirs, files in os.walk(source_root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source_root)
        target_dir = destination_root / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in files:
            src = current_path / filename
            if src.is_symlink() or not src.is_file():
                raise RuntimeError(
                    f"Nem támogatott fájltípus az ISO-ban: {src.relative_to(source_root)}"
                )
            relative = src.relative_to(source_root).as_posix()
            dst = destination_root / src.relative_to(source_root)
            dst.parent.mkdir(parents=True, exist_ok=True)
            expected_size = src.stat().st_size
            digest = hashlib.sha256() if hash_files else None
            file_copied = 0

            # Unbuffered descriptors allow copy_file_range and the fallback
            # reader/writer to share file positions without Python buffer drift.
            with src.open("rb", buffering=0) as read_file, dst.open(
                "wb", buffering=0
            ) as write_file:
                if fast_copy_enabled:
                    while file_copied < expected_size:
                        try:
                            amount = os.copy_file_range(
                                read_file.fileno(),
                                write_file.fileno(),
                                min(CHUNK, expected_size - file_copied),
                            )
                        except OSError as exc:
                            if exc.errno in unsupported_copy_range:
                                fast_copy_enabled = False
                                emit(
                                    "A kernel copy_file_range útvonal nem támogatott ezen a fájlrendszer-kombináción; "
                                    "biztonságos streamelt másolásra váltok.",
                                    log=str(exc),
                                )
                                break
                            raise
                        if amount == 0:
                            # Treat an early EOF as a reason to use the normal
                            # reader path, which will report a short source.
                            break
                        file_copied += amount
                        copied_total += amount
                        report_progress()

                while file_copied < expected_size:
                    data = read_file.read(min(CHUNK, expected_size - file_copied))
                    if not data:
                        raise RuntimeError(
                            f"A forrásfájl másolás közben váratlanul véget ért: {relative}"
                        )
                    if digest is not None:
                        digest.update(data)
                    view = memoryview(data)
                    while view:
                        written = write_file.write(view)
                        if written is None or written <= 0:
                            raise RuntimeError(
                                f"Nem sikerült teljesen kiírni ezt a fájlt: {relative}"
                            )
                        view = view[written:]
                    file_copied += len(data)
                    copied_total += len(data)
                    report_progress()

                # Closing the unbuffered destination completes the per-file
                # userspace I/O. A single syncfs of the USB filesystem follows.
                if file_copied != expected_size:
                    raise RuntimeError(f"Másolási mérethiba: {relative}")
            if src.stat().st_size != expected_size:
                raise RuntimeError(f"A forrásfájl mérete megváltozott másolás közben: {relative}")
            if digest is not None:
                manifest.append((relative, expected_size, digest.hexdigest()))

    if copied_total != total_bytes:
        raise RuntimeError(
            f"A másolt adatmennyiség eltér az ISO előzetes méretétől "
            f"({copied_total} / {total_bytes} bájt)."
        )
    if last_percent < base_percent + span:
        emit("Windows telepítőfájlok átmásolva.", base_percent + span)
    else:
        emit("Windows telepítőfájlok átmásolva.", base_percent + span)
    return manifest

def verify_copied_files(destination_root: Path, manifest: list[tuple[str, int, str]]) -> None:
    total = sum(size for _, size, _ in manifest)
    checked = 0
    for relative, expected_size, expected_hash in manifest:
        target = destination_root / Path(relative)
        if not target.is_file():
            raise RuntimeError(f"Az USB-ről hiányzik egy átmásolt fájl: {relative}")
        if target.stat().st_size != expected_size:
            raise RuntimeError(f"Visszaellenőrzési mérethiba: {relative}")
        digest = hashlib.sha256()
        with target.open("rb") as source:
            # The caller syncs the filesystem before verification. Ask Linux
            # to evict clean cached pages so this pass re-reads the USB media.
            if hasattr(os, "posix_fadvise") and hasattr(os, "POSIX_FADV_DONTNEED"):
                try:
                    os.posix_fadvise(source.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
                except OSError:
                    pass
            while True:
                data = source.read(CHUNK)
                if not data:
                    break
                digest.update(data)
                checked += len(data)
                emit(f"SHA-256 visszaellenőrzés… {checked:,} / {total:,} bájt",
                     86 + int((checked / max(total, 1)) * 12))
        if digest.hexdigest() != expected_hash:
            raise RuntimeError(f"SHA-256 eltérés az USB-n: {relative}")
    emit("Minden telepítőfájl SHA-256 ellenőrzése sikeres.", 98)


def write_uefi_ntfs_image(image: Path, partition: str) -> None:
    """Write and verify the prepared FAT UEFI:NTFS partition image."""
    expected = image.stat().st_size
    actual = int(command(["blockdev", "--getsize64", partition]).stdout.strip())
    if actual != expected:
        raise RuntimeError(
            f"Az UEFI:NTFS partíció mérete ({actual}) nem egyezik a segédkép méretével ({expected})."
        )
    emit("UEFI:NTFS indítópartíció telepítése…", 38)
    fd = os.open(partition, os.O_WRONLY)
    try:
        with image.open("rb", buffering=0) as source:
            remaining = expected
            while remaining:
                data = source.read(min(CHUNK, remaining))
                if not data:
                    raise RuntimeError("Az UEFI:NTFS segédkép váratlanul véget ért.")
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise RuntimeError("Nem sikerült az UEFI:NTFS segédképet a partícióra írni.")
                    view = view[written:]
                remaining -= len(data)
        os.fsync(fd)
    finally:
        os.close(fd)

    digest = hashlib.sha1()
    digest.update(f"blob {expected}\0".encode("ascii"))
    sha256 = hashlib.sha256()
    fd = os.open(partition, os.O_RDONLY)
    try:
        remaining = expected
        while remaining:
            data = os.read(fd, min(CHUNK, remaining))
            if not data:
                raise RuntimeError("Az UEFI:NTFS partíció visszaolvasása váratlanul véget ért.")
            digest.update(data)
            sha256.update(data)
            remaining -= len(data)
    finally:
        os.close(fd)
    if digest.hexdigest() != UEFI_NTFS_GIT_BLOB_SHA1:
        raise RuntimeError("Az UEFI:NTFS indítópartíció Git-blob hash-e eltér a hivatalos képtől.")
    if sha256.hexdigest() != UEFI_NTFS_SHA256:
        raise RuntimeError("Az UEFI:NTFS indítópartíció SHA-256 hash-e eltér a hivatalos képtől.")
    emit("UEFI:NTFS partíció SHA-1 és SHA-256 visszaolvasása sikeres.", 40)




def validate_ntfs_boot_sector(partition: str, expected_start_sector: int) -> None:
    """Verify critical NTFS BPB fields used by Windows boot code."""
    with open(partition, "rb", buffering=0) as source:
        boot = source.read(512)
    if len(boot) != 512:
        raise RuntimeError("Az NTFS rendszerindító szektor nem olvasható teljes hosszban.")
    if boot[3:11] != b"NTFS    ":
        raise RuntimeError("Az elkészült kötet boot szektorában nem található NTFS aláírás.")
    bytes_per_sector = struct.unpack_from("<H", boot, 11)[0]
    sectors_per_cluster = boot[13]
    sectors_per_track = struct.unpack_from("<H", boot, 24)[0]
    heads = struct.unpack_from("<H", boot, 26)[0]
    hidden_sectors = struct.unpack_from("<I", boot, 28)[0]
    if bytes_per_sector != 512:
        raise RuntimeError(f"Az NTFS kötet szektormérete hibás: {bytes_per_sector}, elvárt 512.")
    if sectors_per_cluster == 0 or sectors_per_cluster & (sectors_per_cluster - 1):
        raise RuntimeError(f"Az NTFS klaszterméret mező hibás: {sectors_per_cluster}.")
    if sectors_per_track != 63 or heads != 255:
        raise RuntimeError(
            f"Az NTFS BPB geometria hibás: heads={heads}, sectors/track={sectors_per_track}; "
            "elvárt 255/63."
        )
    if hidden_sectors != expected_start_sector:
        raise RuntimeError(
            f"Az NTFS HiddenSectors mező hibás: {hidden_sectors}; "
            f"elvárt {expected_start_sector}."
        )
    if boot[510:512] != b"\x55\xaa":
        raise RuntimeError("Az NTFS boot szektor 0x55AA aláírása hiányzik.")


def sync_filesystem(path: Path) -> None:
    """Flush only the filesystem containing path, not every filesystem on host."""
    command(["sync", "--file-system", str(path)], timeout=300)


def mount_ntfs_volume(partition: str, mountpoint: Path) -> str:
    """Prefer the in-kernel NTFS3 driver; fall back to ntfs-3g for compatibility."""
    common = ["-o", "rw,nosuid,nodev", partition, str(mountpoint)]
    try:
        command(["mount", "-t", "ntfs3", *common], timeout=120)
        emit("NTFS kötet csatolása a Linux kernel NTFS3 driverével…", 41)
        return "ntfs3"
    except RuntimeError as kernel_error:
        if not shutil.which("ntfs-3g"):
            raise RuntimeError(
                "A kernel NTFS3 illesztőprogram nem tudta csatolni a pendrive-ot, "
                "és az ntfs-3g tartalék driver sem érhető el. "
                f"NTFS3 hiba: {kernel_error}"
            ) from kernel_error
        emit(
            "A kernel NTFS3 driver nem érhető el; kompatibilitási tartalék: ntfs-3g…",
            41,
            log=str(kernel_error),
        )
        command(["mount", "-t", "ntfs-3g", *common], timeout=120)
        return "ntfs-3g"


def write_windows_uefi(image: Path, device: str, verify: bool = True) -> None:
    global TARGET_MODIFIED
    require_programs((
        "lsblk", "blockdev", "findmnt", "umount", "wipefs", "udevadm", "sync",
        "mount", "partprobe", "sfdisk", "mkfs.ntfs",
    ))

    # Validate both the removable target and the upstream boot image before
    # making any changes to the user's USB drive.
    target_size = validate_target(device)
    verify_uefi_ntfs_image()
    sector_size = int(command(["blockdev", "--getss", device]).stdout.strip())
    if sector_size != 512:
        raise RuntimeError(
            f"Ez a verzió 512 bájtos logikai szektort vár; a célmeghajtó {sector_size} bájtos szektorokat jelez."
        )
    total_sectors = int(command(["blockdev", "--getsz", device]).stdout.strip())
    layout = calculate_gpt_layout(total_sectors)
    if layout["first_bytes"] + layout["second_bytes"] > target_size:
        raise RuntimeError("A partíciók számított mérete nagyobb, mint a célmeghajtó kapacitása.")

    temp_root = Path(tempfile.mkdtemp(prefix="bootmediakit-", dir="/run"))
    iso_mount = temp_root / "iso"
    usb_mount = temp_root / "usb"
    mounted_iso = False
    mounted_usb = False
    try:
        # Inspect the entire ISO and determine the exact data size while the
        # target remains untouched.
        emit("Windows ISO és UEFI:NTFS segédkép ellenőrzése…", 1)
        mount_iso(image, iso_mount)
        mounted_iso = True
        install_image, boot_wim, total_copy_bytes = scan_windows_iso(iso_mount)
        reserve_bytes = 128 * 1024 * 1024
        if total_copy_bytes + reserve_bytes > layout["first_bytes"]:
            raise RuntimeError(
                "Kevés a pendrive kapacitása a Windows ISO fájljaihoz. "
                f"Szükséges legalább {total_copy_bytes + reserve_bytes:,} bájt, "
                f"az NTFS partíció mérete {layout['first_bytes']:,} bájt. "
                "A pendrive tartalmához még nem nyúltam."
            )
        emit(
            "ISO előellenőrzés kész; a pendrive-ot még nem módosítottam.",
            8,
            log=(
                f"Windows PE: {boot_wim.relative_to(iso_mount)}; "
                f"telepítőkép: {install_image.relative_to(iso_mount)}; "
                f"másolandó fájlméret: {total_copy_bytes:,} bájt."
            ),
        )

        # From this point on, disk contents will be modified. The device was
        # validated before preflight; validate it once more immediately before
        # unmounting/wiping to catch a device swap or stale selection.
        validate_target(device)
        emit("USB lemez leválasztása és GPT partíciók létrehozása…", 10)
        unmount_disk(device)
        TARGET_MODIFIED = True
        command(["wipefs", "--all", "--force", device])
        script = make_sfdisk_script(layout)
        command(["sfdisk", "--wipe", "never", device], input_text=script)
        command(["blockdev", "--rereadpt", device], check=False)
        command(["partprobe", device], check=False)
        command(["udevadm", "settle"], check=False, timeout=20)

        ntfs_partition = partition_path(device, 1)
        uefi_partition = partition_path(device, 2)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if os.path.exists(ntfs_partition) and os.path.exists(uefi_partition):
                try:
                    if stat.S_ISBLK(os.stat(ntfs_partition).st_mode) and stat.S_ISBLK(os.stat(uefi_partition).st_mode):
                        break
                except OSError:
                    pass
            time.sleep(0.25)
        else:
            raise RuntimeError("A GPT elkészült, de a kernel nem hozta létre időben a két partíció-eszközt.")

        emit("NTFS fájlrendszer létrehozása…", 25)
        command(["mkfs.ntfs", "--fast", "--force", "--label", "BOOTMEDIA", "--partition-start", str(layout["first_start"]), "--sector-size", "512", "--heads", "255", "--sectors-per-track", "63", "--cluster-size", "4096", ntfs_partition], timeout=300)
        validate_ntfs_boot_sector(ntfs_partition, layout["first_start"])
        write_uefi_ntfs_image(UEFI_NTFS_IMAGE, uefi_partition)

        emit("Windows ISO fájlok másolása az NTFS partícióra…", 42)
        usb_mount.mkdir(parents=True, exist_ok=True)
        mount_ntfs_volume(ntfs_partition, usb_mount)
        mounted_usb = True
        copy_span = windows_copy_progress_span(verify)
        copy_end_percent = 42 + copy_span
        manifest = copy_tree_progress(
            iso_mount,
            usb_mount,
            total_copy_bytes,
            base_percent=42,
            span=copy_span,
            hash_files=verify,
        )

        # Commit all writes in one batch. Per-file fsync is particularly slow
        # on low-end USB 2.0 flash drives; unmount also performs final flushing.
        emit("A másolt adatok kiírása a pendrive-ra…", copy_end_percent)
        sync_filesystem(usb_mount)

        # Recheck the boot chain files on the destination before unmounting.
        for relative in ("efi/boot/bootx64.efi", "sources/boot.wim"):
            copied = find_case_insensitive(usb_mount, relative)
            if copied is None or not copied.is_file():
                raise RuntimeError(f"A Windows UEFI indításhoz szükséges fájl hiányzik az USB-ről: {relative}")
        if verify:
            emit("USB-re másolt Windows fájlok SHA-256 visszaellenőrzése…", 86)
            verify_copied_files(usb_mount, manifest)
        else:
            emit(
                "A teljes SHA-256 ellenőrzés kihagyva; az indítófájlok meglétét ellenőriztem.",
                copy_end_percent,
            )

        emit("Fájlrendszer kiürítése és leválasztása…", 99)
        sync_filesystem(usb_mount)
        command(["umount", "--", str(usb_mount)], timeout=120)
        mounted_usb = False
        command(["udevadm", "settle"], check=False, timeout=20)
        emit(
            "A Windows UEFI:NTFS telepítő USB elkészült.",
            100,
            log=(
                "GPT: 1. partíció Microsoft Basic Data / NTFS (Windows fájlok); "
                "2. partíció EFI System / FAT (UEFI:NTFS v2.8 boot image). "
                "A Windows ISO fájljai eredeti formájukban kerültek át."
            ),
        )
    finally:
        if mounted_usb:
            try:
                sync_filesystem(usb_mount)
            except Exception:
                pass
            command(["umount", "--", str(usb_mount)], check=False, timeout=120)
        if mounted_iso:
            command(["umount", "--", str(iso_mount)], check=False, timeout=120)
        if TARGET_MODIFIED:
            try:
                unmount_disk(device)
            except Exception:
                pass
        shutil.rmtree(temp_root, ignore_errors=True)
        command(["udevadm", "settle"], check=False, timeout=20)


def write_raw(image: Path, device: str, verify: bool) -> None:
    global TARGET_MODIFIED
    source_size = image.stat().st_size
    target_size = validate_target(device)
    if source_size <= 0:
        raise RuntimeError("A lemezkép üres.")
    if source_size > target_size:
        raise RuntimeError("A lemezkép nagyobb, mint a célmeghajtó.")
    require_programs(("lsblk", "blockdev", "findmnt", "umount", "wipefs", "udevadm", "sync"))

    emit("Célmeghajtó ellenőrzése…", 1,
         log=f"Forrás: {image} ({source_size:,} bájt); cél: {device} ({target_size:,} bájt)")
    unmount_disk(device)
    emit("Régi partíciós és fájlrendszer-aláírások eltávolítása…", 2)
    TARGET_MODIFIED = True
    command(["wipefs", "--all", "--force", device])
    command(["sync"])

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
                        mismatch = next(
                            (i for i, (a, b) in enumerate(zip(actual, expected)) if a != b),
                            min(len(actual), len(expected)),
                        )
                        raise RuntimeError(
                            f"Visszaolvasási hiba a(z) {compared + mismatch:,}. bájtnál. "
                            "A meghajtó vagy az USB-kapcsolat hibás lehet."
                        )
                    compared += len(expected)
                    percent = 61 + int((compared / source_size) * 38)
                    emit(f"Ellenőrzés… {compared:,} / {source_size:,} bájt", percent)
            finally:
                os.close(target_fd)
    command(["blockdev", "--rereadpt", device], check=False)
    command(["udevadm", "settle"], check=False, timeout=15)
    command(["sync"])
    emit("A lemezkép sikeresen kiírva és ellenőrizve." if verify else "A lemezkép sikeresen kiírva.", 100)


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
    verify = len(argv) >= 5 and argv[4] == "1"
    try:
        if mode == "raw":
            write_raw(image, device, verify)
        elif mode == "windows":
            if image.suffix.lower() != ".iso":
                raise RuntimeError("Windows telepítő készítéséhez ISO fájl szükséges.")
            write_windows_uefi(image, device, verify)
        else:
            raise RuntimeError("Ismeretlen írási mód.")
        return 0
    except Exception as exc:
        if TARGET_MODIFIED:
            state_log = "A célmeghajtó állapota részleges lehet; ellenőrizd újracsatlakoztatás után."
        else:
            state_log = "A célmeghajtó tartalmát nem módosítottam; az előellenőrzés állította le a műveletet."
        emit("A művelet megszakadt.", error=str(exc), log=state_log)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
