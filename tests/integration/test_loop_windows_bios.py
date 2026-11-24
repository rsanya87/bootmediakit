"""Windows Legacy BIOS/MBR media on a loop device, booted in QEMU/SeaBIOS.

``LoopWindowsBiosFeasibilityTests`` is the T0 gate. It performs every step
itself (MBR with one active NTFS partition, ``grub-install --target=i386-pc``
into the MBR gap, a ``grub.cfg`` that runs ``ntldr /bootmgr``) without the
production writer, so a GRUB or distribution change can be told apart from a
writer bug.

``LoopWindowsBiosWriterTests`` (T7) runs the production
``worker.write_windows_bios``; a bind-mounted directory stands in for the ISO,
as in ``test_loop_windows.py``.

Both boot a tiny test ``bootmgr`` that prints ``BMK-BOOT-OK`` to the QEMU
debug port. The QEMU boot is opt-in with ``BMK_QEMU=1``; with
``BMK_INTEGRATION_REQUIRED=1`` a missing QEMU binary is an error, not a skip.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loop_helpers import MIB, LoopIntegrationCase, run, sha256_file, signatures, worker  # noqa: E402

DISK_SIZE = 256 * MIB
SECTOR = 512
PARTITION_START = 2048  # sectors; 1 MiB
NTFS_LABEL = "BMK_T0_BIOS"
GRUB_PC_DIRECTORY = "/usr/lib/grub/i386-pc"
BOOT_MARKER = b"BMK-BOOT-OK"
QEMU_TIMEOUT = 60.0
QEMU_PROGRAMS = ("qemu-system-x86_64", "qemu-system-i386")

# Every module is loaded explicitly. GRUB 2.14-2ubuntu2.1 (CI) does not
# autoload commands from command.lst: without "insmod ntldr" the ntldr line
# fails with "can't find command", while a manual insmod works. GRUB 2.16
# (Arch) autoloads, so the explicit lines are harmless there.
GRUB_CFG = (
    "insmod part_msdos\n"
    "insmod ntfs\n"
    "insmod ntldr\n"
    "insmod boot\n"
    "ntldr /bootmgr\n"
    "boot\n"
)

# Same geometry as worker.write_windows_uefi's mkfs.ntfs call; HiddenSectors
# (--partition-start) is the partition's first sector.
MKFS_NTFS_GEOMETRY = (
    "--partition-start", str(PARTITION_START), "--sector-size", "512",
    "--heads", "255", "--sectors-per-track", "63", "--cluster-size", "4096",
)


def make_test_bootmgr() -> bytes:
    """Position-independent 16-bit real-mode code that prints BOOT_MARKER.

    It only assumes it is entered in real mode at the first byte (CS:IP),
    whatever segment the loader chose. Assembly (NASM syntax, BITS 16):

        start:  cli                     ; FA
                call next               ; E8 00 00
        next:   pop  si                 ; 5E        si = offset of next
                add  si, msg - next     ; 83 C6 15  msg - next = 0x15
                push cs                 ; 0E
                pop  ds                 ; 1F        ds:si -> msg
                mov  dx, 0xE9           ; BA E9 00  QEMU debugcon port
                cld                     ; FC
        print:  lodsb                   ; AC
                test al, al             ; 84 C0
                jz   halt               ; 74 03
                out  dx, al             ; EE
                jmp  print              ; EB F8
        halt:   hlt                     ; F4
                jmp  halt               ; EB FD
        msg:    db "BMK-BOOT-OK", 10, 0
    """
    code = bytes.fromhex(
        "FA" "E80000" "5E" "83C615" "0E" "1F" "BAE900" "FC"
        "AC" "84C0" "7403" "EE" "EBF8" "F4" "EBFD"
    )
    assert len(code) == 0x19 and 0x04 + 0x15 == len(code)
    return code + BOOT_MARKER + b"\n\0"


def host_grub_snapshot() -> dict[str, int]:
    """mtime of everything under the host's /boot/grub (empty if absent)."""
    root = Path("/boot/grub")
    snapshot: dict[str, int] = {}
    if not root.is_dir():
        return snapshot
    for path in [root, *root.rglob("*")]:
        try:
            snapshot[str(path)] = path.lstat().st_mtime_ns
        except OSError:
            pass
    return snapshot


