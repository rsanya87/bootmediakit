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
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterable

CHUNK = 8 * 1024 * 1024
UEFI_NTFS_IMAGE = Path("/usr/share/bootmediakit/uefi/uefi-ntfs.img")
UEFI_NTFS_IMAGE_SIZE = 1_048_576
UEFI_NTFS_GIT_BLOB_SHA1 = "ac50eed9730af847c43c145a5c17678f54128b33"
UEFI_NTFS_SHA256 = "72683fa1250eeea772d3399277b434d4e55ba8dd0dc926e52d817e701fc2eb9e"
UPSTREAM_FAT_VOLUME_LABEL = "RUFUS_BOOT"
BOOTMEDIA_FAT_VOLUME_LABEL = "BMK_EFI"
GPT_BASIC_DATA_GUID = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
# GPT GUID-specific attribute bit 63: do not automatically assign a drive letter.
# Rufus uses Microsoft Basic Data (not EFI System) for its UEFI:NTFS helper
# partition because Windows Setup can fail when it sees a second ESP.
GPT_NO_DRIVE_LETTER_ATTR = "GUID:63"
GPT_ALIGNMENT_SECTORS = 2048
GPT_RESERVED_SECTORS = 34
TARGET_MODIFIED = False
OUTPUT_BROKEN = False
CANCEL_EVENT = threading.Event()


class OperationCancelled(Exception):
    """Raised at safe cancellation points between disk I/O units."""


def check_cancelled() -> None:
    if OUTPUT_BROKEN:
        raise OperationCancelled("A grafikus felülettel megszakadt a kapcsolat.")
    if CANCEL_EVENT.is_set():
        raise OperationCancelled("A felhasználó megszakította a műveletet.")


def start_control_reader() -> None:
    """Read a line-oriented cancel command from pkexec stdin."""
    def read_commands() -> None:
        try:
            for line in sys.stdin:
                if line.strip().lower() == "cancel":
                    CANCEL_EVENT.set()
                    return
        except (OSError, ValueError):
            return

    threading.Thread(target=read_commands, name="bmk-control-stdin", daemon=True).start()


def emit(
    message: str,
    percent: int | None = None,
    *,
    log: str | None = None,
    error: str | None = None,
    worker_started: bool | None = None,
    cancelled: bool = False,
) -> bool:
    """Send one structured event; return False when the GUI pipe is closed."""
    global OUTPUT_BROKEN
    event: dict[str, object] = {"message": message, "target_modified": TARGET_MODIFIED}
    if percent is not None:
        event["percent"] = max(0, min(100, int(percent)))
    if log:
        event["log"] = log
    if error:
        event["error"] = error
    if worker_started is not None:
        event["worker_started"] = worker_started
    if cancelled:
        event["cancelled"] = True
    try:
        print(json.dumps(event, ensure_ascii=False), flush=True)
    except (BrokenPipeError, OSError):
        OUTPUT_BROKEN = True
        return False
    return True


def _write_stderr_safely(message: str) -> None:
    """Best-effort fallback logging when the GUI output pipe is unavailable."""
    try:
        print(message, file=sys.stderr, flush=True)
    except OSError:
        pass


