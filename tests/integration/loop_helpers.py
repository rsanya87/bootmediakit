"""Shared helpers for the loop-device integration tests.

These tests run the real writer functions of ``worker.py`` against a loop
device. They need root and are therefore opt-in: without ``BMK_INTEGRATION=1``,
root privileges and the required system tools every test is skipped.

A loop device is only a stand-in for a USB drive. ``loop_as_usb_disk()`` makes
``worker.lsblk_tree`` report the selected loop device as a removable ``disk``;
this substitution lives here and must never move into production code.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import worker  # noqa: E402

MIB = 1024 * 1024
REQUIRED_PROGRAMS = ("losetup", "sfdisk", "wipefs", "mkfs.ext4", "mkfs.ntfs", "fatlabel")
PARTITION_HELP = (
    "A kernel/udev nem hozta létre a loop eszköz partíció-eszközeit. "
    "Lásd: docs/TESTING.md, „Loop-device integration tests” szakasz."
)


def skip_unless_integration_environment(
    extra_programs: tuple[str, ...] = (),
    extra_directories: tuple[str, ...] = (),
) -> None:
    """Skip when the opt-in integration environment is absent.

    With ``BMK_INTEGRATION_REQUIRED=1`` (set in CI) a missing precondition is
    an error instead, so the CI step cannot turn green by skipping everything.
    ``extra_programs`` and ``extra_directories`` add test-specific
    preconditions; the shared ones apply to every test unchanged.
    """
    reason = ""
    if os.environ.get("BMK_INTEGRATION") != "1":
        reason = "BMK_INTEGRATION=1 szükséges."
    elif os.geteuid() != 0:
        reason = "root jogosultság szükséges (sudo)."
    else:
        missing = [
            name for name in (*REQUIRED_PROGRAMS, *extra_programs) if shutil.which(name) is None
        ]
        missing_dirs = [path for path in extra_directories if not os.path.isdir(path)]
        if missing:
            reason = "hiányzó program: " + ", ".join(missing)
        elif missing_dirs:
            reason = "hiányzó könyvtár: " + ", ".join(missing_dirs)
    if not reason:
        return
    if os.environ.get("BMK_INTEGRATION_REQUIRED") == "1":
        raise RuntimeError("Az integrációs teszt kötelező (BMK_INTEGRATION_REQUIRED=1), de " + reason)
    raise unittest.SkipTest("Integrációs teszt kihagyva: " + reason)


def run(args: list[str], *, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        input=input_text,
        stdin=None if input_text is not None else subprocess.DEVNULL,
        text=True,
        capture_output=True,
        timeout=300,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"Sikertelen parancs ({result.returncode}): {' '.join(args)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(MIB), b""):
            digest.update(block)
    return digest.hexdigest()


def signatures(device: str) -> list[tuple[int, str]]:
    """Return (offset, type) for every signature wipefs finds on device."""
    output = run(["wipefs", "--noheadings", "--output", "OFFSET,TYPE", device]).stdout
    found: list[tuple[int, str]] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2:
            found.append((int(fields[0], 16), fields[1]))
    return found


def mounts_from(device: str) -> list[str]:
    """Mountpoints whose source is the device or one of its partitions."""
    targets: list[str] = []
    with open("/proc/self/mountinfo", encoding="utf-8") as stream:
        for line in stream:
            fields = line.split()
            separator = fields.index("-")
            source = fields[separator + 2]
            if source == device or source.startswith(device + "p"):
                targets.append(worker._decode_mountinfo_field(fields[4]))
    return targets


class LoopIntegrationCase(unittest.TestCase):
    """Base class: tmpfs work directory, loop attach/detach and worker patching."""

    WORKDIR_SIZE_MIB = 512
    # Test-specific preconditions in addition to REQUIRED_PROGRAMS.
    EXTRA_REQUIRED_PROGRAMS: tuple[str, ...] = ()
    EXTRA_REQUIRED_DIRECTORIES: tuple[str, ...] = ()

    def setUp(self) -> None:
        skip_unless_integration_environment(
            self.EXTRA_REQUIRED_PROGRAMS, self.EXTRA_REQUIRED_DIRECTORIES
        )
        self.events: list[dict[str, object]] = []
        # A private tmpfs keeps the source files on a filesystem type the
        # worker's source/target collision check accepts on every host
        # (a container's overlay root would be rejected, by design).
        self.workdir = Path(tempfile.mkdtemp(prefix="bmk-integration-"))
        self.addCleanup(shutil.rmtree, self.workdir, True)
        run(["mount", "-t", "tmpfs", "-o", f"size={self.WORKDIR_SIZE_MIB}m,mode=0700", "tmpfs", str(self.workdir)])
        self.addCleanup(run, ["umount", "--lazy", str(self.workdir)], check=False)
        self._run_dirs_before = self._worker_run_dirs()
        for name in ("TARGET_MODIFIED", "OUTPUT_BROKEN"):
            patcher = patch.object(worker, name, False)
            patcher.start()
            self.addCleanup(patcher.stop)
        worker.CANCEL_EVENT.clear()

    # -- loop device ------------------------------------------------------

    def attach_loop(self, image: Path) -> str:
        device = run(["losetup", "--partscan", "--show", "--find", str(image)]).stdout.strip()
        self.assertTrue(device.startswith("/dev/loop"), msg=f"váratlan losetup kimenet: {device!r}")
        self.addCleanup(self._detach_loop, device)
        return device

    def _detach_loop(self, device: str) -> None:
        for target in sorted(mounts_from(device), key=len, reverse=True):
            run(["umount", "--", target], check=False)
        run(["udevadm", "settle"], check=False)
        run(["losetup", "--detach", device], check=False)

    def wait_for_partitions(self, device: str, count: int, timeout: float = 20.0) -> list[str]:
        """Return the partition device nodes or fail loudly (never pass silently)."""
        expected = [f"{device}p{number}" for number in range(1, count + 1)]
        # Ask the kernel to (re)scan; harmless when the scan already happened.
        run(["partx", "--update", device], check=False)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run(["udevadm", "settle"], check=False)
            if all(self._node_matches_kernel(path) for path in expected):
                return expected
            time.sleep(0.25)
        self.fail(f"{PARTITION_HELP} Hiányzik: {', '.join(p for p in expected if not os.path.exists(p))}")

    @staticmethod
    def _node_matches_kernel(path: str) -> bool:
        """True when /dev/loopNpM exists and has the device number sysfs reports."""
        name = os.path.basename(path)
        disk = name.rsplit("p", 1)[0]
        try:
            info = os.stat(path)
            wanted = Path("/sys/block", disk, name, "dev").read_text(encoding="ascii").strip()
        except OSError:
            return False
        return stat.S_ISBLK(info.st_mode) and wanted == f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"

    def kernel_partitions(self, device: str) -> list[str]:
        """Partition names the kernel currently knows, read from sysfs."""
        name = os.path.basename(device)
        return sorted(entry.name for entry in Path("/sys/block", name).glob(f"{name}p*"))

    # -- worker -----------------------------------------------------------

    @contextlib.contextmanager
    def loop_as_usb_disk(self, device: str):
        """Make the worker treat exactly this loop device as a removable disk."""
        real_lsblk_tree = worker.lsblk_tree
        wanted = os.path.realpath(device)

        def lsblk_tree(path: str, *, inverse: bool = False):
            nodes = real_lsblk_tree(path, inverse=inverse)
            for node in nodes:
                if node.get("type") == "loop" and os.path.realpath(str(node.get("path") or "")) == wanted:
                    node["type"] = "disk"
                    node["rm"] = True
            return nodes

        def record_event(message, percent=None, **fields):
            self.events.append({"message": message, "percent": percent, **fields})
            return True

        with patch.object(worker, "lsblk_tree", side_effect=lsblk_tree), patch.object(
            worker, "emit", side_effect=record_event
        ):
            yield

    def _worker_run_dirs(self) -> set[str]:
        return {entry.name for entry in Path("/run").glob("bootmediakit-*")}

    def assert_worker_left_no_mounts_or_temp_dirs(self, device: str) -> None:
        self.assertEqual(mounts_from(device), [], msg="a céleszköz kötete csatolva maradt")
        self.assertEqual(
            self._worker_run_dirs(), self._run_dirs_before,
            msg="a worker ideiglenes /run/bootmediakit-* könyvtára megmaradt",
        )