def tool_version(args: list[str]) -> str:
    """First line of a tool's --version output, for the test log."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"{args[0]}: {exc}"
    lines = (result.stdout or result.stderr).strip().splitlines()
    return lines[0] if lines else f"{args[0]}: no output"


def monitor_command(sock_path: Path, command: str, timeout: float = 10.0) -> str:
    """Run one human-monitor command over QEMU's unix monitor socket."""
    prompt = b"(qemu) "
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect(str(sock_path))
        buffer = b""
        while not buffer.endswith(prompt):
            chunk = conn.recv(65536)
            if not chunk:
                break
            buffer += chunk
        conn.sendall(command.encode("ascii") + b"\n")
        buffer = b""
        while not buffer.rstrip(b" ").endswith(b"(qemu)"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            buffer += chunk
    text = buffer.decode("utf-8", errors="replace")
    # Drop terminal escape sequences and the echoed command / trailing prompt.
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text).replace("\r", "")
    lines = [line for line in text.split("\n") if line.strip() and not line.startswith("(qemu)")]
    # The monitor echoes the command as it is typed (readline redraws).
    if lines and lines[0].rstrip().endswith(command):
        lines = lines[1:]
    return "\n".join(lines)


# QEMU "sendkey" names for the characters the diagnostic GRUB commands use
# (US layout, as GRUB assumes).
SENDKEY_NAMES = {
    " ": "spc", "/": "slash", ".": "dot", "-": "minus", "_": "shift-minus",
    "$": "shift-4", "(": "shift-9", ")": "shift-0", ",": "comma", "=": "equal",
    "\n": "ret",
}
# "set" prints prefix/root without needing the echo module; the insmod
# errors tell a missing file from a read or format problem.
GRUB_DIAGNOSTIC_COMMANDS = (
    "set",
    "ls /grub",
    "ls -l /grub/i386-pc/command.lst",
    "ls -l /grub/i386-pc/ntldr.mod",
    "insmod echo",
    "insmod ntldr",
    "ntldr /bootmgr",
)


def type_into_guest(sock_path: Path, text: str) -> None:
    """Type text on the guest keyboard through the QEMU monitor."""
    for char in text:
        if char.isascii() and (char.islower() or char.isdigit()):
            key = char
        elif char.isascii() and char.isupper():
            key = "shift-" + char.lower()
        else:
            key = SENDKEY_NAMES[char]
        monitor_command(sock_path, f"sendkey {key}")
        time.sleep(0.03)


def vga_text_screen(xp_output: str) -> str:
    """Decode 'xp /2000hx 0xb8000' output (80x25 text cells) into lines."""
    values: list[str] = []
    for line in xp_output.splitlines():
        if ":" in line:
            values += re.findall(r"0x([0-9a-fA-F]{4})\b", line.split(":", 1)[1])
    cells = [int(value, 16) & 0xFF for value in values]
    chars = "".join(chr(cell) if 32 <= cell < 127 else " " for cell in cells)
    rows = [chars[index:index + 80].rstrip() for index in range(0, len(chars), 80)]
    while rows and not rows[-1]:
        rows.pop()
    return "\n".join(rows)


