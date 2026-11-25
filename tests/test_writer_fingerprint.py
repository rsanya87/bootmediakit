"""Writer fingerprint tests: freeze what the three writers do (T1).

``write_raw``, ``write_windows_uefi`` and ``write_windows_bios`` are frozen
(docs/INVARIANTS.md, A1-A6). These tests run each writer through the real
``worker.main()`` without root and without any physical device:

* Every external program goes through a fake ``worker.command`` that records
  the arguments, the stdin script, the timeout and the check flag, and that
  simulates just enough of the system (sfdisk, mkfs.ntfs, fatlabel, mount,
  grub-install, blockdev) on regular files in a temporary directory.
* The functions that inspect the live host (``validate_target``,
  ``ensure_source_not_on_target``, ``unmount_disk``, ``assert_disk_unmounted``,
  ``require_programs``, ``require_bios_grub``, ``validate_privileged_install``)
  are replaced by recording stand-ins; their own logic has unit tests in
  tests/test_worker.py and loop-device tests in tests/integration/.
* Everything else is the production code: layout calculation and read-back,
  UEFI:NTFS image hash and label checks, NTFS boot sector check, file copy
  and SHA-256 verification, GRUB argument building and the grub.cfg write.
* ``os.open``/``os.fsync`` on the fake device, partitions and grub.cfg and
  every JSON event the worker prints (Hungarian text included) are recorded.

The recorded timeline is normalised (temporary paths become placeholders)
and compared with the golden files in tests/fixtures/writer_fingerprints/.

The golden files were produced from the last release before 0.4 work
started (the writers are unchanged since). Changing them is a
change to a frozen writer: it needs the INVARIANTS A6 decision gate and the
maintainer's approval. Set BMK_UPDATE_WRITER_FINGERPRINTS=1 to rewrite them;
the run then fails on purpose so that the diff is reviewed before anything
is committed.

Proof level: unit/mock. This does not replace the loop-device integration
tests, QEMU, or physical USB tests (docs/INVARIANTS.md D6).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import worker

GOLDEN_DIR = ROOT / "tests" / "fixtures" / "writer_fingerprints"
UPDATE_ENV = "BMK_UPDATE_WRITER_FINGERPRINTS"
# Additive event fields (T6, docs/MESSAGES.md). They are left out of the
# golden timeline, so the goldens keep pinning every field from before
# byte for byte; MessageIdTests checks the identifiers themselves.
ID_FIELDS = ("msg_id", "msg_args")
GOLDEN_FAILURE = (
    "A(z) {name} writer ujjlenyomata eltér a rögzítettől ({path}).\n"
    "A három writer befagyasztott (docs/INVARIANTS.md A1-A6). A golden fájl csak az "
    "INVARIANTS A6 döntési kapuján át, a gazda jóváhagyásával módosítható "
    "(hibajelenség, reprodukció, bizonyíték, kockázatelemzés, célzott regressziós "
    "teszt, fizikai teszt). Ha ez megvolt: {env}=1 írja újra, és a diffet a gazda "
    "ellenőrzi.\n"
    "The writer fingerprint changed. The writers are frozen (docs/INVARIANTS.md "
    "A1-A6); the golden file may only change through the A6 decision gate with "
    "the maintainer's approval.\n"
    "First difference at line {line}:\n  expected: {expected}\n  actual:   {actual}"
)

DISK_SECTORS = 16 * 1024 * 1024  # 8 GiB of 512-byte sectors
DISK_BYTES = DISK_SECTORS * 512
IDENTITY = {"serial": "FAKE-SERIAL", "size": DISK_BYTES}
ISO_LABEL = "CCCOMA_X64FRE_HU-HU_DV9"
RAW_IMAGE_BYTES = 20 * 1024 * 1024 + 123  # two and a half CHUNKs, odd tail
FAT_LABEL_OFFSET = 43  # FAT12/16 extended BPB volume label, 11 bytes

REAL_GRUB_INSTALL_ARGS = worker.grub_install_args
_REAL_STAT = os.stat
_REAL_OPEN = os.open
_REAL_FSYNC = os.fsync
_REAL_WALK = os.walk

OPEN_FLAG_NAMES = (
    "O_CREAT", "O_TRUNC", "O_APPEND", "O_EXCL",
    "O_NOFOLLOW", "O_CLOEXEC", "O_DIRECT", "O_SYNC", "O_DSYNC",
)

ISO_TREE = {
    "bootmgr": b"BOOTMGR" * 64,
    "boot/bcd": b"BCD" * 300,
    "boot/boot.sdi": b"SDI" * 1000,
    "efi/boot/bootx64.efi": b"MZ-EFI" * 500,
    "efi/microsoft/boot/bcd": b"EFIBCD" * 200,
    "setup.exe": b"MZ-SETUP" * 700,
    "sources/boot.wim": b"MSWIM-BOOT" * 3000,
    "sources/install.wim": b"MSWIM-INSTALL" * 5000,
}


def _flag_names(flags: int) -> list[str]:
    access = {os.O_RDONLY: "O_RDONLY", os.O_WRONLY: "O_WRONLY", os.O_RDWR: "O_RDWR"}[flags & os.O_ACCMODE]
    return [access, *(name for name in OPEN_FLAG_NAMES if getattr(os, name, 0) and flags & getattr(os, name))]


class _BlockStat:
    """os.stat result that reports a block device for the fake /dev files."""

    def __init__(self, real: os.stat_result, path: str) -> None:
        self._real = real
        self.st_mode = stat.S_IFBLK | 0o660
        self.st_rdev = zlib.crc32(path.encode("utf-8"))

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


class _EventStream(io.TextIOBase):
    """Collects the worker's JSON lines from print() into the timeline."""

    def __init__(self, sink) -> None:
        self._sink = sink
        self._buffer = ""

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self._sink(json.loads(line))
        return len(text)


