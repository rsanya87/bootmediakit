"""Windows UEFI:NTFS write against a loop device.

There is no real Windows ISO here: a directory with the essential file names
is bind-mounted in place of the ISO (``worker.mount_iso`` is replaced).
"""

from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loop_helpers import MIB, LoopIntegrationCase, run, sha256_file, worker  # noqa: E402

DISK_SIZE = 384 * MIB
ISO_LABEL = "BMK_WIN_TEST"
BASIC_DATA = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"

ISO_FILES = {
    "bootmgr.efi": 64 * 1024,
    "setup.exe": 100_000,
    "efi/boot/bootx64.efi": 1 * MIB,
    "boot/bcd": 16 * 1024,
    "sources/boot.wim": 6 * MIB,
    "sources/install.wim": 20 * MIB + 12_345,
    "sources/lang.ini": 0,
    "support/Olvass el – árvíztűrő.txt": 777,
}


class LoopWindowsWriteTests(LoopIntegrationCase):
    WORKDIR_SIZE_MIB = 640

    def make_iso_tree(self) -> Path:
        root = self.workdir / "iso-root"
        generator = random.Random(0x57494E)
        for relative, size in ISO_FILES.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(generator.randbytes(size))
        return root

    def mount_ntfs_read_only(self, partition: str) -> Path:
        mountpoint = self.workdir / "verify-ntfs"
        mountpoint.mkdir()
        for filesystem in ("ntfs3", "ntfs-3g"):
            result = run(["mount", "-t", filesystem, "-o", "ro", partition, str(mountpoint)], check=False)
            if result.returncode == 0:
                self.addCleanup(run, ["umount", "--", str(mountpoint)], check=False)
                return mountpoint
        self.fail(f"Az elkészült NTFS partíció nem csatolható ellenőrzésre: {result.stderr}")

    def test_windows_write_creates_expected_gpt_labels_and_files(self):
        helper_image = self.locate_uefi_ntfs_image()
        iso_root = self.make_iso_tree()
        iso_file = self.workdir / "windows.iso"
        iso_file.write_bytes(b"BootMediaKit integration test placeholder ISO\n")

        disk = self.workdir / "disk.img"
        with disk.open("wb") as stream:
            stream.truncate(DISK_SIZE)
        device = self.attach_loop(disk)

        def bind_mount_iso(_image: Path, mountpoint: Path) -> None:
            mountpoint.mkdir(parents=True, exist_ok=True)
            run(["mount", "--bind", str(iso_root), str(mountpoint)])
            run(["mount", "-o", "remount,bind,ro", str(mountpoint)])

        with self.loop_as_usb_disk(device), patch.object(
            worker, "mount_iso", side_effect=bind_mount_iso
        ), patch.object(worker, "read_iso_volume_label", return_value=ISO_LABEL), patch.object(
            worker, "UEFI_NTFS_IMAGE", helper_image
        ):
            identity = worker.device_identity(device)
            worker.write_windows_uefi(iso_file, device, True, identity)

        run(["udevadm", "settle"], check=False)
        ntfs_partition, helper_partition = self.wait_for_partitions(device, 2)

        # GPT: two Microsoft Basic Data partitions, the 2nd BMK_EFI with GUID:63.
        table = json.loads(run(["sfdisk", "--json", device]).stdout)["partitiontable"]
        self.assertEqual(table["label"], "gpt")
        partitions = sorted(table["partitions"], key=lambda part: int(part["start"]))
        self.assertEqual(len(partitions), 2)
        for partition in partitions:
            self.assertEqual(partition["type"].strip("{}").upper(), BASIC_DATA)
        self.assertEqual(partitions[0]["name"], ISO_LABEL)
        self.assertEqual(partitions[1]["name"], "BMK_EFI")
        self.assertEqual(int(partitions[1]["size"]) * 512, 1 * MIB)
        attributes = partitions[1].get("attrs") or run(["sfdisk", "--part-attrs", device, "2"]).stdout
        self.assertIn("GUID:63", attributes)
        self.assertNotIn("attrs", partitions[0])

        # Filesystem types and labels.
        def probe(partition: str, tag: str) -> str:
            return run(["blkid", "--probe", "--match-tag", tag, "--output", "value", partition]).stdout.strip()

        self.assertEqual(probe(ntfs_partition, "TYPE"), "ntfs")
        self.assertEqual(probe(ntfs_partition, "LABEL"), ISO_LABEL)
        self.assertEqual(probe(helper_partition, "TYPE"), "vfat")
        self.assertEqual(run(["fatlabel", helper_partition]).stdout.strip(), "BMK_EFI")
        # The pinned upstream image itself must stay untouched.
        self.assertEqual(run(["fatlabel", str(helper_image)]).stdout.strip(), "RUFUS_BOOT")

        # Copied files: same set, same SHA-256.
        self.assert_worker_left_no_mounts_or_temp_dirs(device)
        mounted = self.mount_ntfs_read_only(ntfs_partition)
        copied = sorted(
            str(path.relative_to(mounted))
            for path in mounted.rglob("*")
            if path.is_file() and "System Volume Information" not in path.parts
        )
        self.assertEqual(copied, sorted(ISO_FILES))
        for relative in ISO_FILES:
            self.assertEqual(
                sha256_file(mounted / relative), sha256_file(iso_root / relative), msg=relative
            )

        self.assertTrue(worker.TARGET_MODIFIED)
        self.assertEqual(self.events[-1]["percent"], 100)


if __name__ == "__main__":
    unittest.main()