class QemuBootMixin:
    """Boot a raw disk image in QEMU/SeaBIOS and wait for BOOT_MARKER."""

    def find_qemu(self) -> str:
        if os.environ.get("BMK_QEMU") != "1":
            raise unittest.SkipTest("QEMU-próba kihagyva: BMK_QEMU=1 szükséges.")
        qemu = next((shutil.which(name) for name in QEMU_PROGRAMS if shutil.which(name)), None)
        if qemu is None:
            reason = "nincs qemu-system-x86_64 / qemu-system-i386."
            if os.environ.get("BMK_INTEGRATION_REQUIRED") == "1":
                raise RuntimeError(
                    "A QEMU-próba kötelező (BMK_INTEGRATION_REQUIRED=1, BMK_QEMU=1), de " + reason
                )
            raise unittest.SkipTest("QEMU-próba kihagyva: " + reason)
        return qemu

    def assert_boots_in_qemu(self, qemu: str, disk: Path, tag: str) -> None:
        """The image must reach the test bootmgr within QEMU_TIMEOUT seconds."""
        output = self.workdir / "debugcon.txt"
        seabios_log = self.workdir / "seabios.log"
        monitor_socket = self.workdir / "qemu-monitor.sock"
        args = [
            qemu, "-machine", "pc", "-accel", "tcg", "-m", "128",
            "-display", "none", "-no-reboot", "-serial", "none",
            "-monitor", f"unix:{monitor_socket},server=on,wait=off",
            "-parallel", "none",
            "-drive", f"file={disk},format=raw,if=ide,snapshot=on",
            "-boot", "c", "-debugcon", f"file:{output}",
            # Diagnostics only: SeaBIOS writes its own log to port 0x402.
            "-chardev", f"file,id=seabioslog,path={seabios_log}",
            "-device", "isa-debugcon,iobase=0x402,chardev=seabioslog",
        ]
        sys.stderr.write(
            f"\n[{tag} versions] {tool_version(['grub-install', '--version'])}; "
            f"{tool_version([qemu, '--version'])}\n"
        )
        started = time.monotonic()
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        found = False
        diagnostics = ""
        try:
            while time.monotonic() - started < QEMU_TIMEOUT:
                if output.is_file() and BOOT_MARKER in output.read_bytes():
                    found = True
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.25)
            if not found and process.poll() is None:
                diagnostics = self.collect_qemu_diagnostics(monitor_socket)
                if "grub>" in diagnostics:
                    diagnostics += "\n" + self.probe_grub_shell(monitor_socket, output)
        finally:
            if process.poll() is None:
                process.kill()
            stdout, stderr = process.communicate(timeout=10)
        debug = output.read_bytes() if output.is_file() else b""
        sys.stderr.write(
            f"\n[{tag}] {time.monotonic() - started:.1f} s, exit={process.returncode}, "
            f"debugcon={debug[:200]!r}\nqemu stderr: {stderr.decode(errors='replace').strip()}\n"
        )
        if not found:
            bios = seabios_log.read_text(encoding="utf-8", errors="replace") if seabios_log.is_file() else ""
            sys.stderr.write(
                f"[{tag} diag] SeaBIOS log (last 40 lines):\n"
                + ("\n".join(bios.splitlines()[-40:]) or "(empty)")
                + "\n" + diagnostics + "\n"
            )
        self.assertTrue(
            found,
            msg=(
                f"A BMK-BOOT-OK nem jelent meg {QEMU_TIMEOUT:.0f} s alatt. "
                f"debugcon: {debug[:200]!r}; qemu stdout: {stdout[:500]!r}; stderr: {stderr[:500]!r}"
            ),
        )

    @staticmethod
    def collect_qemu_diagnostics(monitor_socket: Path) -> str:
        """Screen text and CPU state of a running guest; never raises."""
        parts: list[str] = []
        try:
            screen = vga_text_screen(monitor_command(monitor_socket, "xp /2000hx 0xb8000"))
            parts.append("[QEMU diag] VGA text screen:\n" + (screen or "(empty)"))
        except OSError as exc:
            parts.append(f"[QEMU diag] VGA text screen not readable: {exc}")
        try:
            registers = monitor_command(monitor_socket, "info registers")
            parts.append("[QEMU diag] info registers (first 12 lines):\n" + "\n".join(registers.splitlines()[:12]))
        except OSError as exc:
            parts.append(f"[QEMU diag] registers not readable: {exc}")
        return "\n".join(parts)

    @staticmethod
    def probe_grub_shell(monitor_socket: Path, debugcon: Path) -> str:
        """At a grub> prompt, run read-only commands and capture each screen.

        Diagnostics only: the media and grub.cfg are not changed. The last
        command repeats the configured "ntldr /bootmgr" by hand so that its
        error message (if any) is not cleared by the prompt's screen reset.
        """
        parts: list[str] = []
        try:
            for command in GRUB_DIAGNOSTIC_COMMANDS:
                type_into_guest(monitor_socket, "clear\n")
                time.sleep(1.0)
                type_into_guest(monitor_socket, command + "\n")
                time.sleep(3.0)
                screen = vga_text_screen(monitor_command(monitor_socket, "xp /2000hx 0xb8000"))
                parts.append(f"[QEMU diag] grub> {command}\n" + (screen or "(empty)"))
            if debugcon.is_file() and BOOT_MARKER in debugcon.read_bytes():
                parts.append("[QEMU diag] BMK-BOOT-OK appeared after the manual ntldr command.")
        except (OSError, KeyError) as exc:
            parts.append(f"[QEMU diag] GRUB shell probe failed: {exc!r}")
        return "\n".join(parts)