def _parse_sfdisk_script(script: str) -> tuple[str, list[dict[str, object]]]:
    label = ""
    partitions: list[dict[str, object]] = []
    for line in script.splitlines():
        if line.startswith("label:"):
            label = line.split(":", 1)[1].strip()
            continue
        if not line.startswith("start="):
            continue
        entry: dict[str, object] = {}
        for item in line.split(", "):
            key, sep, value = item.partition("=")
            if not sep:
                entry[key.strip()] = True
            else:
                entry[key.strip()] = value.strip().strip('"')
        entry["start"] = int(entry["start"])
        entry["size"] = int(entry["size"])
        partitions.append(entry)
    return label, partitions


class FakeSystem:
    """A recording, simulating stand-in for the host the worker runs on."""

    def __init__(self, base: Path, *, sources: str = "windows") -> None:
        self.base = base
        self.dev_dir = base / "dev"
        self.dev_dir.mkdir()
        self.device = str(self.dev_dir / "sdX")
        self.run_dir = base / "run"
        self.run_dir.mkdir()
        self.temp_root = self.run_dir / "bootmediakit-fixed"
        self.source_dir = base / "source"
        self.source_dir.mkdir()
        self.iso_tree = base / "iso-tree"
        for relative, data in ISO_TREE.items():
            path = self.iso_tree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.steps: list[dict[str, object]] = []
        # Full JSON events including the additive msg_id/msg_args fields
        # (T6); the golden timeline keeps only the fields from before.
        self.full_events: list[dict[str, object]] = []
        self.table: tuple[str, list[dict[str, object]]] | None = None
        self.fd_paths: dict[int, str] = {}
        self.on_step = None
        with open(self.device, "wb") as handle:
            handle.truncate(DISK_BYTES)
        self.uefi_image = base / "uefi-ntfs.img"
        image = bytearray(worker.UEFI_NTFS_IMAGE_SIZE)
        image[0:3] = b"\xeb\x3c\x90"
        image[3:11] = b"MSWIN4.1"
        image[FAT_LABEL_OFFSET:FAT_LABEL_OFFSET + 11] = worker.UPSTREAM_FAT_VOLUME_LABEL.ljust(11).encode()
        image[54:62] = b"FAT12   "
        image[510:512] = b"\x55\xaa"
        for offset in range(4096, len(image), 4096):
            image[offset:offset + 8] = struct.pack("<Q", offset)
        self.uefi_image.write_bytes(bytes(image))

    # -- recording ------------------------------------------------------
    def record_event(self, event: dict[str, object]) -> None:
        self.full_events.append(event)
        self.record({"emit": {key: value for key, value in event.items() if key not in ID_FIELDS}})

    def record(self, step: dict[str, object]) -> None:
        self.steps.append(step)
        if self.on_step is not None:
            self.on_step(step)

    def spy(self, name: str, result: object = None, call_through=None):
        def stand_in(*args, **kwargs):
            step: dict[str, object] = {"call": name, "args": list(args)}
            if kwargs:
                step["kwargs"] = kwargs
            self.record(step)
            if call_through is not None:
                return call_through(*args, **kwargs)
            return result
        return stand_in

    # -- os-level hooks -------------------------------------------------
    def is_fake_device(self, path: object) -> bool:
        return isinstance(path, (str, os.PathLike)) and os.fspath(path).startswith(str(self.dev_dir) + "/")

    def fake_stat(self, path, *args, **kwargs):
        real = _REAL_STAT(path, *args, **kwargs)
        if self.is_fake_device(path):
            return _BlockStat(real, os.fspath(path))
        return real

    def fake_open(self, path, flags, *args, **kwargs):
        fd = _REAL_OPEN(path, flags, *args, **kwargs)
        text = os.fspath(path) if isinstance(path, (str, os.PathLike)) else ""
        # Record the fake device and partitions, and files opened for writing
        # (grub.cfg). Read-only opens of other files are not part of the
        # fingerprint: shutil.rmtree uses os.open differently across Python
        # versions.
        writes = flags & (os.O_WRONLY | os.O_RDWR)
        if text.startswith(str(self.base) + "/") and (self.is_fake_device(text) or writes):
            self.fd_paths[fd] = text
            self.record({"open": text, "flags": _flag_names(flags)})
        return fd

    def fake_fsync(self, fd):
        self.record({"fsync": self.fd_paths.get(fd, "<other>")})
        return _REAL_FSYNC(fd)

    @staticmethod
    def sorted_walk(top, *args, **kwargs):
        # Directory listing order depends on the filesystem; the writers do
        # not rely on it, but progress text does, so make it deterministic.
        for current, dirs, files in _REAL_WALK(top, *args, **kwargs):
            dirs.sort()
            files.sort()
            yield current, dirs, files

    def fake_mkdtemp(self, *, prefix: str = "", dir: str | None = None, **kwargs):
        self.record({"call": "tempfile.mkdtemp", "kwargs": {"prefix": prefix, "dir": dir}})
        self.temp_root.mkdir()
        return str(self.temp_root)

    # -- simulated programs ---------------------------------------------
    def command(self, args, *, check=True, timeout=None, input_text=None):
        args = [str(item) for item in args]
        step: dict[str, object] = {"run": args, "check": check}
        if timeout is not None:
            step["timeout"] = timeout
        if input_text is not None:
            step["input"] = input_text
        if args[:2] == ["umount", "--"] and Path(args[2]) == self.temp_root / "usb":
            step["usb_content"] = self.usb_snapshot(Path(args[2]))
        self.record(step)
        stdout = self.simulate(args, input_text)
        return subprocess.CompletedProcess(args, 0, stdout, "")

    def usb_snapshot(self, root: Path) -> list[str]:
        result = []
        for current, _dirs, files in self.sorted_walk(root):
            for name in files:
                path = Path(current) / name
                data = path.read_bytes()
                result.append(
                    f"{path.relative_to(root).as_posix()} {len(data)} {hashlib.sha256(data).hexdigest()[:16]}"
                )
        return result

    def partition_paths(self) -> list[str]:
        assert self.table is not None
        return [worker.partition_path(self.device, index + 1) for index in range(len(self.table[1]))]

    def simulate(self, args: list[str], input_text: str | None) -> str:
        program = args[0]
        if program == "blockdev":
            if args[1] == "--getss":
                return "512\n"
            if args[1] == "--getsz":
                return f"{DISK_SECTORS}\n"
            if args[1] == "--getsize64":
                return f"{os.path.getsize(args[2])}\n"
            if args[1] in ("--flushbufs", "--rereadpt"):
                return ""
        if program in ("wipefs", "partprobe", "udevadm", "sync", "umount"):
            return ""
        if program == "sfdisk":
            return self.sfdisk(args, input_text)
        if program == "blkid":
            return ISO_LABEL + "\n"
        if program == "fatlabel":
            return self.fatlabel(args)
        if program == "mkfs.ntfs":
            return self.mkfs_ntfs(args)
        if program == "mount":
            if args[1] == "-o":
                shutil.copytree(self.iso_tree, args[-1], dirs_exist_ok=True)
            return ""
        if program == "findmnt" and "--mountpoint" in args:
            return worker.partition_path(self.device, 1) + "\n"
        if program == "grub-install":
            return self.grub_install(args)
        raise AssertionError(f"a hamis rendszer nem ismeri ezt a parancsot: {args}")

    def sfdisk(self, args: list[str], input_text: str | None) -> str:
        if args[1] == "--wipe":
            label, partitions = _parse_sfdisk_script(input_text or "")
            self.table = (label, partitions)
            with open(self.device, "r+b") as disk:
                disk.seek(510)
                disk.write(b"\x55\xaa")
            for path, partition in zip(self.partition_paths(), partitions):
                with open(path, "wb") as handle:
                    handle.truncate(int(partition["size"]) * 512)
            return ""
        if args[1] == "--verify":
            return ""
        if args[1] == "--json":
            assert self.table is not None
            label, partitions = self.table
            entries = []
            for path, partition in zip(self.partition_paths(), partitions):
                entry = {"node": path, "start": partition["start"], "size": partition["size"],
                         "type": partition["type"]}
                if "name" in partition:
                    entry["name"] = partition["name"]
                if "attrs" in partition:
                    entry["attrs"] = partition["attrs"]
                if partition.get("bootable"):
                    entry["bootable"] = True
                entries.append(entry)
            return json.dumps({"partitiontable": {"label": label, "device": self.device,
                                                  "unit": "sectors", "partitions": entries}})
        raise AssertionError(f"váratlan sfdisk hívás: {args}")

    @staticmethod
    def fatlabel(args: list[str]) -> str:
        if len(args) == 3:
            with open(args[1], "r+b") as handle:
                handle.seek(FAT_LABEL_OFFSET)
                handle.write(args[2].ljust(11)[:11].encode("ascii"))
            return ""
        with open(args[1], "rb") as handle:
            handle.seek(FAT_LABEL_OFFSET)
            return handle.read(11).decode("ascii").strip() + "\n"

    @staticmethod
    def mkfs_ntfs(args: list[str]) -> str:
        options = dict(zip(args[1:-1], args[2:-1]))
        sector = int(options["--sector-size"])
        boot = bytearray(512)
        boot[0:3] = b"\xeb\x52\x90"
        boot[3:11] = b"NTFS    "
        struct.pack_into("<H", boot, 11, sector)
        boot[13] = int(options["--cluster-size"]) // sector
        struct.pack_into("<H", boot, 24, int(options["--sectors-per-track"]))
        struct.pack_into("<H", boot, 26, int(options["--heads"]))
        struct.pack_into("<I", boot, 28, int(options["--partition-start"]))
        boot[510:512] = b"\x55\xaa"
        with open(args[-1], "r+b") as partition:
            partition.write(bytes(boot))
        return ""

    def grub_install(self, args: list[str]) -> str:
        boot_directory = next(item.split("=", 1)[1] for item in args if item.startswith("--boot-directory="))
        modules = Path(boot_directory) / "grub" / "i386-pc"
        modules.mkdir(parents=True)
        for name in ("ntfs.mod", "ntldr.mod", "part_msdos.mod", "boot.img", "core.img"):
            (modules / name).write_bytes(b"GRUB-" + name.encode())
        with open(args[-1], "r+b") as disk:
            disk.write(b"\xeb\x63\x90GRUB-BOOT-CODE".ljust(440, b"\x01"))
        return ""

    def grub_install_args(self, device: str, ntfs_mount: str) -> list[str]:
        """Run the real argument builder on the /dev name of the fake disk.

        grub_install_args() accepts only /dev paths (INVARIANTS B5); the fake
        disk lives in a temporary directory, so the real function checks and
        builds the command line for /dev/<name>, and only the last argument is
        mapped back to the fake device file.
        """
        self.record({"call": "grub_install_args", "args": [device, ntfs_mount]})
        assert device == self.device
        args = REAL_GRUB_INSTALL_ARGS("/dev/" + os.path.basename(device), ntfs_mount)
        assert args[-1] == "/dev/" + os.path.basename(device)
        return [*args[:-1], device]

    # -- running a writer -----------------------------------------------
    def patches(self, *, disk_bytes: int = DISK_BYTES):
        return [
            patch.object(worker.os, "geteuid", return_value=0),
            patch.object(worker, "validate_privileged_install", self.spy("validate_privileged_install")),
            patch.object(worker, "start_control_reader", lambda: None),
            patch.object(worker, "require_programs", self.spy("require_programs")),
            patch.object(worker, "ensure_source_not_on_target", self.spy("ensure_source_not_on_target")),
            patch.object(worker, "validate_target", self.spy("validate_target", disk_bytes)),
            patch.object(worker, "unmount_disk", self.spy("unmount_disk")),
            patch.object(worker, "assert_disk_unmounted", self.spy("assert_disk_unmounted")),
            patch.object(worker, "require_bios_grub", self.spy("require_bios_grub")),
            patch.object(worker, "verify_uefi_ntfs_image",
                         self.spy("verify_uefi_ntfs_image", call_through=worker.verify_uefi_ntfs_image)),
            patch.object(worker, "validate_ntfs_boot_sector",
                         self.spy("validate_ntfs_boot_sector", call_through=worker.validate_ntfs_boot_sector)),
            patch.object(worker, "grub_install_args", self.grub_install_args),
            patch.object(worker, "command", self.command),
            patch.object(worker.tempfile, "mkdtemp", self.fake_mkdtemp),
            # The pinned upstream image is not in the repository; a generated
            # stand-in with its own pins exercises the same checks. The real
            # pins are part of the golden header.
            patch.object(worker, "UEFI_NTFS_IMAGE", self.uefi_image),
            patch.object(worker, "UEFI_NTFS_GIT_BLOB_SHA1", worker.git_blob_sha1(self.uefi_image)),
            patch.object(worker, "UEFI_NTFS_SHA256", hashlib.sha256(self.uefi_image.read_bytes()).hexdigest()),
            patch.object(worker.os, "stat", self.fake_stat),
            patch.object(worker.os, "open", self.fake_open),
            patch.object(worker.os, "fsync", self.fake_fsync),
            patch.object(worker.os, "walk", self.sorted_walk),
            patch.object(worker.sys, "stdout", _EventStream(self.record_event)),
        ]

    def run(self, mode: str, source: Path, *, verify: bool, disk_bytes: int = DISK_BYTES) -> int:
        argv = ["bootmediakit-worker", mode, str(source), self.device, "1" if verify else "0",
                json.dumps(IDENTITY)]
        worker.CANCEL_EVENT.clear()
        try:
            with contextlib.ExitStack() as stack:
                for item in self.patches(disk_bytes=disk_bytes):
                    stack.enter_context(item)
                code = worker.main(argv)
        finally:
            worker.CANCEL_EVENT.clear()
        self.steps.append({"exit": code})
        return code

    def normalised_lines(self) -> list[str]:
        replacements = (
            (str(self.temp_root), "<TEMP>"),
            (str(self.dev_dir), "/dev"),
            (str(self.source_dir), "<SOURCE>"),
            (str(self.base), "<TMP>"),
        )
        lines = []
        for step in self.steps:
            text = json.dumps(step, ensure_ascii=False, sort_keys=True, default=str)
            for old, new in replacements:
                text = text.replace(old, new)
            lines.append(text)
        return lines

    def commands(self) -> list[list[str]]:
        return [step["run"] for step in self.steps if "run" in step]

    def events(self) -> list[dict[str, object]]:
        return [step["emit"] for step in self.steps if "emit" in step]