def command(
    args: list[str],
    *,
    check: bool = True,
    timeout: int | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        if input_text is None:
            result = subprocess.run(
                args,
                stdin=subprocess.DEVNULL,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        else:
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


LSBLK_COLUMNS = (
    "PATH,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,RM,RO,MAJ:MIN,"
    "PKNAME,FSTYPE,LABEL,PARTTYPE,PARTLABEL,MOUNTPOINTS"
)


def _as_bool(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def _flatten_block_tree(nodes: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for node in nodes:
        result.append(node)
        children = node.get("children") or []
        if isinstance(children, list):
            result.extend(_flatten_block_tree(children))
    return result


def lsblk_tree(path: str, *, inverse: bool = False) -> list[dict[str, object]]:
    args = ["lsblk", "--json", "--bytes", "--paths", "--tree", "--output", LSBLK_COLUMNS]
    if inverse:
        args.append("--inverse")
    args.append(path)
    result = command(args)
    try:
        nodes = json.loads(result.stdout).get("blockdevices", [])
    except (json.JSONDecodeError, AttributeError) as exc:
        raise RuntimeError("Az lsblk nem adott érvényes JSON meghajtólistát.") from exc
    return _flatten_block_tree(nodes)


def _read_diskseq(maj_min: str) -> str:
    if not maj_min:
        return ""
    path = Path("/sys/dev/block") / maj_min / "diskseq"
    try:
        return path.read_text(encoding="ascii").strip()
    except OSError:
        return ""


def _device_by_id(path: str) -> str:
    wanted = canonical(path)
    directory = Path("/dev/disk/by-id")
    try:
        matches = sorted(
            str(entry)
            for entry in directory.iterdir()
            if entry.is_symlink() and canonical(str(entry)) == wanted
        )
    except OSError:
        return ""
    return next((item for item in matches if "-part" not in Path(item).name), matches[0] if matches else "")


def device_identity(device: str) -> dict[str, object]:
    nodes = lsblk_tree(device)
    node = next(
        (item for item in nodes if item.get("type") == "disk" and canonical(str(item.get("path", ""))) == canonical(device)),
        nodes[0] if nodes else None,
    )
    if not node or node.get("type") != "disk":
        raise RuntimeError("Partíció helyett a teljes fizikai lemezt válaszd ki.")
    path = str(node.get("path") or device)
    maj_min = str(node.get("maj:min") or "")
    identity = {
        "path": path,
        "size": int(node.get("size") or 0),
        "model": str(node.get("model") or ""),
        "serial": str(node.get("serial") or "").strip(),
        "wwn": str(node.get("wwn") or "").strip(),
        "tran": str(node.get("tran") or "").strip().lower(),
        "rm": _as_bool(node.get("rm")),
        "maj_min": maj_min,
        "diskseq": _read_diskseq(maj_min),
        "by_id": _device_by_id(path),
    }
    if not any(identity[key] for key in ("serial", "wwn", "diskseq", "by_id")):
        raise RuntimeError(
            "A meghajtóhoz nem található stabil fizikai azonosító (sorozatszám, WWN, diskseq vagy by-id). "
            "Biztonsági okból ezt az eszközt nem írhatom."
        )
    return identity


def _normalize_identity_value(value: object) -> str:
    """Collapse whitespace without changing a model's meaningful characters."""
    return " ".join(str(value or "").split())


def compare_device_identity(expected: dict[str, object], current: dict[str, object]) -> None:
    """Reject path reuse, device swaps, and changes to the selected disk."""
    for key in ("size", "maj_min"):
        if expected.get(key) in (None, "") or str(expected.get(key)) != str(current.get(key)):
            raise RuntimeError(f"A célmeghajtó azonosítója megváltozott ({key}); válaszd ki újra a meghajtót.")
    for key in ("model", "serial", "wwn", "tran", "diskseq", "by_id"):
        normalize = _normalize_identity_value if key == "model" else lambda value: str(value or "").strip()
        old_value = normalize(expected.get(key))
        if old_value and old_value != normalize(current.get(key)):
            raise RuntimeError(f"A célmeghajtó fizikai azonossága megváltozott ({key}); az írást leállítottam.")
    if not any(str(expected.get(key) or "").strip() for key in ("serial", "wwn", "diskseq", "by_id")):
        raise RuntimeError("A kiválasztáskor nem volt rögzítve stabil meghajtóazonosító.")


def _block_ancestor_paths(source: str) -> set[str]:
    if not source.startswith("/dev/") or not os.path.exists(source):
        return set()
    result: set[str] = set()
    for item in lsblk_tree(source, inverse=True):
        path = str(item.get("path") or "")
        if path.startswith("/dev/"):
            result.add(canonical(path))
    result.add(canonical(source))
    return result


def _block_ancestor_majmins(source: str) -> set[str]:
    if not source.startswith("/dev/") or not os.path.exists(source):
        return set()
    return {
        str(item.get("maj:min"))
        for item in lsblk_tree(source, inverse=True)
        if item.get("maj:min")
    }


def protected_physical_devices() -> set[str]:
    """Return physical devices backing system mounts and active swap."""
    protected: set[str] = set()
    for target in ("/", "/boot", "/boot/efi", "/efi", "/home", "/usr", "/var", "/opt", "/srv", "/root"):
        result = command(["findmnt", "-nro", "SOURCE", "--target", target], check=False)
        source = result.stdout.strip().split("[", 1)[0]
        protected.update(_block_ancestor_paths(source))
    swap = command(["swapon", "--noheadings", "--raw", "--output", "NAME"], check=False)
    for line in swap.stdout.splitlines():
        source = line.strip()
        if source.startswith("/dev/"):
            protected.update(_block_ancestor_paths(source))
        elif source and Path(source).exists():
            major_minor = command(
                ["findmnt", "-nro", "MAJ:MIN", "--target", source],
                check=False,
            ).stdout.strip()
            if major_minor and Path("/dev/block", major_minor).exists():
                protected.update(
                    _block_ancestor_paths(canonical(str(Path("/dev/block") / major_minor)))
                )
    return protected


def inspect_target_layout(device: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    nodes = lsblk_tree(device)
    disk = next((item for item in nodes if item.get("type") == "disk"), None)
    if disk is None:
        raise RuntimeError("Partíció helyett a teljes fizikai lemezt válaszd ki.")
    children = _flatten_block_tree([disk])
    unsafe_types = {"crypt", "lvm", "raid", "raid0", "raid1", "raid5", "raid6", "raid10", "mpath"}
    unsafe_fs = {"crypto_luks", "lvm2_member", "swap", "linux_raid_member", "isw_raid_member", "ddf_raid_member"}
    for item in children:
        if item is disk:
            continue
        item_type = str(item.get("type") or "").lower()
        filesystem = str(item.get("fstype") or "").lower()
        if item_type in unsafe_types or filesystem in unsafe_fs:
            path = str(item.get("path") or "ismeretlen partíció")
            label = str(item.get("label") or "")
            raise RuntimeError(
                f"A céllemezen védett vagy összetett kötet található ({path}, "
                f"{filesystem or item_type}, {label}). Előbb biztonságosan válaszd le a "
                "LUKS/LVM/RAID/swap réteget; a BootMediaKit nem bontja le automatikusan."
            )
    return disk, children


def validate_target(
    device: str,
    expected_identity: dict[str, object] | None = None,
) -> int:
    """Validate whole USB disk, identity snapshot, system backing and layout."""
    if not device.startswith("/dev/"):
        raise RuntimeError("A cél nem érvényes /dev eszköz.")
    try:
        info = os.stat(device)
    except OSError as exc:
        raise RuntimeError(f"A célmeghajtó nem érhető el: {exc}") from exc
    if not stat.S_ISBLK(info.st_mode):
        raise RuntimeError("A cél csak valódi blokk eszköz lehet; fájlba írás nem engedélyezett.")

    identity = device_identity(device)
    if expected_identity is None:
        raise RuntimeError("Hiányzik a kiválasztáskor rögzített meghajtóazonosító; válaszd ki újra a célt.")
    compare_device_identity(expected_identity, identity)
    disk, _ = inspect_target_layout(device)
    if str(disk.get("type")) != "disk":
        raise RuntimeError("Partíció helyett a teljes fizikai lemezt válaszd ki.")
    if _as_bool(disk.get("ro")):
        raise RuntimeError("A célmeghajtó írásvédett.")
    if str(disk.get("tran") or "").lower() != "usb" and not _as_bool(disk.get("rm")):
        raise RuntimeError("Biztonsági okból csak USB vagy eltávolítható lemezre lehet írni.")
    if canonical(device) in protected_physical_devices():
        raise RuntimeError(
            "A kiválasztott lemez a rendszer vagy az aktív swap fizikai meghajtója. "
            "A műveletet biztonsági okból leállítottam."
        )
    return int(identity["size"])


BTRFS_SYSFS_ROOT = Path("/sys/fs/btrfs")
_BTRFS_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


def _btrfs_member_devices(source: str, source_stat: os.stat_result) -> list[str]:
    """Return the /dev path of every member device of a mounted btrfs.

    The filesystem is located under /sys/fs/btrfs/<UUID>/devices/ by the
    MAJ:MIN of the member reported in mountinfo. Fail closed when the member
    list cannot be read completely.
    """
    unreadable = RuntimeError(
        f"A Btrfs fájlrendszer tagjainak listája nem olvasható ki ({source}), ezért nem igazolható, "
        "hogy a forrásfájl nem a célmeghajtón van; az írást biztonsági okból leállítottam. "
        "Másold az ISO-t egy másik helyi lemezre (például a saját mappádba), majd válaszd ki újra."
    )
    try:
        wanted = f"{os.major(source_stat.st_rdev)}:{os.minor(source_stat.st_rdev)}"
        candidates = sorted(
            entry for entry in BTRFS_SYSFS_ROOT.iterdir()
            if _BTRFS_UUID_RE.match(entry.name)
        )
    except (OSError, AttributeError, TypeError) as exc:
        raise unreadable from exc

    for candidate in candidates:
        members: dict[str, str] = {}
        try:
            for entry in sorted((candidate / "devices").iterdir()):
                members[entry.name] = (entry / "dev").read_text(encoding="ascii").strip()
        except OSError:
            # A filesystem unmounted meanwhile; if it was ours, no match is
            # found below and the operation is rejected.
            continue
        if wanted not in members.values():
            continue
        if not all(re.fullmatch(r"\d+:\d+", value) for value in members.values()):
            raise unreadable
        paths: list[str] = []
        for name, maj_min in sorted(members.items()):
            path = next(
                (
                    item for item in (f"/dev/{name}", f"/dev/block/{maj_min}")
                    if os.path.exists(item)
                ),
                "",
            )
            if not path:
                raise unreadable
            paths.append(path)
        return paths
    raise unreadable


def source_backing_majmins(image: Path) -> set[str]:
    """Resolve every backing block device for the mount containing an image.

    Mountinfo is used instead of findmnt --target because --target can return
    only one entry and therefore hide an autofs/CIFS over-mount stack. All
    entries at the deepest matching mountpoint are examined so hidden
    block-backed layers cannot be ignored.
    """
    entries = _source_mounts_for_path(image)
    non_block_backed_types = {
        "tmpfs", "ramfs", "proc", "sysfs", "cgroup", "cgroup2",
        "devtmpfs", "devpts", "mqueue", "securityfs", "tracefs",
        "debugfs", "pstore", "configfs", "rpc_pipefs",
        "nfs", "nfs4", "cifs", "smb3", "ceph", "9p",
        # Network/virtual filesystems that can never live on the target USB
        # disk. "fuseblk" (ntfs-3g) is deliberately absent: it has a /dev
        # source and must go through the block-device collision check.
        "virtiofs", "vboxsf",
        "fuse.sshfs", "fuse.rclone", "fuse.gvfsd-fuse", "fuse.portal",
    }
    backing: set[str] = set()
    has_autofs = False
    has_real_filesystem = False

    for _major_minor, _mountpoint, filesystem_type, source_value in entries:
        source = source_value.split("[", 1)[0].strip()
        if filesystem_type == "autofs":
            has_autofs = True
            continue

        has_real_filesystem = True
        if source.startswith(("UUID=", "LABEL=", "PARTUUID=", "PARTLABEL=")):
            resolved = command(["findfs", source], check=False, timeout=10)
            source = resolved.stdout.strip().splitlines()[0] if resolved.stdout.strip() else ""
            if resolved.returncode != 0 or not source:
                raise RuntimeError(
                    "A forrásfájlrendszer blokkeszköz-azonosítója nem oldható fel; "
                    "biztonsági okból az írást leállítottam."
                )

        if source.startswith("/dev/"):
            try:
                source_stat = os.stat(source)
            except OSError as exc:
                raise RuntimeError(
                    f"A forrásfájlrendszer blokkeszköze nem érhető el ({source}); "
                    "az írást biztonsági okból leállítottam."
                ) from exc
            if not stat.S_ISBLK(source_stat.st_mode):
                raise RuntimeError(
                    f"A mountinfo által megadott forrás nem blokkeszköz ({source}); "
                    "az írást biztonsági okból leállítottam."
                )
            # A multi-device btrfs shows only one member in mountinfo. Every
            # member must take part in the source/target collision check.
            if filesystem_type == "btrfs":
                members = _btrfs_member_devices(source, source_stat)
            else:
                members = [source]
            for member in members:
                resolved_backing = _block_ancestor_majmins(member)
                if not resolved_backing:
                    raise RuntimeError(
                        f"A forrás blokkeszközének fizikai meghajtója nem oldható fel ({member}); "
                        "az írást biztonsági okból leállítottam."
                    )
                backing.update(resolved_backing)
        elif filesystem_type not in non_block_backed_types:
            raise RuntimeError(
                "A forrásfájl olyan fájlrendszeren van, amelynek fizikai háttértára nem igazolható "
                f"(típus: {filesystem_type or 'ismeretlen'}, forrás: {source_value or 'ismeretlen'}), "
                "ezért biztonsági okból az írást leállítottam. "
                "Másold az ISO-t helyi, blokkeszközön lévő lemezre (például a saját mappádba), "
                "majd válaszd ki újra."
            )

    # An autofs record is only an automounter layer, not the mounted data
    # filesystem. Require the corresponding active filesystem to be visible.
    if has_autofs and not has_real_filesystem:
        raise RuntimeError(
            "Az autofs csatolás mögötti tényleges fájlrendszer nem azonosítható; "
            "biztonsági okból az írást leállítottam."
        )
    if not has_real_filesystem:
        raise RuntimeError(
            "Nem sikerült azonosítani a forrásfájl tényleges fájlrendszerét; "
            "biztonsági okból az írást leállítottam."
        )
    return backing

def ensure_source_not_on_target(image: Path, device: str) -> None:
    """Reject an image whose containing filesystem is on the target disk."""
    resolved = image.resolve(strict=True)
    if not resolved.is_file():
        raise RuntimeError("A forrásnak normál fájlnak kell lennie.")
    source_majmins = source_backing_majmins(resolved)
    target_identity = device_identity(device)
    target_majmins = _block_ancestor_majmins(device)
    # If the target is a whole disk, its MAJ:MIN is in the source partition's
    # inverse tree. If the target itself is a partition alias, compare all
    # ancestors on both sides.
    if target_identity.get("maj_min") in source_majmins or source_majmins.intersection(target_majmins):
        raise RuntimeError(
            "A forrásfájl a célmeghajtó egyik kötetén található. "
            "A céllemezt nem módosítottam; másold a lemezképet egy másik meghajtóra."
        )


def _decode_mountinfo_field(value: str) -> str:
    """Decode the octal escapes used by /proc/self/mountinfo."""
    return re.sub(
        r"\\([0-7]{3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )


def _decode_findmnt_target(value: str) -> str:
    """Decode util-linux findmnt's hexadecimal path escapes."""
    return re.sub(
        r"\\x([0-9a-fA-F]{2})",
        lambda match: chr(int(match.group(1), 16)),
        value,
    )


def _read_mountinfo_records() -> list[tuple[str, str, str, str]]:
    """Read MAJ:MIN, mountpoint, filesystem type and source from mountinfo."""
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            "Nem ellenőrizhető a csatolási állapot (/proc/self/mountinfo); "
            "az írást biztonsági okból leállítottam."
        ) from exc

    entries: list[tuple[str, str, str, str]] = []
    for line in lines:
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError as exc:
            raise RuntimeError(
                "Hibás /proc/self/mountinfo sor; a fájlrendszer forrása nem ellenőrizhető."
            ) from exc
        if len(fields) < 6 or separator < 6 or len(fields) <= separator + 2:
            raise RuntimeError(
                "Hibás /proc/self/mountinfo sor; a fájlrendszer forrása nem ellenőrizhető."
            )
        entries.append(
            (
                fields[2],
                _decode_mountinfo_field(fields[4]),
                fields[separator + 1].lower(),
                _decode_mountinfo_field(fields[separator + 2]),
            )
        )
    return entries


def _source_mounts_for_path(image: Path) -> list[tuple[str, str, str, str]]:
    """Return all mount layers at the deepest mountpoint containing image."""
    image_path = str(image.resolve(strict=True))
    matches = [
        entry
        for entry in _read_mountinfo_records()
        if entry[1] == "/"
        or image_path == entry[1]
        or image_path.startswith(entry[1].rstrip("/") + os.sep)
    ]
    if not matches:
        raise RuntimeError(
            "Nem található csatolási bejegyzés a forrásfájlhoz; "
            "biztonsági okból az írást leállítottam."
        )
    deepest_length = max(len(entry[1]) for entry in matches)
    return [entry for entry in matches if len(entry[1]) == deepest_length]


def _read_mountinfo() -> list[tuple[str, str]]:
    return [
        (major_minor, mountpoint)
        for major_minor, mountpoint, _filesystem_type, _source in _read_mountinfo_records()
    ]


def _disk_mount_targets(device: str) -> set[str]:
    """Return all mountpoints backed by the disk or any of its child nodes."""
    _disk, nodes = inspect_target_layout(device)
    paths: set[str] = set()
    majmins: set[str] = set()
    for item in nodes:
        path = str(item.get("path") or "")
        if path:
            paths.add(path)
        maj_min = str(item.get("maj:min") or "")
        if maj_min:
            majmins.add(maj_min)
    if not majmins:
        raise RuntimeError(
            "A célmeghajtó MAJ:MIN azonosítója hiányzik; a csatolási állapot nem ellenőrizhető."
        )

    targets = {
        target
        for major_minor, target in _read_mountinfo()
        if major_minor in majmins
    }
    # findmnt source matching also catches aliases and source strings that do
    # not map directly to a mountinfo MAJ:MIN entry.
    for path in paths:
        result = command(
            ["findmnt", "-rn", "-S", path, "-o", "TARGET"],
            check=False,
            timeout=10,
        )
        targets.update(
            _decode_findmnt_target(line.strip())
            for line in result.stdout.splitlines()
            if line.strip()
        )
    return targets


def assert_disk_unmounted(device: str) -> None:
    remaining = _disk_mount_targets(device)
    if remaining:
        mounts = ", ".join(sorted(remaining))
        raise RuntimeError(
            f"A célmeghajtó vagy valamelyik kötete még csatolva van ({mounts}); "
            "a törlést biztonsági okból leállítottam."
        )


def unmount_disk(device: str) -> None:
    mountpoints = _disk_mount_targets(device)
    for mountpoint in sorted(mountpoints, key=lambda value: (value.count(os.sep), len(value)), reverse=True):
        emit(f"Meghajtó leválasztása: {mountpoint}", 1)
        command(["umount", "--", mountpoint], timeout=120)
    command(["udevadm", "settle"], check=False, timeout=15)
    assert_disk_unmounted(device)



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


def verify_uefi_ntfs_image(path: Path | None = None) -> None:
    if path is None:
        path = UEFI_NTFS_IMAGE
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

    Both partitions use Microsoft Basic Data. Partition 1 contains the NTFS
    Windows files; partition 2 contains the FAT UEFI:NTFS helper image and has
    the GUID-specific no-drive-letter attribute. Rufus deliberately does not
    mark this helper partition as an ESP: Windows Setup can fail when it sees
    two ESPs on one machine.
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
    """Resolve partition paths for /dev, /dev/disk/by-id and NVMe devices."""
    if device.startswith("/dev/disk/by-id/"):
        return f"{device}-part{number}"
    base = os.path.basename(device)
    separator = "p" if base and base[-1].isdigit() else ""
    return f"{device}{separator}{number}"


def normalize_iso_volume_label(value: str) -> str:
    """Make an ISO/UDF volume ID safe for both GPT partition and NTFS labels."""
    label = value.strip()
    # Labels are taken from untrusted ISO metadata. Do not let control
    # characters, quotes or filesystem-forbidden characters enter sfdisk.
    label = "".join(
        "_" if ord(char) < 32 or char in '<>:"/\\|?*' else char
        for char in label
    )
    label = label.rstrip(" .")[:36]
    return label or "BOOTMEDIA"


def read_iso_volume_label(image: Path) -> str:
    """Read the source ISO's own volume ID; fall back only when it has none."""
    result = command(
        ["blkid", "--probe", "--match-tag", "LABEL", "--output", "value", str(image)],
        check=False,
        timeout=20,
    )
    label = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if not label:
        listing = command(["7z", "l", "-slt", str(image)], check=False, timeout=30)
        for line in listing.stdout.splitlines():
            if line.startswith("Volume = "):
                label = line.partition("=")[2].strip()
                break
    return normalize_iso_volume_label(label)


def make_sfdisk_script(layout: dict[str, int], iso_label: str = "BOOTMEDIA") -> str:
    iso_label = normalize_iso_volume_label(iso_label)
    return (
        "label: gpt\n"
        "unit: sectors\n"
        f"first-lba: {GPT_ALIGNMENT_SECTORS}\n"
        f"start={layout['first_start']}, size={layout['first_size']}, "
        f"type={GPT_BASIC_DATA_GUID}, name=\"{iso_label}\"\n"
        f"start={layout['second_start']}, size={layout['second_size']}, "
        f"type={GPT_BASIC_DATA_GUID}, attrs={GPT_NO_DRIVE_LETTER_ATTR}, name=\"BMK_EFI\"\n"
    )



def _attribute_has_no_drive_letter(value: object) -> bool:
    """Accept sfdisk's textual GPT attribute representations for bit 63."""
    text = str(value or "").lower().replace(" ", "").replace(",", "")
    return (
        "guid:63" in text
        or "0x8000000000000000" in text
        or "9223372036854775808" in text
    )


def verify_gpt_layout(
    device: str,
    layout: dict[str, int],
    iso_label: str = "BOOTMEDIA",
) -> None:
    """Read back the GPT and reject an ESP-typed UEFI:NTFS helper partition."""
    iso_label = normalize_iso_volume_label(iso_label)
    command(["sfdisk", "--verify", device])
    result = command(["sfdisk", "--json", device])
    try:
        partition_table = json.loads(result.stdout)["partitiontable"]
        partitions = sorted(
            partition_table["partitions"],
            key=lambda part: int(part["start"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Nem sikerült visszaolvasni az elkészült GPT partíciós táblát.") from exc

    if partition_table.get("label", "").lower() != "gpt" or len(partitions) != 2:
        raise RuntimeError("A létrehozott USB nem a várt, kétpartíciós GPT elrendezést tartalmazza.")

    first, helper = partitions
    expected_ranges = (
        (int(first.get("start", -1)), int(first.get("size", -1)),
         layout["first_start"], layout["first_size"], "1. NTFS"),
        (int(helper.get("start", -1)), int(helper.get("size", -1)),
         layout["second_start"], layout["second_size"], "UEFI:NTFS"),
    )
    for actual_start, actual_size, expected_start, expected_size, label in expected_ranges:
        if actual_start != expected_start or actual_size != expected_size:
            raise RuntimeError(
                f"A(z) {label} GPT partíció mérete/kezdete eltér a tervezettől: "
                f"{actual_start}+{actual_size}, várt: {expected_start}+{expected_size}."
            )

    if first.get("name") != iso_label:
        raise RuntimeError(
            f"Az első GPT partíció neve nem egyezik az ISO címkéjével: "
            f"{first.get('name')!r}, várt: {iso_label!r}."
        )
    if helper.get("name") != BOOTMEDIA_FAT_VOLUME_LABEL:
        raise RuntimeError(
            f"Az UEFI segédpartíció GPT neve nem {BOOTMEDIA_FAT_VOLUME_LABEL}."
        )

    first_type = str(first.get("type", "")).strip("{}").lower()
    helper_type = str(helper.get("type", "")).strip("{}").lower()
    expected_type = GPT_BASIC_DATA_GUID.lower()
    if first_type != expected_type:
        raise RuntimeError("Az első USB-partíció GPT típusa nem Microsoft Basic Data.")
    if helper_type != expected_type:
        raise RuntimeError(
            "Az UEFI:NTFS segédpartíció hibás GPT típust kapott. "
            "Microsoft Basic Data szükséges, nem EFI System Partition (ESP), "
            "különben a Windows Setup több ESP-t érzékelhet."
        )

    attributes = helper.get("attrs")
    if not _attribute_has_no_drive_letter(attributes):
        attributes = command(["sfdisk", "--part-attrs", device, "2"]).stdout.strip()
    if not _attribute_has_no_drive_letter(attributes):
        raise RuntimeError(
            "Az UEFI:NTFS segédpartícióról hiányzik a GPT NoDriveLetter (GUID:63) attribútum."
        )


MBR_NTFS_PARTITION_TYPE = "7"
# MBR stores LBA start and size in 32 bits. util-linux (sfdisk 2.42) warns
# that a DOS label cannot be used on disks larger than 2199023255040 bytes
# (2**32 - 1 sectors of 512 bytes) and does not place a partition beyond that
# point; a larger disk would be silently cut. Such disks are refused instead.
MBR_MAX_SECTORS = 2**32 - 1


def calculate_mbr_layout(total_sectors: int) -> dict[str, int]:
    """One active NTFS partition from 1 MiB to the 1 MiB-aligned disk end.

    Units are 512-byte logical sectors; the caller rejects other sector
    sizes, as the Windows UEFI writer does.
    """
    sector_size = 512
    if total_sectors <= 0:
        raise ValueError("A lemezméretnek pozitívnak kell lennie.")
    if total_sectors > MBR_MAX_SECTORS:
        raise ValueError(
            "A célmeghajtó mérete eléri vagy meghaladja a 2 TiB-ot, az MBR partíciós tábla ennyit nem tud kezelni. "
            "Használj legfeljebb 2 TiB-os pendrive-ot, vagy válaszd az UEFI (GPT) módot."
        )
    start = GPT_ALIGNMENT_SECTORS
    size = ((total_sectors - start) // GPT_ALIGNMENT_SECTORS) * GPT_ALIGNMENT_SECTORS
    if size <= 0:
        raise ValueError("A meghajtó túl kicsi a Legacy BIOS (MBR) elrendezéshez.")
    return {"start": start, "size": size, "bytes": size * sector_size}


def make_mbr_sfdisk_script(layout: dict[str, int]) -> str:
    return (
        "label: dos\n"
        "unit: sectors\n"
        f"start={layout['start']}, size={layout['size']}, "
        f"type={MBR_NTFS_PARTITION_TYPE}, bootable\n"
    )


def verify_mbr_layout(device: str, layout: dict[str, int]) -> None:
    """Read back the MBR: one active type-7 partition exactly as planned."""
    command(["sfdisk", "--verify", device])
    result = command(["sfdisk", "--json", device])
    try:
        partition_table = json.loads(result.stdout)["partitiontable"]
        partitions = list(partition_table["partitions"])
        label = str(partition_table.get("label", "")).lower()
    except (KeyError, TypeError, ValueError, AttributeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Nem sikerült visszaolvasni az elkészült MBR partíciós táblát.") from exc

    if label != "dos" or len(partitions) != 1:
        raise RuntimeError(
            "A pendrive nem a várt MBR elrendezést tartalmazza (egyetlen partíció, dos címke); "
            "a műveletet leállítottam."
        )
    partition = partitions[0]
    try:
        actual_start = int(partition.get("start", -1))
        actual_size = int(partition.get("size", -1))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Az MBR partíció kezdete vagy mérete nem olvasható.") from exc
    if actual_start != layout["start"] or actual_size != layout["size"]:
        raise RuntimeError(
            "Az MBR partíció mérete/kezdete eltér a tervezettől: "
            f"{actual_start}+{actual_size}, várt: {layout['start']}+{layout['size']}."
        )
    partition_type = str(partition.get("type", "")).strip().lower()
    if partition_type.removeprefix("0x") != MBR_NTFS_PARTITION_TYPE:
        raise RuntimeError(
            f"Az MBR partíció típusa hibás: {partition_type!r}; elvárt: 7 (NTFS)."
        )
    if partition.get("bootable") is not True:
        raise RuntimeError("Az MBR partíció nincs aktívnak (indíthatónak) jelölve.")


GRUB_PC_DIRECTORY = Path("/usr/lib/grub/i386-pc")
GRUB_PC_REQUIRED_FILES = ("boot.img", "biosdisk.mod", "part_msdos.mod", "ntfs.mod", "ntldr.mod")
GRUB_INSTALL_TIMEOUT = 300
# Every module is loaded explicitly: some GRUB builds (2.14-2ubuntu2.1) do
# not autoload commands, and "ntldr" then fails with "can't find command".
BIOS_GRUB_CFG = (
    "insmod part_msdos\n"
    "insmod ntfs\n"
    "insmod ntldr\n"
    "insmod boot\n"
    "ntldr /bootmgr\n"
    "boot\n"
)
HOST_BOOT_DIRECTORIES = ("/boot", "/efi")
GRUB_MISSING_MESSAGE = (
    "A Legacy BIOS módhoz szükséges GRUB (i386-pc) nincs telepítve vagy hiányos ({detail}). "
    "Telepítsd a grub csomagot (sudo pacman -S grub), majd próbáld újra. "
    "A csomag telepítése nem módosítja a gép saját rendszerbetöltőjét."
)


def require_bios_grub() -> None:
    """Fail before any disk change when grub-install or i386-pc files are missing."""
    if shutil.which("grub-install") is None:
        raise RuntimeError(GRUB_MISSING_MESSAGE.format(detail="nincs grub-install"))
    if not GRUB_PC_DIRECTORY.is_dir():
        raise RuntimeError(GRUB_MISSING_MESSAGE.format(detail=f"nincs {GRUB_PC_DIRECTORY}"))
    missing = [name for name in GRUB_PC_REQUIRED_FILES if not (GRUB_PC_DIRECTORY / name).is_file()]
    if missing:
        raise RuntimeError(GRUB_MISSING_MESSAGE.format(detail="hiányzik: " + ", ".join(missing)))


def grub_install_args(device: str, ntfs_mount: str) -> list[str]:
    """The only grub-install command line BootMediaKit runs.

    BIOS target only, explicit --boot-directory on the target's NTFS mount,
    and the validated device as the last argument. Never the host's root,
    /boot or ESP.
    """
    if not isinstance(device, str) or not device.startswith("/dev/") or device != os.path.normpath(device):
        raise RuntimeError("A GRUB telepítésének céleszköze hiányzik vagy érvénytelen; a telepítést leállítottam.")
    if not isinstance(ntfs_mount, str) or not ntfs_mount or not os.path.isabs(ntfs_mount):
        raise RuntimeError("A GRUB könyvtárának helye hiányzik vagy nem abszolút útvonal; a telepítést leállítottam.")
    # POSIX normpath keeps a leading "//"; collapse it so "//boot" is /boot.
    boot_directory = "/" + os.path.normpath(ntfs_mount).lstrip("/")
    if boot_directory == "/" or any(
        boot_directory == root or boot_directory.startswith(root + "/") for root in HOST_BOOT_DIRECTORIES
    ):
        raise RuntimeError(
            f"A GRUB könyvtára nem lehet a gép saját gyökér-, /boot vagy /efi könyvtára ({boot_directory}); "
            "a telepítést biztonsági okból leállítottam."
        )
    return ["grub-install", "--target=i386-pc", f"--boot-directory={boot_directory}", device]


def assert_mount_is_partition(mountpoint: Path, partition: str) -> None:
    """The boot directory must be the target partition's own mountpoint."""
    if mountpoint.is_symlink() or os.path.realpath(mountpoint) != os.path.normpath(str(mountpoint)):
        raise RuntimeError("A pendrive csatolási pontja szimbolikus linken át vezet; a GRUB telepítését leállítottam.")
    result = command(["findmnt", "-rn", "-o", "SOURCE", "--mountpoint", str(mountpoint)], check=False, timeout=10)
    sources = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    try:
        wanted = os.stat(partition).st_rdev
        matches = bool(sources) and all(
            stat.S_ISBLK(os.stat(source).st_mode) and os.stat(source).st_rdev == wanted for source in sources
        )
    except OSError:
        matches = False
    if not matches:
        raise RuntimeError(
            f"A(z) {mountpoint} helyen nem a pendrive NTFS partíciója ({partition}) van csatolva; "
            "a GRUB telepítését biztonsági okból leállítottam."
        )


def read_mbr(device: str) -> bytes:
    with open(device, "rb", buffering=0) as source:
        return source.read(512)


def install_bios_chainloader(
    device: str,
    ntfs_mount: Path,
    expected_identity: dict[str, object] | None,
    layout: dict[str, int],
) -> None:
    """Install GRUB i386-pc to the target MBR gap and chainload /bootmgr."""
    check_cancelled()
    require_bios_grub()
    args = grub_install_args(device, str(ntfs_mount))
    assert_mount_is_partition(ntfs_mount, partition_path(device, 1))
    # Rule: the identity check runs again immediately before grub-install.
    validate_target(device, expected_identity)
    check_cancelled()
    emit(
        "GRUB indító telepítése a pendrive-ra…",
        99,
        log="A grub-install futása közben a megszakítás csak a lépés végén érvényesül.",
    )
    command(args, timeout=GRUB_INSTALL_TIMEOUT)
    check_cancelled()

    grub_dir = ntfs_mount / "grub"
    if grub_dir.is_symlink() or not grub_dir.is_dir():
        raise RuntimeError("A grub-install nem hozta létre a /grub könyvtárat a pendrive-on.")
    for module in ("ntfs.mod", "ntldr.mod"):
        if not (grub_dir / "i386-pc" / module).is_file():
            raise RuntimeError(f"A pendrive-ról hiányzik a GRUB modul: grub/i386-pc/{module}")
    config = grub_dir / "grub.cfg"
    fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        data = BIOS_GRUB_CFG.encode("ascii")
        if os.write(fd, data) != len(data):
            raise RuntimeError("A grub.cfg nem íródott ki teljesen.")
        os.fsync(fd)
    finally:
        os.close(fd)
    if config.read_text(encoding="ascii") != BIOS_GRUB_CFG:
        raise RuntimeError("A pendrive grub.cfg fájljának visszaolvasott tartalma eltér.")

    mbr = read_mbr(device)
    if len(mbr) != 512 or mbr[510:512] != b"\x55\xaa":
        raise RuntimeError("Az MBR 0x55AA aláírása hiányzik a GRUB telepítése után.")
    if mbr[:440] == bytes(440):
        raise RuntimeError("Az MBR indítókód-területe üres maradt; a GRUB nem települt.")
    verify_mbr_layout(device, layout)
    emit("A GRUB indító települt; a partíciós tábla változatlan.", 99)


def mount_iso(image: Path, mountpoint: Path) -> None:
    mountpoint.mkdir(parents=True, exist_ok=True)
    command(["mount", "-o", "loop,ro,nosuid,nodev", str(image), str(mountpoint)])


WINDOWS_BOOT_MODES = ("uefi", "bios")


def _check_bios_boot_files(iso_root: Path) -> None:
    """Files the Legacy BIOS chainload needs; EFI files are not required."""
    bootmgr = find_case_insensitive(iso_root, "bootmgr")
    if bootmgr is None or not bootmgr.is_file():
        i386 = find_case_insensitive(iso_root, "i386")
        if i386 is not None and i386.is_dir():
            raise RuntimeError(
                "Ez Windows XP / Server 2003 jellegű telepítő ISO (i386 könyvtár, bootmgr nélkül). "
                "Ezt a típust a BootMediaKit nem támogatja; válassz Windows Vista vagy újabb telepítő ISO-t."
            )
        raise RuntimeError(
            "Az ISO gyökerében nem található a bootmgr Windows indítókezelő, ezért a Legacy BIOS "
            "módhoz nem használható. Válaszd az UEFI módot, vagy egy bootmgr-t tartalmazó Windows ISO-t."
        )
    bcd = find_case_insensitive(iso_root, "boot/bcd")
    if bcd is None or not bcd.is_file():
        raise RuntimeError(
            "Nem található a boot/BCD Windows indítási konfiguráció, ezért az ISO a Legacy BIOS "
            "módhoz nem használható. Válaszd az UEFI módot, vagy egy teljes Windows telepítő ISO-t."
        )
    if find_case_insensitive(iso_root, "grub") is not None:
        raise RuntimeError(
            "Az ISO gyökerében már van „grub” nevű fájl vagy könyvtár. A Legacy BIOS mód ide "
            "telepítené a GRUB indítóját, de az ISO tartalmát nem írom felül. Használd az UEFI módot."
        )


def scan_windows_iso(iso_root: Path, boot_mode: str = "uefi") -> tuple[Path, Path, int]:
    """Validate essential Windows Setup files and return install image + size.

    ``boot_mode="uefi"`` (default) requires the x64 UEFI loader. ``"bios"``
    requires bootmgr and boot/BCD for the GRUB ntldr chainload instead, and
    refuses an ISO that already has a root "grub" entry.
    """
    if boot_mode not in WINDOWS_BOOT_MODES:
        raise ValueError(f"Ismeretlen indítási mód: {boot_mode!r}")
    if boot_mode == "bios":
        _check_bios_boot_files(iso_root)
    else:
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
                raise RuntimeError("Az ISO szimbolikus könyvtárlinket tartalmaz; ez a fájltípus biztonsági okból nem támogatott.")
        for name in files:
            file_path = current_path / name
            if file_path.is_symlink():
                raise RuntimeError("Az ISO szimbolikus fájllinket tartalmaz; ez a fájltípus biztonsági okból nem támogatott.")
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
    fast_copy_method = None
    if not hash_files:
        if hasattr(os, "copy_file_range"):
            fast_copy_method = "copy_file_range"
        elif hasattr(os, "sendfile"):
            fast_copy_method = "sendfile"
    unsupported_copy_errors = {
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
        check_cancelled()
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
                while fast_copy_method is not None and file_copied < expected_size:
                    check_cancelled()
                    try:
                        remaining = min(CHUNK, expected_size - file_copied)
                        if fast_copy_method == "copy_file_range":
                            amount = os.copy_file_range(
                                read_file.fileno(),
                                write_file.fileno(),
                                remaining,
                            )
                        else:
                            # sendfile() supports file-to-file copies on Linux
                            # and may work where copy_file_range returns EXDEV
                            # for an ISO9660 loop mount -> NTFS volume pair.
                            amount = os.sendfile(
                                write_file.fileno(),
                                read_file.fileno(),
                                None,
                                remaining,
                            )
                    except OSError as exc:
                        if exc.errno not in unsupported_copy_errors:
                            raise
                        if fast_copy_method == "copy_file_range" and hasattr(os, "sendfile"):
                            fast_copy_method = "sendfile"
                            emit(
                                "A fájlrendszerek közötti gyorsmásolás nem érhető el; alternatív kernelmásolásra váltok.",
                                log="A copy_file_range ezen a forrás/cél fájlrendszer-kombináción nem támogatott; a másolás folytatódik.",
                            )
                            continue
                        fast_copy_method = None
                        emit(
                            "A gyors kernelmásolás nem támogatott ezen a fájlrendszer-kombináción; "
                            "kompatibilis adatmásolásra váltok.",
                            log="A két fájlrendszer közötti gyorsmásolás nem támogatott; a kompatibilis másolás zavartalanul folytatódik.",
                        )
                        break
                    if amount == 0:
                        # Treat an early EOF as a reason to use the normal
                        # reader path, which will report a short source.
                        break
                    file_copied += amount
                    copied_total += amount
                    report_progress()

                while file_copied < expected_size:
                    check_cancelled()
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
        check_cancelled()
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
                check_cancelled()
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



def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_bmk_uefi_ntfs_image(upstream_image: Path, destination: Path) -> Path:
    """Make a temporary copy with BMK_EFI FAT volume label; preserve upstream."""
    if not upstream_image.is_file() or upstream_image.stat().st_size != UEFI_NTFS_IMAGE_SIZE:
        raise RuntimeError("Hiányzik vagy hibás méretű az ellenőrzött upstream UEFI:NTFS segédkép.")
    upstream_label = command(["fatlabel", str(upstream_image)]).stdout.strip().upper()
    if upstream_label != UPSTREAM_FAT_VOLUME_LABEL:
        raise RuntimeError(
            f"Az upstream FAT segédkép címkéje {upstream_label!r}; "
            f"elvárt: {UPSTREAM_FAT_VOLUME_LABEL}."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(upstream_image, destination)
    command(["fatlabel", str(destination), BOOTMEDIA_FAT_VOLUME_LABEL])
    actual_label = command(["fatlabel", str(destination)]).stdout.strip().upper()
    if actual_label != BOOTMEDIA_FAT_VOLUME_LABEL:
        raise RuntimeError("Nem sikerült a FAT segédpartíció kötetcímkéjét BMK_EFI értékre állítani.")
    if destination.stat().st_size != UEFI_NTFS_IMAGE_SIZE:
        raise RuntimeError("A BMK_EFI címkézett segédkép mérete megváltozott.")
    return destination



def write_uefi_ntfs_image(image: Path, partition: str) -> None:
    """Write the BMK_EFI-labelled FAT helper image and verify its exact bytes."""
    expected = image.stat().st_size
    if expected != UEFI_NTFS_IMAGE_SIZE:
        raise RuntimeError(
            f"A BMK_EFI segédkép mérete hibás: {expected}; elvárt: {UEFI_NTFS_IMAGE_SIZE}."
        )
    expected_sha256 = sha256_file(image)
    actual = int(command(["blockdev", "--getsize64", partition]).stdout.strip())
    if actual != expected:
        raise RuntimeError(
            f"Az UEFI:NTFS partíció mérete ({actual}) nem egyezik a segédkép méretével ({expected})."
        )
    emit("BMK_EFI FAT indítópartíció telepítése…", 38)
    fd = os.open(partition, os.O_WRONLY)
    try:
        with image.open("rb", buffering=0) as source:
            remaining = expected
            while remaining:
                check_cancelled()
                data = source.read(min(CHUNK, remaining))
                if not data:
                    raise RuntimeError("A BMK_EFI segédkép váratlanul véget ért.")
                view = memoryview(data)
                while view:
                    check_cancelled()
                    written = os.write(fd, view)
                    if written <= 0:
                        raise RuntimeError("Nem sikerült a BMK_EFI segédképet a partícióra írni.")
                    view = view[written:]
                remaining -= len(data)
        os.fsync(fd)
    finally:
        os.close(fd)

    command(["blockdev", "--flushbufs", partition])
    digest = hashlib.sha256()
    fd = os.open(partition, os.O_RDONLY)
    try:
        remaining = expected
        while remaining:
            check_cancelled()
            data = os.read(fd, min(CHUNK, remaining))
            if not data:
                raise RuntimeError("A BMK_EFI partíció visszaolvasása váratlanul véget ért.")
            digest.update(data)
            remaining -= len(data)
    finally:
        os.close(fd)
    if digest.hexdigest() != expected_sha256:
        raise RuntimeError("A BMK_EFI partíció SHA-256 visszaolvasása nem egyezik a címkézett képpel.")

    actual_label = command(["fatlabel", partition]).stdout.strip().upper()
    if actual_label != BOOTMEDIA_FAT_VOLUME_LABEL:
        raise RuntimeError(
            f"A pendrive FAT segédpartíciójának címkéje hibás: {actual_label!r}; "
            f"elvárt: {BOOTMEDIA_FAT_VOLUME_LABEL}."
        )
    emit("BMK_EFI FAT segédpartíció SHA-256 és kötetcímke visszaellenőrzése sikeres.", 40)



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


# -- Steps shared by the Windows UEFI and Legacy BIOS writers ---------------
# Moved verbatim from write_windows_uefi; the UEFI path runs the same
# commands with the same arguments, messages and order as before.


def read_512_byte_sector_count(device: str) -> int:
    """Reject non-512-byte logical sectors; return the size in sectors."""
    sector_size = int(command(["blockdev", "--getss", device]).stdout.strip())
    if sector_size != 512:
        raise RuntimeError(
            f"Ez a verzió 512 bájtos logikai szektort vár; a célmeghajtó {sector_size} bájtos szektorokat jelez."
        )
    return int(command(["blockdev", "--getsz", device]).stdout.strip())


def write_partition_table(device: str, script: str) -> None:
    """Apply an sfdisk script to the already wiped target and re-read it."""
    command(["sfdisk", "--wipe", "never", device], input_text=script)
    command(["blockdev", "--rereadpt", device], check=False)
    command(["partprobe", device], check=False)
    command(["udevadm", "settle"], check=False, timeout=20)


def wait_for_partition_nodes(partitions: Iterable[str], error: str, timeout: float = 20) -> None:
    """Wait until every partition node exists as a block device."""
    partitions = tuple(partitions)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_cancelled()
        if all(os.path.exists(partition) for partition in partitions):
            try:
                if all(stat.S_ISBLK(os.stat(partition).st_mode) for partition in partitions):
                    return
            except OSError:
                pass
        time.sleep(0.25)
    raise RuntimeError(error)


def format_ntfs(partition: str, label: str, start_sector: int) -> None:
    """mkfs.ntfs with the BPB geometry Windows boot code expects."""
    command(["mkfs.ntfs", "--fast", "--force", "--label", label, "--partition-start", str(start_sector), "--sector-size", "512", "--heads", "255", "--sectors-per-track", "63", "--cluster-size", "4096", partition], timeout=300)


def copy_windows_files(
    iso_mount: Path,
    usb_mount: Path,
    total_copy_bytes: int,
    verify: bool,
    boot_files: tuple[str, ...],
    missing_boot_file_message: str,
) -> None:
    """Copy the ISO tree, flush, recheck boot files and optionally verify SHA-256."""
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
    check_cancelled()
    emit("A másolt adatok kiírása a pendrive-ra…", copy_end_percent)
    sync_filesystem(usb_mount)

    # Recheck the boot chain files on the destination before unmounting.
    for relative in boot_files:
        check_cancelled()
        copied = find_case_insensitive(usb_mount, relative)
        if copied is None or not copied.is_file():
            raise RuntimeError(f"{missing_boot_file_message}: {relative}")
    if verify:
        emit("USB-re másolt Windows fájlok SHA-256 visszaellenőrzése…", 86)
        verify_copied_files(usb_mount, manifest)
    else:
        emit(
            "A teljes SHA-256 ellenőrzés kihagyva; az indítófájlok meglétét ellenőriztem.",
            copy_end_percent,
        )


def cleanup_windows_write(
    device: str,
    temp_root: Path,
    iso_mount: Path,
    usb_mount: Path,
    mounted_iso: bool,
    mounted_usb: bool,
) -> None:
    """Unmount everything the Windows writers mounted and remove temp files."""
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


def write_windows_uefi(
    image: Path,
    device: str,
    verify: bool = True,
    expected_identity: dict[str, object] | None = None,
) -> None:
    global TARGET_MODIFIED
    require_programs((
        "lsblk", "blockdev", "findmnt", "umount", "wipefs", "udevadm", "sync",
        "mount", "partprobe", "sfdisk", "mkfs.ntfs", "fatlabel", "blkid", "7z",
    ))

    # Validate both the removable target and the upstream boot image before
    # making any changes to the user's USB drive.
    check_cancelled()
    ensure_source_not_on_target(image, device)
    target_size = validate_target(device, expected_identity)
    verify_uefi_ntfs_image()
    total_sectors = read_512_byte_sector_count(device)
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
        check_cancelled()
        ensure_source_not_on_target(image, device)
        emit("Windows ISO és UEFI:NTFS segédkép ellenőrzése…", 1)
        mount_iso(image, iso_mount)
        mounted_iso = True
        install_image, boot_wim, total_copy_bytes = scan_windows_iso(iso_mount)
        iso_label = read_iso_volume_label(image)
        reserve_bytes = 128 * 1024 * 1024
        if total_copy_bytes + reserve_bytes > layout["first_bytes"]:
            raise RuntimeError(
                "Kevés a pendrive kapacitása a Windows ISO fájljaihoz. "
                f"Szükséges legalább {total_copy_bytes + reserve_bytes:,} bájt, "
                f"az NTFS partíció mérete {layout['first_bytes']:,} bájt. "
                "A pendrive tartalmához még nem nyúltam."
            )

        # Preserve the hash-pinned upstream image and alter only a temporary FAT label.
        bmk_efi_image = prepare_bmk_uefi_ntfs_image(
            UEFI_NTFS_IMAGE, temp_root / "uefi-ntfs-bmk-efi.img"
        )
        emit(
            "ISO előellenőrzés kész; a pendrive-ot még nem módosítottam.",
            8,
            log=(
                f"Windows PE: {boot_wim.relative_to(iso_mount)}; "
                f"telepítőkép: {install_image.relative_to(iso_mount)}; "
                f"ISO kötetcímke: {iso_label}; "
                f"másolandó fájlméret: {total_copy_bytes:,} bájt."
            ),
        )

        # From this point on, disk contents will be modified. The device was
        # validated before preflight; validate it once more immediately before
        # unmounting/wiping to catch a device swap or stale selection.
        check_cancelled()
        ensure_source_not_on_target(image, device)
        validate_target(device, expected_identity)
        emit("USB lemez leválasztása és GPT partíciók létrehozása…", 10)
        unmount_disk(device)
        # Last-moment identity and source checks after unmounting but before wipefs.
        validate_target(device, expected_identity)
        ensure_source_not_on_target(image, device)
        check_cancelled()
        assert_disk_unmounted(device)
        TARGET_MODIFIED = True
        # util-linux needs --force to erase a block-device partition-table signature.
        # assert_disk_unmounted() above ensures the target is not mounted.
        command(["wipefs", "--all", "--force", device])
        write_partition_table(device, make_sfdisk_script(layout, iso_label))
        verify_gpt_layout(device, layout, iso_label)
        emit(
            "GPT ellenőrzése sikeres: két Microsoft Basic Data partíció; "
            "az UEFI:NTFS segédpartíció automatikus meghajtóbetűjel nélkül.",
            22,
        )

        ntfs_partition = partition_path(device, 1)
        uefi_partition = partition_path(device, 2)
        wait_for_partition_nodes(
            (ntfs_partition, uefi_partition),
            "A GPT elkészült, de a kernel nem hozta létre időben a két partíció-eszközt.",
        )

        emit("NTFS fájlrendszer létrehozása…", 25)
        format_ntfs(ntfs_partition, iso_label, layout["first_start"])
        validate_ntfs_boot_sector(ntfs_partition, layout["first_start"])
        write_uefi_ntfs_image(bmk_efi_image, uefi_partition)

        emit("Windows ISO fájlok másolása az NTFS partícióra…", 42)
        usb_mount.mkdir(parents=True, exist_ok=True)
        check_cancelled()
        validate_target(device, expected_identity)
        unmount_disk(device)
        mount_ntfs_volume(ntfs_partition, usb_mount)
        mounted_usb = True
        copy_windows_files(
            iso_mount,
            usb_mount,
            total_copy_bytes,
            verify,
            ("efi/boot/bootx64.efi", "sources/boot.wim"),
            "A Windows UEFI indításhoz szükséges fájl hiányzik az USB-ről",
        )

        check_cancelled()
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
                "2. partíció BMK_EFI nevű Microsoft Basic Data / FAT UEFI:NTFS segédpartíció, "
                "NoDriveLetter GUID:63 attribútummal. A segédpartíció szándékosan nem ESP, "
                "hogy a Windows Setup ne találjon második EFI System Partitiont. "
                "A Windows ISO fájljai eredeti formájukban kerültek át."
            ),
        )
    finally:
        cleanup_windows_write(device, temp_root, iso_mount, usb_mount, mounted_iso, mounted_usb)


WINDOWS_BIOS_PROGRAMS = (
    "lsblk", "blockdev", "findmnt", "umount", "wipefs", "udevadm", "sync",
    "mount", "partprobe", "sfdisk", "mkfs.ntfs", "blkid", "7z",
)


def write_windows_bios(
    image: Path,
    device: str,
    verify: bool = True,
    expected_identity: dict[str, object] | None = None,
) -> None:
    """Windows Setup USB for Legacy BIOS/CSM: MBR, one active NTFS, GRUB ntldr."""
    global TARGET_MODIFIED
    require_programs(WINDOWS_BIOS_PROGRAMS)

    # Everything that can refuse the operation runs before the first write.
    check_cancelled()
    ensure_source_not_on_target(image, device)
    target_size = validate_target(device, expected_identity)
    require_bios_grub()
    total_sectors = read_512_byte_sector_count(device)
    layout = calculate_mbr_layout(total_sectors)
    if layout["start"] * 512 + layout["bytes"] > target_size:
        raise RuntimeError("A partíció számított mérete nagyobb, mint a célmeghajtó kapacitása.")

    temp_root = Path(tempfile.mkdtemp(prefix="bootmediakit-", dir="/run"))
    iso_mount = temp_root / "iso"
    usb_mount = temp_root / "usb"
    mounted_iso = False
    mounted_usb = False
    try:
        check_cancelled()
        ensure_source_not_on_target(image, device)
        emit("Windows ISO ellenőrzése a Legacy BIOS módhoz…", 1)
        mount_iso(image, iso_mount)
        mounted_iso = True
        install_image, boot_wim, total_copy_bytes = scan_windows_iso(iso_mount, boot_mode="bios")
        iso_label = read_iso_volume_label(image)
        reserve_bytes = 128 * 1024 * 1024
        if total_copy_bytes + reserve_bytes > layout["bytes"]:
            raise RuntimeError(
                "Kevés a pendrive kapacitása a Windows ISO fájljaihoz. "
                f"Szükséges legalább {total_copy_bytes + reserve_bytes:,} bájt, "
                f"az NTFS partíció mérete {layout['bytes']:,} bájt. "
                "A pendrive tartalmához még nem nyúltam."
            )
        emit(
            "ISO előellenőrzés kész; a pendrive-ot még nem módosítottam.",
            8,
            log=(
                f"Windows PE: {boot_wim.relative_to(iso_mount)}; "
                f"telepítőkép: {install_image.relative_to(iso_mount)}; "
                f"ISO kötetcímke: {iso_label}; "
                f"másolandó fájlméret: {total_copy_bytes:,} bájt."
            ),
        )

        check_cancelled()
        ensure_source_not_on_target(image, device)
        validate_target(device, expected_identity)
        emit("USB lemez leválasztása és MBR partíció létrehozása…", 10)
        unmount_disk(device)
        # Last-moment identity and source checks after unmounting but before wipefs.
        validate_target(device, expected_identity)
        ensure_source_not_on_target(image, device)
        check_cancelled()
        assert_disk_unmounted(device)
        TARGET_MODIFIED = True
        # util-linux needs --force to erase a block-device partition-table signature.
        # assert_disk_unmounted() above ensures the target is not mounted.
        command(["wipefs", "--all", "--force", device])
        write_partition_table(device, make_mbr_sfdisk_script(layout))
        verify_mbr_layout(device, layout)
        emit("MBR ellenőrzése sikeres: egy aktív NTFS partíció.", 22)

        ntfs_partition = partition_path(device, 1)
        wait_for_partition_nodes(
            (ntfs_partition,),
            "Az MBR elkészült, de a kernel nem hozta létre időben a partíció-eszközt.",
        )

        emit("NTFS fájlrendszer létrehozása…", 25)
        format_ntfs(ntfs_partition, iso_label, layout["start"])
        validate_ntfs_boot_sector(ntfs_partition, layout["start"])

        emit("Windows ISO fájlok másolása az NTFS partícióra…", 42)
        usb_mount.mkdir(parents=True, exist_ok=True)
        check_cancelled()
        validate_target(device, expected_identity)
        unmount_disk(device)
        mount_ntfs_volume(ntfs_partition, usb_mount)
        mounted_usb = True
        # The SHA-256 manifest covers the ISO files only; /grub is added later.
        copy_windows_files(
            iso_mount,
            usb_mount,
            total_copy_bytes,
            verify,
            ("bootmgr", "boot/bcd", "sources/boot.wim"),
            "A Windows Legacy BIOS indításhoz szükséges fájl hiányzik az USB-ről",
        )

        install_bios_chainloader(device, usb_mount, expected_identity, layout)

        check_cancelled()
        emit("Fájlrendszer kiürítése és leválasztása…", 99)
        sync_filesystem(usb_mount)
        command(["umount", "--", str(usb_mount)], timeout=120)
        mounted_usb = False
        command(["udevadm", "settle"], check=False, timeout=20)
        verify_mbr_layout(device, layout)
        emit(
            "A Windows Legacy BIOS telepítő USB elkészült.",
            100,
            log=(
                "MBR: egyetlen aktív NTFS partíció a Windows fájlokkal; "
                "GRUB láncbetöltő az MBR-ben és a /grub könyvtárban, amely a Windows bootmgr-t indítja. "
                "A pendrive csak Legacy BIOS / CSM módban indul, UEFI módban nem. "
                "A Windows ISO fájljai eredeti formájukban kerültek át."
            ),
        )
    finally:
        cleanup_windows_write(device, temp_root, iso_mount, usb_mount, mounted_iso, mounted_usb)


def write_raw(
    image: Path,
    device: str,
    verify: bool,
    expected_identity: dict[str, object] | None = None,
) -> None:
    global TARGET_MODIFIED
    image = image.resolve(strict=True)
    source_fd = os.open(image, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise RuntimeError("A RAW forrásnak normál, nem symlink fájlnak kell lennie.")
        source_size = source_stat.st_size
        if source_size <= 0:
            raise RuntimeError("A lemezkép üres.")

        check_cancelled()
        ensure_source_not_on_target(image, device)
        target_size = validate_target(device, expected_identity)
        if source_size > target_size:
            raise RuntimeError("A lemezkép nagyobb, mint a célmeghajtó.")
        require_programs(("lsblk", "blockdev", "findmnt", "umount", "wipefs", "udevadm", "sync"))

        emit(
            "Célmeghajtó ellenőrzése…",
            1,
            log=f"Forrás: {image} ({source_size:,} bájt); cél: {device} ({target_size:,} bájt)",
        )
        check_cancelled()
        unmount_disk(device)
        # Re-check the source filesystem and the physical disk identity at the
        # destructive boundary. The source fd remains open throughout writing.
        ensure_source_not_on_target(image, device)
        validate_target(device, expected_identity)
        check_cancelled()
        assert_disk_unmounted(device)
        emit("Régi partíciós és fájlrendszer-aláírások eltávolítása…", 2)
        TARGET_MODIFIED = True
        # util-linux needs --force to erase a block-device partition-table signature.
        # assert_disk_unmounted() above ensures the target is not mounted.
        command(["wipefs", "--all", "--force", device])
        command(["sync"])

        emit("Lemezkép kiírása…", 3)
        offset = 0
        os.lseek(source_fd, 0, os.SEEK_SET)
        fd = os.open(device, os.O_WRONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            while True:
                check_cancelled()
                data = os.read(source_fd, CHUNK)
                if not data:
                    break
                view = memoryview(data)
                while view:
                    check_cancelled()
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

        check_cancelled()
        command(["sync"])
        if verify:
            emit("Visszaolvasás és adategyezőség ellenőrzése…", 61)
            compared = 0
            os.lseek(source_fd, 0, os.SEEK_SET)
            command(["blockdev", "--flushbufs", device])
            target_fd = os.open(device, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
            try:
                while True:
                    check_cancelled()
                    expected = os.read(source_fd, CHUNK)
                    if not expected:
                        break
                    chunks: list[bytes] = []
                    remaining = len(expected)
                    while remaining:
                        check_cancelled()
                        part = os.read(target_fd, remaining)
                        if not part:
                            raise RuntimeError(
                                f"Rövid visszaolvasás a(z) {compared:,}. bájtnál; "
                                "a célmeghajtó nem adta vissza a teljes adatot."
                            )
                        chunks.append(part)
                        remaining -= len(part)
                    actual = b"".join(chunks)
                    if actual != expected:
                        mismatch = next(
                            (i for i, (a, b) in enumerate(zip(actual, expected)) if a != b),
                            0,
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
        check_cancelled()
        emit("A lemezkép sikeresen kiírva és ellenőrizve." if verify else "A lemezkép sikeresen kiírva.", 100)
    finally:
        os.close(source_fd)


def _assert_root_owned_path(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"Hiányzó vagy nem ellenőrizhető privilegizált fájl: {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise RuntimeError(f"A privilegizált útvonal nem lehet szimbolikus link: {path}")
    if info.st_uid != 0:
        raise RuntimeError(f"A privilegizált fájl/könyvtár nem root tulajdonú: {path}")
    if info.st_mode & 0o022:
        raise RuntimeError(f"A privilegizált fájl/könyvtár csoport vagy más felhasználó által írható: {path}")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"A privilegizált útvonal nem könyvtár: {path}")
    if not directory and not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"A privilegizált útvonal nem normál fájl: {path}")


def validate_privileged_install() -> None:
    """Refuse root execution from a user-writable checkout or modified install."""
    expected_worker = Path("/usr/lib/bootmediakit/worker.py")
    expected_wrapper = Path("/usr/libexec/bootmediakit/bootmediakit-worker")
    current_worker = Path(__file__).resolve(strict=True)
    if current_worker != expected_worker:
        raise RuntimeError(
            "A root worker csak a telepített /usr/lib/bootmediakit/worker.py útvonalról indulhat. "
            "Forráskönyvtárból történő közvetlen root indítás tiltott."
        )
    for path in (
        Path("/usr"),
        Path("/usr/lib"),
        Path("/usr/lib/bootmediakit"),
        Path("/usr/libexec"),
        Path("/usr/libexec/bootmediakit"),
        Path("/usr/share/polkit-1"),
        Path("/usr/share/polkit-1/actions"),
    ):
        _assert_root_owned_path(path, directory=True)
    _assert_root_owned_path(expected_worker, directory=False)
    _assert_root_owned_path(expected_wrapper, directory=False)
    _assert_root_owned_path(
        Path("/usr/share/polkit-1/actions/org.bootmediakit.policy"),
        directory=False,
    )
    try:
        wrapper_mode = expected_wrapper.stat().st_mode
    except OSError as exc:
        raise RuntimeError("A BootMediaKit root wrapper nem érhető el.") from exc
    if not wrapper_mode & 0o111:
        raise RuntimeError("A BootMediaKit root wrapper nem végrehajtható.")
    pkexec_uid = os.environ.get("PKEXEC_UID", "")
    if not pkexec_uid.isdigit() or int(pkexec_uid) == 0:
        raise RuntimeError("A worker csak a saját polkit akción keresztül indítható.")


def main(argv: list[str]) -> int:
    global TARGET_MODIFIED, OUTPUT_BROKEN
    TARGET_MODIFIED = False
    OUTPUT_BROKEN = False
    CANCEL_EVENT.clear()
    if len(argv) != 6:
        if not emit(
            "Hibás paraméterezés.",
            error="Használat: bootmediakit-worker raw|windows ISO DEVICE VERIFY IDENTITY_JSON",
        ):
            _write_stderr_safely("HIBA: Hibás BootMediaKit worker paraméterezés.")
        return 2
    mode, image_arg, device, verify_arg, identity_arg = argv[1:6]
    if os.geteuid() != 0:
        if not emit("A háttérfolyamat nem kapott rendszergazdai jogosultságot.", error="A művelethez a BootMediaKit polkit akció szükséges."):
            _write_stderr_safely("HIBA: A BootMediaKit worker nem kapott rendszergazdai jogosultságot.")
        return 1
    try:
        validate_privileged_install()
    except Exception as exc:
        if not emit("A privilegizált worker biztonsági ellenőrzése sikertelen.", error=str(exc)):
            _write_stderr_safely(f"HIBA: A privilegizált worker biztonsági ellenőrzése sikertelen: {exc}")
        return 1

    try:
        expected_identity = json.loads(identity_arg)
        if not isinstance(expected_identity, dict):
            raise ValueError("A meghajtóazonosító nem JSON objektum.")
        if mode not in {"raw", "windows"}:
            raise ValueError("Ismeretlen írási mód.")
        if verify_arg not in {"0", "1"}:
            raise ValueError("A visszaellenőrzés jelzője hibás.")
        image = Path(image_arg).expanduser().resolve(strict=True)
        if not image.is_file() or not os.access(image, os.R_OK):
            raise RuntimeError(f"A forrásfájl nem olvasható: {image}")
        if mode == "windows" and image.suffix.lower() != ".iso":
            raise RuntimeError("Windows telepítő készítéséhez ISO fájl szükséges.")

        start_control_reader()
        emit("A BootMediaKit biztonságos háttérfolyamata elindult.", 0, worker_started=True)
        check_cancelled()
        verify = verify_arg == "1"
        if mode == "raw":
            write_raw(image, device, verify, expected_identity)
        else:
            write_windows_uefi(image, device, verify, expected_identity)
        return 0
    except OperationCancelled as exc:
        if TARGET_MODIFIED:
            detail = (
                "A megszakítás biztonságos írási határon történt. A célmeghajtó részleges állapotban maradhat; "
                "újrahasználat előtt készítsd el ismét."
            )
        else:
            detail = "A megszakítás a célmeghajtó módosítása előtt történt; a cél tartalmához nem nyúltam."
        if not emit("A művelet biztonságosan megszakítva.", error=str(exc), log=detail, cancelled=True):
            _write_stderr_safely(f"Megszakítva: {exc}. {detail}")
        return 130
    except Exception as exc:
        if TARGET_MODIFIED:
            state_log = "A célmeghajtó állapota részleges lehet; ellenőrizd újracsatlakoztatás után."
        else:
            state_log = "A célmeghajtó tartalmát nem módosítottam; az előellenőrzés állította le a műveletet."
        if not emit("A művelet megszakadt.", error=str(exc), log=state_log):
            _write_stderr_safely(f"HIBA: {exc}. {state_log}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