class LoopWindowsBiosFeasibilityTests(QemuBootMixin, LoopIntegrationCase):
    """T0 gate. A failure here means: stop and ask the maintainer."""

    WORKDIR_SIZE_MIB = 320
    EXTRA_REQUIRED_PROGRAMS = ("grub-install",)
    EXTRA_REQUIRED_DIRECTORIES = (GRUB_PC_DIRECTORY,)

    # -- media construction ------------------------------------------------

    def mount_ntfs(self, partition: str, mountpoint: Path, driver: str) -> bool:
        mountpoint.mkdir(parents=True, exist_ok=True)
        result = run(
            ["mount", "-t", driver, "-o", "rw,nosuid,nodev", partition, str(mountpoint)],
            check=False,
        )
        if result.returncode != 0:
            self.mount_errors[driver] = result.stderr.strip()
            return False
        self.addCleanup(run, ["umount", "--", str(mountpoint)], check=False)
        return True

    def build_media(self, drivers: tuple[str, ...]) -> tuple[Path, str, str]:
        """Create the T0 media; return (image, loop device, ntfs driver used)."""
        self.mount_errors: dict[str, str] = {}
        disk = self.workdir / "disk.img"
        with disk.open("wb") as stream:
            stream.truncate(DISK_SIZE)
        device = self.attach_loop(disk)

        # 2. MBR, one active type-7 partition from 1 MiB to the end.
        run(
            ["sfdisk", "--quiet", "--wipe", "always", device],
            input_text=f"label: dos\nunit: sectors\nstart={PARTITION_START}, type=7, bootable\n",
        )
        (partition,) = self.wait_for_partitions(device, 1)

        # 3. NTFS with the production geometry; checked by the production validator.
        run(["mkfs.ntfs", "--fast", "--force", "--label", NTFS_LABEL, *MKFS_NTFS_GEOMETRY, partition])
        worker.validate_ntfs_boot_sector(partition, PARTITION_START)

        table_before = run(["sfdisk", "--dump", device]).stdout
        with open(device, "rb") as stream:
            mbr_before = stream.read(SECTOR)
        self.assertEqual(mbr_before[:440], bytes(440), msg="az MBR boot-kód területe már a GRUB előtt sem üres")

        # 4. Mount (kernel ntfs3 first, then ntfs-3g) and add the test bootmgr.
        mountpoint = self.workdir / "ntfs"
        driver = next((name for name in drivers if self.mount_ntfs(partition, mountpoint, name)), "")
        if not driver:
            raise unittest.SkipTest(f"NTFS csatolás nem sikerült ({', '.join(drivers)}): {self.mount_errors}")
        (mountpoint / "bootmgr").write_bytes(make_test_bootmgr())

        # 5. grub-install into the loop device's MBR gap, no --force.
        host_before = host_grub_snapshot()
        args = ["grub-install", "--target=i386-pc", f"--boot-directory={mountpoint}", device]
        result = run(args, check=False)
        report = (
            f"\n[T0 {driver}] {' '.join(args)} -> {result.returncode}\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}\n"
        )
        sys.stderr.write(report)
        self.assertEqual(result.returncode, 0, msg="a grub-install --force nélkül nem futott le" + report)
        self.assertNotIn("blocklist", (result.stdout + result.stderr).lower(), msg=report)
        self.assertEqual(host_grub_snapshot(), host_before, msg="a gazdagép /boot/grub könyvtára megváltozott")

        grub_dir = mountpoint / "grub"
        cfg = grub_dir / "grub.cfg"
        with cfg.open("w", encoding="ascii") as stream:
            stream.write(GRUB_CFG)
            stream.flush()
            os.fsync(stream.fileno())
        self.assertTrue(cfg.is_file())
        for module in ("ntfs.mod", "ntldr.mod"):
            self.assertTrue((grub_dir / "i386-pc" / module).is_file(), msg=f"hiányzik: grub/i386-pc/{module}")

        # 6. Unmount and flush.
        run(["umount", "--", str(mountpoint)])
        run(["sync"])

        # 8. Static checks.
        self.assertEqual(run(["sfdisk", "--dump", device]).stdout, table_before,
                         msg="a grub-install megváltoztatta a partíciós táblát")
        with open(device, "rb") as stream:
            mbr = stream.read(SECTOR)
            gap = stream.read((PARTITION_START - 1) * SECTOR)
        self.assertEqual(mbr[510:512], b"\x55\xaa")
        self.assertNotEqual(mbr[:440], bytes(440), msg="az MBR boot-kód területe üres maradt")
        self.assertEqual(mbr[440:510], mbr_before[440:510], msg="a lemezazonosító vagy a partíciós bejegyzés megváltozott")
        self.assertNotEqual(gap, bytes(len(gap)), msg="a partíció előtti résben nincs core.img")
        self.assertEqual(mbr[446], 0x80, msg="az 1. partíció nem aktív")
        self.assertEqual(mbr[450], 0x07, msg="az 1. partíció típusa nem 7")
        return disk, device, driver

    # -- tests ---------------------------------------------------------------

    def test_grub_install_static_checks_with_kernel_ntfs3(self):
        self.build_media(("ntfs3",))

    def test_grub_install_static_checks_with_ntfs_3g_fuseblk(self):
        if shutil.which("ntfs-3g") is None:
            raise unittest.SkipTest("az ntfs-3g nincs telepítve")
        self.build_media(("ntfs-3g",))

    def test_qemu_seabios_chainloads_bootmgr(self):
        self.boot_media_in_qemu(("ntfs3", "ntfs-3g"))

    def test_qemu_seabios_chainloads_bootmgr_from_ntfs_3g_media(self):
        """Same boot check; GRUB and bootmgr written through ntfs-3g instead of ntfs3."""
        if shutil.which("ntfs-3g") is None:
            raise unittest.SkipTest("az ntfs-3g nincs telepítve")
        self.boot_media_in_qemu(("ntfs-3g",))

    def boot_media_in_qemu(self, drivers: tuple[str, ...]) -> None:
        qemu = self.find_qemu()
        disk, device, driver = self.build_media(drivers)
        self._detach_loop(device)
        self.assert_boots_in_qemu(qemu, disk, f"T0 QEMU {driver}")