def make_raw_image(path: Path, size: int = RAW_IMAGE_BYTES) -> bytes:
    block = hashlib.sha256(b"BootMediaKit RAW fingerprint").digest() * 2048
    data = (block * (size // len(block) + 1))[:size]
    path.write_bytes(data)
    return data


def golden_header(name: str) -> dict[str, object]:
    """Writer constants that the golden file pins next to the timeline."""
    header: dict[str, object] = {"fingerprint": name, "CHUNK": worker.CHUNK}
    if name.startswith("windows"):
        header.update({
            "GPT_ALIGNMENT_SECTORS": worker.GPT_ALIGNMENT_SECTORS,
            "windows_copy_progress_span": [worker.windows_copy_progress_span(True),
                                           worker.windows_copy_progress_span(False)],
        })
    if name.startswith("windows_uefi"):
        header.update({
            "UEFI_NTFS_IMAGE": str(worker.UEFI_NTFS_IMAGE),
            "UEFI_NTFS_IMAGE_SIZE": worker.UEFI_NTFS_IMAGE_SIZE,
            "UEFI_NTFS_GIT_BLOB_SHA1": worker.UEFI_NTFS_GIT_BLOB_SHA1,
            "UEFI_NTFS_SHA256": worker.UEFI_NTFS_SHA256,
            "UPSTREAM_FAT_VOLUME_LABEL": worker.UPSTREAM_FAT_VOLUME_LABEL,
            "BOOTMEDIA_FAT_VOLUME_LABEL": worker.BOOTMEDIA_FAT_VOLUME_LABEL,
            "GPT_BASIC_DATA_GUID": worker.GPT_BASIC_DATA_GUID,
            "GPT_NO_DRIVE_LETTER_ATTR": worker.GPT_NO_DRIVE_LETTER_ATTR,
            "GPT_RESERVED_SECTORS": worker.GPT_RESERVED_SECTORS,
        })
    if name.startswith("windows_bios"):
        header.update({
            "BIOS_GRUB_CFG": worker.BIOS_GRUB_CFG,
            "GRUB_PC_DIRECTORY": str(worker.GRUB_PC_DIRECTORY),
            "GRUB_PC_REQUIRED_FILES": list(worker.GRUB_PC_REQUIRED_FILES),
            "GRUB_INSTALL_TIMEOUT": worker.GRUB_INSTALL_TIMEOUT,
            "HOST_BOOT_DIRECTORIES": list(worker.HOST_BOOT_DIRECTORIES),
            "MBR_NTFS_PARTITION_TYPE": worker.MBR_NTFS_PARTITION_TYPE,
            "MBR_MAX_SECTORS": worker.MBR_MAX_SECTORS,
            "WINDOWS_BIOS_PROGRAMS": list(worker.WINDOWS_BIOS_PROGRAMS),
        })
    return header


class FakeSystemTestCase(unittest.TestCase):
    def make_system(self) -> FakeSystem:
        temp = tempfile.TemporaryDirectory(prefix="bmk-fingerprint-")
        self.addCleanup(temp.cleanup)
        return FakeSystem(Path(os.path.realpath(temp.name)))

    def source_for(self, system: FakeSystem, mode: str) -> Path:
        if mode == "raw":
            source = system.source_dir / "linux.iso"
            make_raw_image(source)
        else:
            source = system.source_dir / "windows.iso"
            source.write_bytes(b"fake Windows ISO; the fake mount supplies the tree")
        return source


class WriterFingerprintTests(FakeSystemTestCase):
    CASES = (
        ("raw_verify", "raw", True),
        ("raw_no_verify", "raw", False),
        ("windows_uefi_verify", "windows", True),
        ("windows_uefi_no_verify", "windows", False),
        ("windows_bios_verify", "windows-bios", True),
        ("windows_bios_no_verify", "windows-bios", False),
    )

    def fingerprint(self, name: str, mode: str, verify: bool) -> list[str]:
        system = self.make_system()
        code = system.run(mode, self.source_for(system, mode), verify=verify)
        self.assertEqual(code, 0, msg="\n".join(system.normalised_lines()[-5:]))
        header = json.dumps(golden_header(name), ensure_ascii=False, sort_keys=True)
        return [header, *system.normalised_lines()]

    def test_writers_match_their_golden_fingerprints(self):
        updated = []
        for name, mode, verify in self.CASES:
            with self.subTest(name=name):
                lines = self.fingerprint(name, mode, verify)
                path = GOLDEN_DIR / f"{name}.jsonl"
                if os.environ.get(UPDATE_ENV) == "1":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    updated.append(path.name)
                    continue
                self.assertTrue(path.is_file(), msg=f"hiányzik a golden fájl: {path}")
                expected = path.read_text(encoding="utf-8").splitlines()
                if expected != lines:
                    index = next(
                        (i for i, (a, b) in enumerate(zip(expected, lines)) if a != b),
                        min(len(expected), len(lines)),
                    )
                    self.fail(GOLDEN_FAILURE.format(
                        name=name,
                        path=path.relative_to(ROOT),
                        env=UPDATE_ENV,
                        line=index + 1,
                        expected=expected[index] if index < len(expected) else "<vége>",
                        actual=lines[index] if index < len(lines) else "<vége>",
                    ))
        if updated:
            self.fail(
                f"{UPDATE_ENV}=1: a golden fájlok újraírva ({', '.join(updated)}). "
                "Nézd át a diffet; commit csak a gazda jóváhagyásával (INVARIANTS A6)."
            )

    def test_fingerprint_is_deterministic(self):
        for name, mode, verify in (self.CASES[0], self.CASES[2], self.CASES[4]):
            with self.subTest(name=name):
                self.assertEqual(self.fingerprint(name, mode, verify), self.fingerprint(name, mode, verify))

    def test_golden_files_pin_the_frozen_essentials(self):
        """Readable guards on top of the byte-exact comparison."""
        def load(name):
            return [json.loads(line) for line in
                    (GOLDEN_DIR / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]

        for name, _mode, verify in self.CASES:
            with self.subTest(name=name):
                steps = load(name)
                runs = [step["run"] for step in steps if "run" in step]
                wipe = ["wipefs", "--all", "--force", "/dev/sdX"]
                self.assertEqual(runs.count(wipe), 1)
                self.assertEqual(steps[-1], {"exit": 0})
                calls = [step for step in steps if "call" in step or "run" in step]
                wipe_index = calls.index(next(step for step in calls if step.get("run") == wipe))
                before = [step.get("call") for step in calls[:wipe_index]]
                # The last checks before wipefs: identity, source collision, unmounted.
                self.assertEqual(
                    [call for call in before if call][-3:],
                    ["validate_target", "ensure_source_not_on_target", "assert_disk_unmounted"]
                    if not name.startswith("raw")
                    else ["ensure_source_not_on_target", "validate_target", "assert_disk_unmounted"],
                )
                events = [step["emit"] for step in steps if "emit" in step]
                self.assertTrue(all(not event["target_modified"] for event in events[: next(
                    i for i, event in enumerate(events) if event["target_modified"])]))
                self.assertEqual(events[-1]["percent"], 100)
                if name.startswith("raw"):
                    self.assertIn(["blockdev", "--rereadpt", "/dev/sdX"], runs)
                    self.assertEqual(any(run[:2] == ["blockdev", "--flushbufs"] for run in runs), verify)
                    self.assertIn({"fsync": "/dev/sdX"}, steps)
                if name.startswith("windows_uefi"):
                    script = next(step["input"] for step in steps if step.get("run", [""])[0] == "sfdisk"
                                  and "input" in step)
                    self.assertIn("label: gpt", script)
                    self.assertIn(f'name="{ISO_LABEL}"', script)
                    self.assertIn('attrs=GUID:63, name="BMK_EFI"', script)
                    self.assertIn(["fatlabel", "<TEMP>/uefi-ntfs-bmk-efi.img", "BMK_EFI"], runs)
                    self.assertIn({"call": "verify_uefi_ntfs_image", "args": []}, steps)
                if name.startswith("windows_bios"):
                    script = next(step["input"] for step in steps if step.get("run", [""])[0] == "sfdisk"
                                  and "input" in step)
                    self.assertEqual(
                        script,
                        f"label: dos\nunit: sectors\nstart=2048, size={DISK_SECTORS - 2048}, type=7, bootable\n",
                    )
                    grub = [run for run in runs if run[0] == "grub-install"]
                    self.assertEqual(
                        grub,
                        [["grub-install", "--target=i386-pc", "--boot-directory=<TEMP>/usb", "/dev/sdX"]],
                    )
                    grub_index = calls.index(next(step for step in calls if step.get("run") == grub[0]))
                    self.assertEqual(calls[grub_index - 1].get("call"), "validate_target")
                    self.assertIn({"fsync": "<TEMP>/usb/grub/grub.cfg"}, steps)


class CancellationBoundaryTests(FakeSystemTestCase):
    """Cooperative cancel at the writer boundaries (INVARIANTS A5)."""

    def run_with_cancel(self, mode: str, trigger, *, verify: bool = True):
        system = self.make_system()
        fired = []

        def on_step(step):
            if not fired and trigger(step):
                fired.append(step)
                worker.CANCEL_EVENT.set()

        system.on_step = on_step
        code = system.run(mode, self.source_for(system, mode), verify=verify)
        self.assertTrue(fired, msg="a megszakítás kiváltója nem futott le")
        return system, code

    def assert_cancelled(self, system: FakeSystem, code: int, *, modified: bool) -> None:
        self.assertEqual(code, 130)
        final = system.events()[-1]
        self.assertTrue(final.get("cancelled"))
        self.assertEqual(final["message"], "A művelet biztonságosan megszakítva.")
        self.assertEqual(final["target_modified"], modified)
        if modified:
            self.assertIn("részleges állapotban maradhat", final["log"])
        else:
            self.assertIn("a cél tartalmához nem nyúltam", final["log"])

    @staticmethod
    def fsyncs(system: FakeSystem) -> list[object]:
        return [step["fsync"] for step in system.steps if "fsync" in step]

    @staticmethod
    def call_is(name):
        return lambda step: step.get("call") == name

    @staticmethod
    def run_is(program, *prefix):
        return lambda step: step.get("run", [None])[: 1 + len(prefix)] == [program, *prefix]

    def test_cancel_before_wipefs_leaves_target_untouched(self):
        # The last cancel point before wipefs follows the unmount and the
        # final identity/source checks.
        for mode in ("raw", "windows", "windows-bios"):
            with self.subTest(mode=mode):
                system, code = self.run_with_cancel(mode, self.call_is("unmount_disk"))
                self.assert_cancelled(system, code, modified=False)
                self.assertNotIn("wipefs", [run[0] for run in system.commands()])
                self.assertEqual(self.fsyncs(system), [])

    def test_cancel_after_the_last_pre_wipe_point_takes_effect_after_wipefs(self):
        # Frozen behaviour: there is no cancel point between
        # assert_disk_unmounted() and wipefs, so a cancel arriving there is
        # honoured at the next boundary and reports a modified target.
        for mode in ("raw", "windows", "windows-bios"):
            with self.subTest(mode=mode):
                system, code = self.run_with_cancel(mode, self.call_is("assert_disk_unmounted"))
                self.assert_cancelled(system, code, modified=True)
                self.assertIn(["wipefs", "--all", "--force", system.device], system.commands())
                self.assertEqual(self.fsyncs(system), [])

    def test_cancel_right_after_wipefs_marks_target_modified_without_fsync(self):
        for mode in ("raw", "windows", "windows-bios"):
            with self.subTest(mode=mode):
                system, code = self.run_with_cancel(mode, self.run_is("wipefs"))
                self.assert_cancelled(system, code, modified=True)
                self.assertEqual(self.fsyncs(system), [])
                commands = system.commands()
                self.assertNotIn("mkfs.ntfs", [run[0] for run in commands])
                if mode == "raw":
                    # Stopped inside the write loop before the first chunk.
                    self.assertEqual(commands.count(["sync"]), 1)
                    self.assertFalse(any(
                        "emit" in step and step["emit"]["message"].startswith("Lemezkép kiírása… ")
                        for step in system.steps
                    ))
                else:
                    # Windows: the first cancel point after wipefs is the wait
                    # for the partition nodes, after the table was written.
                    self.assertEqual([run[0] for run in commands].count("sfdisk"), 3)

    def test_raw_cancel_mid_write_stops_without_fsync_or_read_back(self):
        system, code = self.run_with_cancel(
            "raw", lambda step: "emit" in step and step["emit"]["message"].startswith("Lemezkép kiírása… ")
        )
        self.assert_cancelled(system, code, modified=True)
        self.assertEqual(self.fsyncs(system), [])
        self.assertFalse(any(run[:2] == ["blockdev", "--flushbufs"] for run in system.commands()))
        self.assertNotIn(["blockdev", "--rereadpt", system.device], system.commands())

    def test_uefi_cancel_while_writing_the_helper_image_skips_its_fsync(self):
        system, code = self.run_with_cancel(
            "windows",
            lambda step: step.get("open", "").endswith("/sdX2") and step.get("flags") == ["O_WRONLY"],
        )
        self.assert_cancelled(system, code, modified=True)
        self.assertEqual(self.fsyncs(system), [])
        self.assertFalse(any(run[:2] == ["mount", "-t"] for run in system.commands()))

    def test_bios_cancel_before_grub_install_skips_the_bootloader(self):
        # The identity check that runs right before grub-install comes after
        # the findmnt check of the NTFS mountpoint.
        seen_mount_check = []

        def identity_check_before_grub(step):
            if "--mountpoint" in (step.get("run") or []):
                seen_mount_check.append(step)
            return bool(seen_mount_check) and step.get("call") == "validate_target"

        system, code = self.run_with_cancel("windows-bios", identity_check_before_grub, verify=False)
        self.assert_cancelled(system, code, modified=True)
        self.assertNotIn("grub-install", [run[0] for run in system.commands()])
        self.assertEqual(self.fsyncs(system), [])

    def test_bios_cancel_during_grub_install_skips_grub_cfg(self):
        system, code = self.run_with_cancel("windows-bios", self.run_is("grub-install"), verify=False)
        self.assert_cancelled(system, code, modified=True)
        self.assertEqual(self.fsyncs(system), [])
        self.assertFalse(any("grub.cfg" in str(step.get("open", "")) for step in system.steps))

    def test_cancel_after_the_final_event_does_not_undo_success(self):
        for mode in ("windows", "windows-bios"):
            with self.subTest(mode=mode):
                system, code = self.run_with_cancel(
                    mode, lambda step: "emit" in step and step["emit"].get("percent") == 100
                )
                self.assertEqual(code, 0)
                self.assertFalse(system.events()[-1].get("cancelled", False))

    def test_raw_checks_cancel_once_more_after_its_final_sync(self):
        # RAW checks for cancel after the final sync and before the success
        # event; a cancel there is still reported as a cancel.
        commands_seen = []

        def after_final_sync(step):
            if step.get("run") == ["sync"]:
                commands_seen.append(step)
            return len(commands_seen) == 3

        system, code = self.run_with_cancel("raw", after_final_sync)
        self.assert_cancelled(system, code, modified=True)
        self.assertNotEqual(system.events()[-2].get("percent"), 100)
        self.assertEqual(self.fsyncs(system), [system.device])


class RawByteExactnessTests(FakeSystemTestCase):
    """Fast file-based counterpart of the loop-device RAW test."""

    def test_raw_write_is_byte_exact_and_leaves_the_tail_untouched(self):
        for verify in (True, False):
            with self.subTest(verify=verify):
                system = self.make_system()
                source = system.source_dir / "linux.iso"
                payload = make_raw_image(source)
                tail = bytes([0xA5]) * 8192
                with open(system.device, "r+b") as device:
                    device.write(bytes([0x5A]) * len(payload) + tail)
                code = system.run("raw", source, verify=verify)
                self.assertEqual(code, 0)
                with open(system.device, "rb") as device:
                    self.assertEqual(device.read(len(payload)), payload)
                    self.assertEqual(device.read(len(tail)), tail)

    def test_raw_read_back_detects_a_corrupted_target(self):
        system = self.make_system()
        source = system.source_dir / "linux.iso"
        make_raw_image(source)
        real_fsync = system.fake_fsync

        def corrupt_after_fsync(fd):
            result = real_fsync(fd)
            with open(system.device, "r+b") as device:
                device.seek(worker.CHUNK + 7)
                value = device.read(1)[0]
                device.seek(worker.CHUNK + 7)
                device.write(bytes([value ^ 0xFF]))
            return result

        system.fake_fsync = corrupt_after_fsync
        code = system.run("raw", source, verify=True)
        self.assertEqual(code, 1)
        final = system.events()[-1]
        self.assertIn(f"{worker.CHUNK + 7:,}. bájtnál", final["error"])
        self.assertTrue(final["target_modified"])


if __name__ == "__main__":
    unittest.main()
