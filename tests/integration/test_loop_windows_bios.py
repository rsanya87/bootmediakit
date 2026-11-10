"""T0 feasibility gate: GRUB i386-pc chainloads a Windows ``bootmgr`` from NTFS.

There is no production writer here yet. The test performs every step itself
on a loop device: MBR with one active NTFS partition, ``grub-install
--target=i386-pc`` into the MBR gap, a ``grub.cfg`` that runs ``ntldr
/bootmgr``, and a tiny test ``bootmgr`` that prints ``BMK-BOOT-OK`` to the
QEMU debug port. The QEMU boot is opt-in with ``BMK_QEMU=1``.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loop_helpers import MIB, LoopIntegrationCase, run, worker  # noqa: E402

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


class LoopWindowsBiosFeasibilityTests(LoopIntegrationCase):
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
        if os.environ.get("BMK_QEMU") != "1":
            raise unittest.SkipTest("QEMU-próba kihagyva: BMK_QEMU=1 szükséges.")
        qemu = next((shutil.which(name) for name in QEMU_PROGRAMS if shutil.which(name)), None)
        if qemu is None:
            raise unittest.SkipTest("QEMU-próba kihagyva: nincs qemu-system-x86_64 / qemu-system-i386.")

        disk, device, driver = self.build_media(drivers)
        self._detach_loop(device)

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
            f"\n[T0 versions] {tool_version(['grub-install', '--version'])}; "
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
            f"\n[T0 QEMU {driver}] {time.monotonic() - started:.1f} s, exit={process.returncode}, "
            f"debugcon={debug[:200]!r}\nqemu stderr: {stderr.decode(errors='replace').strip()}\n"
        )
        if not found:
            bios = seabios_log.read_text(encoding="utf-8", errors="replace") if seabios_log.is_file() else ""
            sys.stderr.write(
                "[T0 QEMU diag] SeaBIOS log (last 40 lines):\n"
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
            parts.append("[T0 QEMU diag] VGA text screen:\n" + (screen or "(empty)"))
        except OSError as exc:
            parts.append(f"[T0 QEMU diag] VGA text screen not readable: {exc}")
        try:
            registers = monitor_command(monitor_socket, "info registers")
            parts.append("[T0 QEMU diag] info registers (first 12 lines):\n" + "\n".join(registers.splitlines()[:12]))
        except OSError as exc:
            parts.append(f"[T0 QEMU diag] registers not readable: {exc}")
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
                parts.append(f"[T0 QEMU diag] grub> {command}\n" + (screen or "(empty)"))
            if debugcon.is_file() and BOOT_MARKER in debugcon.read_bytes():
                parts.append("[T0 QEMU diag] BMK-BOOT-OK appeared after the manual ntldr command.")
        except (OSError, KeyError) as exc:
            parts.append(f"[T0 QEMU diag] GRUB shell probe failed: {exc!r}")
        return "\n".join(parts)


if __name__ == "__main__":
    unittest.main()