# -- T7: the production writer ---------------------------------------------

WRITER_ISO_LABEL = "BMK_BIOS_TEST"
# What scan_windows_iso(boot_mode="bios") needs, without the EFI loader; the
# bootmgr is the test program that prints BOOT_MARKER. Mixed-case names check
# that the writer finds and copies the ISO's own spelling; every path uses the
# same spelling of a directory, because on a case-sensitive source two
# spellings ("Boot", "boot") would be two directories, which an ISO cannot have.
WRITER_ISO_FILES: dict[str, bytes | int] = {
    "bootmgr": make_test_bootmgr(),
    "setup.exe": 100_000,
    "Boot/BCD": 16 * 1024,
    "Boot/boot.sdi": 3 * MIB,
    "sources/boot.wim": 6 * MIB,
    "sources/install.wim": 20 * MIB + 12_345,
    "sources/lang.ini": 0,
    "support/Olvass el – árvíztűrő.txt": 777,
}


class LoopWindowsBiosWriterTests(QemuBootMixin, LoopIntegrationCase):
    """worker.write_windows_bios against a loop device (T7)."""

    WORKDIR_SIZE_MIB = 448
    EXTRA_REQUIRED_PROGRAMS = ("grub-install", *worker.WINDOWS_BIOS_PROGRAMS)
    EXTRA_REQUIRED_DIRECTORIES = (GRUB_PC_DIRECTORY,)

    def make_iso_tree(self) -> Path:
        root = self.workdir / "iso-root"
        generator = random.Random(0x42494F53)
        for relative, content in WRITER_ISO_FILES.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else generator.randbytes(content))
        return root

    def make_disk(self) -> tuple[Path, str]:
        disk = self.workdir / "disk.img"
        with disk.open("wb") as stream:
            stream.truncate(DISK_SIZE)
        return disk, self.attach_loop(disk)

    def write_bios(self, device: str, iso_root: Path) -> None:
        iso_file = self.workdir / "windows.iso"
        iso_file.write_bytes(b"BootMediaKit integration test placeholder ISO\n")

        def bind_mount_iso(_image: Path, mountpoint: Path) -> None:
            mountpoint.mkdir(parents=True, exist_ok=True)
            run(["mount", "--bind", str(iso_root), str(mountpoint)])
            run(["mount", "-o", "remount,bind,ro", str(mountpoint)])

        host_before = host_grub_snapshot()
        with self.loop_as_usb_disk(device), patch.object(
            worker, "mount_iso", side_effect=bind_mount_iso
        ), patch.object(worker, "read_iso_volume_label", return_value=WRITER_ISO_LABEL):
            identity = worker.device_identity(device)
            worker.write_windows_bios(iso_file, device, True, identity)
        run(["udevadm", "settle"], check=False)
        self.assertEqual(host_grub_snapshot(), host_before, msg="a gazdagép /boot/grub könyvtára megváltozott")
        self.assertTrue(worker.TARGET_MODIFIED)
        self.assertEqual(self.events[-1]["percent"], 100)

    def mount_ntfs_read_only(self, partition: str) -> Path:
        mountpoint = self.workdir / "verify-ntfs"
        mountpoint.mkdir()
        for filesystem in ("ntfs3", "ntfs-3g"):
            result = run(["mount", "-t", filesystem, "-o", "ro", partition, str(mountpoint)], check=False)
            if result.returncode == 0:
                self.addCleanup(run, ["umount", "--", str(mountpoint)], check=False)
                return mountpoint
        self.fail(f"Az elkészült NTFS partíció nem csatolható ellenőrzésre: {result.stderr}")

    def assert_bios_media(self, device: str, iso_root: Path) -> None:
        """Partition table, filesystem, files, grub.cfg and the T0 static checks."""
        (partition,) = self.wait_for_partitions(device, 1)
        self.assertEqual(self.kernel_partitions(device), [os.path.basename(partition)])

        # MBR: dos, one active type-7 partition from 1 MiB to the aligned end.
        layout = worker.calculate_mbr_layout(DISK_SIZE // SECTOR)
        table = json.loads(run(["sfdisk", "--json", device]).stdout)["partitiontable"]
        self.assertEqual(table["label"], "dos")
        self.assertEqual(len(table["partitions"]), 1)
        (entry,) = table["partitions"]
        self.assertEqual(entry["type"], "7")
        self.assertTrue(entry.get("bootable"))
        self.assertEqual(int(entry["start"]), PARTITION_START)
        self.assertEqual(int(entry["start"]), layout["start"])
        self.assertEqual(int(entry["size"]) * SECTOR, layout["bytes"])

        def probe(tag: str) -> str:
            return run(["blkid", "--probe", "--match-tag", tag, "--output", "value", partition]).stdout.strip()

        self.assertEqual(probe("TYPE"), "ntfs")
        self.assertEqual(probe("LABEL"), WRITER_ISO_LABEL)
        worker.validate_ntfs_boot_sector(partition, PARTITION_START)

        # T0 static checks: boot signature, GRUB boot code and core.img in the gap.
        with open(device, "rb") as stream:
            mbr = stream.read(SECTOR)
            gap = stream.read((PARTITION_START - 1) * SECTOR)
        self.assertEqual(mbr[510:512], b"\x55\xaa")
        self.assertNotEqual(mbr[:440], bytes(440), msg="az MBR boot-kód területe üres maradt")
        self.assertNotEqual(gap, bytes(len(gap)), msg="a partíció előtti résben nincs core.img")
        self.assertEqual(mbr[446], 0x80, msg="az 1. partíció nem aktív")
        self.assertEqual(mbr[450], 0x07, msg="az 1. partíció típusa nem 7")

        self.assert_worker_left_no_mounts_or_temp_dirs(device)
        mounted = self.mount_ntfs_read_only(partition)
        grub_dir = mounted / "grub"
        self.assertEqual((grub_dir / "grub.cfg").read_text(encoding="ascii"), worker.BIOS_GRUB_CFG)
        for module in ("ntfs.mod", "ntldr.mod"):
            self.assertTrue((grub_dir / "i386-pc" / module).is_file(), msg=f"hiányzik: grub/i386-pc/{module}")

        # Every ISO file arrived unchanged; besides them only /grub was added.
        copied = sorted(
            str(path.relative_to(mounted))
            for path in mounted.rglob("*")
            if path.is_file()
            and "System Volume Information" not in path.parts
            and path.relative_to(mounted).parts[0] != "grub"
        )
        self.assertEqual(copied, sorted(WRITER_ISO_FILES))
        for relative in WRITER_ISO_FILES:
            self.assertEqual(sha256_file(mounted / relative), sha256_file(iso_root / relative), msg=relative)
        top_level = sorted(path.name for path in mounted.iterdir() if path.name != "System Volume Information")
        expected_top = sorted({relative.split("/")[0] for relative in WRITER_ISO_FILES} | {"grub"})
        self.assertEqual(top_level, expected_top)

    def test_bios_write_creates_active_ntfs_mbr_with_grub_and_files(self):
        iso_root = self.make_iso_tree()
        _disk, device = self.make_disk()
        self.write_bios(device, iso_root)
        self.assert_bios_media(device, iso_root)

    def test_qemu_seabios_boots_bootmgr_from_written_media(self):
        qemu = self.find_qemu()
        iso_root = self.make_iso_tree()
        disk, device = self.make_disk()
        self.write_bios(device, iso_root)
        self.assert_worker_left_no_mounts_or_temp_dirs(device)
        self._detach_loop(device)
        self.assert_boots_in_qemu(qemu, disk, "T7 QEMU writer")

    def test_bios_write_over_uefi_gpt_media_leaves_no_gpt_signature(self):
        helper_image = self.locate_uefi_ntfs_image()
        iso_root = self.make_iso_tree()
        # The UEFI writer needs the EFI loader. It is removed before the BIOS
        # write so that assert_bios_media can compare against WRITER_ISO_FILES.
        efi_loader = iso_root / "efi" / "boot" / "bootx64.efi"
        efi_loader.parent.mkdir(parents=True)
        efi_loader.write_bytes(b"\0" * 4096)
        disk, device = self.make_disk()

        def bind_mount_iso(_image: Path, mountpoint: Path) -> None:
            mountpoint.mkdir(parents=True, exist_ok=True)
            run(["mount", "--bind", str(iso_root), str(mountpoint)])
            run(["mount", "-o", "remount,bind,ro", str(mountpoint)])

        uefi_iso = self.workdir / "uefi.iso"
        uefi_iso.write_bytes(b"BootMediaKit integration test placeholder ISO\n")
        with self.loop_as_usb_disk(device), patch.object(
            worker, "mount_iso", side_effect=bind_mount_iso
        ), patch.object(worker, "read_iso_volume_label", return_value="BMK_UEFI_OLD"), patch.object(
            worker, "UEFI_NTFS_IMAGE", helper_image
        ):
            worker.write_windows_uefi(uefi_iso, device, False, worker.device_identity(device))
        run(["udevadm", "settle"], check=False)
        self.wait_for_partitions(device, 2)
        self.assertTrue(self.has_gpt_header(device, 1), msg="az előkészítő UEFI-írás nem hozott létre GPT-t")
        self.assertTrue(self.has_gpt_header(device, DISK_SIZE // SECTOR - 1), msg="nincs tartalék GPT-fejléc")
        worker.TARGET_MODIFIED = False
        self.events.clear()

        efi_loader.unlink()
        efi_loader.parent.rmdir()
        efi_loader.parent.parent.rmdir()
        self.write_bios(device, iso_root)

        types = [kind for _offset, kind in signatures(device)]
        self.assertNotIn("gpt", types, msg=f"GPT-aláírás maradt: {signatures(device)}")
        self.assertNotIn("PMBR", types, msg=f"védő MBR maradt: {signatures(device)}")
        self.assertFalse(self.has_gpt_header(device, 1), msg="az elsődleges GPT-fejléc megmaradt")
        self.assertFalse(
            self.has_gpt_header(device, DISK_SIZE // SECTOR - 1), msg="a tartalék GPT-fejléc megmaradt"
        )
        self.assert_bios_media(device, iso_root)

    @staticmethod
    def has_gpt_header(device: str, lba: int) -> bool:
        with open(device, "rb") as stream:
            stream.seek(lba * SECTOR)
            return stream.read(8) == b"EFI PART"


if __name__ == "__main__":
    unittest.main()
