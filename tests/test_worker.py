import json
import errno
import hashlib
import os
import struct
import subprocess
import shutil
import stat
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import worker
from iso_utils import is_windows_install_iso

_REAL_OS_STAT = os.stat


def fake_dev_stat(block_stat):
    """Return block_stat for /dev paths only; real files keep the real stat."""
    def stat_side_effect(path, *args, **kwargs):
        if isinstance(path, str) and path.startswith("/dev/"):
            return block_stat
        return _REAL_OS_STAT(path, *args, **kwargs)
    return stat_side_effect


class WorkerSafetyTests(unittest.TestCase):
    def test_relative_target_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "érvényes /dev"):
            worker.validate_target("sdb")

    def test_non_block_device_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "blokk eszköz"):
            worker.validate_target("/dev/null")

    def test_case_insensitive_iso_lookup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            boot = root / "EFI" / "Boot"
            boot.mkdir(parents=True)
            image = boot / "BootX64.EFI"
            image.write_bytes(b"test")
            found = worker.find_case_insensitive(root, "efi/boot/bootx64.efi")
            self.assertEqual(found, image)

    def test_missing_iso_path_returns_none(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertIsNone(
                worker.find_case_insensitive(Path(temp), "sources/install.wim")
            )

    def test_windows_iso_detector_recognizes_install_wim(self):
        result = subprocess.CompletedProcess(
            ["7z"], 0, "Path = test.iso\nPath = sources\\install.wim\n", ""
        )
        with patch("shutil.which", return_value="/usr/bin/7z"), patch(
            "subprocess.run", return_value=result
        ):
            self.assertTrue(is_windows_install_iso(Path("fake.iso")))

    def test_windows_iso_detector_ignores_regular_linux_iso(self):
        result = subprocess.CompletedProcess(
            ["7z"], 0, "Path = test.iso\nPath = casper/filesystem.squashfs\n", ""
        )
        with patch("shutil.which", return_value="/usr/bin/7z"), patch(
            "subprocess.run", return_value=result
        ):
            self.assertFalse(is_windows_install_iso(Path("fake.iso")))


class P0SecurityTests(unittest.TestCase):
    def test_device_identity_rejects_diskseq_change_even_when_devnode_is_reused(self):
        expected = {
            "size": 8 * 1024**3, "maj_min": "8:16", "model": "USB Disk",
            "serial": "", "wwn": "", "tran": "usb", "diskseq": "41", "by_id": "",
        }
        current = dict(expected, diskseq="42")
        with self.assertRaisesRegex(RuntimeError, "diskseq"):
            worker.compare_device_identity(expected, current)

    def test_device_identity_rejects_capacity_or_major_minor_change(self):
        expected = {
            "size": 8 * 1024**3, "maj_min": "8:16", "model": "USB Disk",
            "serial": "ABC123", "wwn": "", "tran": "usb", "diskseq": "41", "by_id": "",
        }
        with self.assertRaisesRegex(RuntimeError, "size"):
            worker.compare_device_identity(expected, dict(expected, size=16 * 1024**3))
        with self.assertRaisesRegex(RuntimeError, "maj_min"):
            worker.compare_device_identity(expected, dict(expected, **{"maj_min": "8:32"}))

    def test_device_identity_requires_at_least_one_stable_hardware_token(self):
        expected = {
            "size": 1024, "maj_min": "8:16", "model": "", "serial": "",
            "wwn": "", "tran": "usb", "diskseq": "", "by_id": "",
        }
        with self.assertRaisesRegex(RuntimeError, "stabil"):
            worker.compare_device_identity(expected, expected)

    def test_source_on_target_disk_is_rejected_before_any_destructive_step(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image.iso"
            image.write_bytes(b"source image")
            identity = {"maj_min": "8:0"}
            with patch("worker.source_backing_majmins", return_value={"8:0", "8:1"}), patch(
                "worker.device_identity", return_value=identity
            ), patch("worker._block_ancestor_majmins", return_value={"8:0"}):
                with self.assertRaisesRegex(RuntimeError, "forrásfájl a célmeghajtó"):
                    worker.ensure_source_not_on_target(image, "/dev/sdb")

    def test_source_on_different_physical_disk_is_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image.iso"
            image.write_bytes(b"source image")
            with patch("worker.source_backing_majmins", return_value={"8:17", "8:16"}), patch(
                "worker.device_identity", return_value={"maj_min": "8:32"}
            ), patch("worker._block_ancestor_majmins", return_value={"8:32"}):
                worker.ensure_source_not_on_target(image, "/dev/sdc")

    def test_target_with_luks_partition_is_rejected(self):
        disk = {"type": "disk", "path": "/dev/sdb", "children": [
            {"type": "part", "path": "/dev/sdb1", "fstype": "crypto_LUKS", "label": "vault"}
        ]}
        with patch("worker.lsblk_tree", return_value=[disk]):
            with self.assertRaisesRegex(RuntimeError, "LUKS/LVM/RAID/swap"):
                worker.inspect_target_layout("/dev/sdb")

    def test_target_with_active_swap_signature_is_rejected(self):
        disk = {"type": "disk", "path": "/dev/sdb", "children": [
            {"type": "part", "path": "/dev/sdb1", "fstype": "swap", "label": "swap"}
        ]}
        with patch("worker.lsblk_tree", return_value=[disk]):
            with self.assertRaisesRegex(RuntimeError, "swap"):
                worker.inspect_target_layout("/dev/sdb")

    def test_cancel_event_raises_only_at_explicit_safe_point(self):
        worker.CANCEL_EVENT.set()
        try:
            with self.assertRaises(worker.OperationCancelled):
                worker.check_cancelled()
        finally:
            worker.CANCEL_EVENT.clear()

    def test_copy_stops_before_creating_destination_when_cancelled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            (source / "boot.wim").write_bytes(b"payload")
            with patch("worker.check_cancelled", side_effect=worker.OperationCancelled("cancel")):
                with self.assertRaises(worker.OperationCancelled):
                    worker.copy_tree_progress(source, destination, 7, hash_files=False)
            self.assertFalse((destination / "boot.wim").exists())

    def test_root_worker_rejects_uninstalled_checkout_path(self):
        with patch.object(Path, "resolve", return_value=Path("/home/test/checkout/worker.py")):
            with self.assertRaisesRegex(RuntimeError, "Forráskönyvtárból"):
                worker.validate_privileged_install()


class StabilityRegressionTests(unittest.TestCase):
    def test_model_identity_comparison_collapses_whitespace(self):
        identity = {
            "size": 1024,
            "maj_min": "8:16",
            "model": "  USB   Flash  ",
            "serial": "ABC123",
            "wwn": "",
            "tran": "usb",
            "diskseq": "41",
            "by_id": "",
        }
        worker.compare_device_identity(identity, dict(identity, model="USB Flash"))

    def test_empty_model_is_not_fabricated_into_a_mismatch(self):
        identity = {
            "size": 1024,
            "maj_min": "8:16",
            "model": "   ",
            "serial": "ABC123",
            "wwn": "",
            "tran": "usb",
            "diskseq": "41",
            "by_id": "",
        }
        worker.compare_device_identity(identity, dict(identity, model="Generic USB"))

    def test_btrfs_source_subvolume_suffix_resolves_to_the_real_block_device(self):
        block_stat = type("BlockStat", (), {"st_mode": stat.S_IFBLK})()
        with patch(
            "worker._source_mounts_for_path",
            return_value=[("259:2", "/mnt/data", "btrfs", "/dev/nvme0n1p2[/@]")],
        ), patch(
            "worker.os.stat", return_value=block_stat
        ), patch(
            "worker._btrfs_member_devices", return_value=["/dev/nvme0n1p2"]
        ), patch(
            "worker._block_ancestor_majmins", return_value={"259:2", "259:0"}
        ) as resolve:
            self.assertEqual(
                worker.source_backing_majmins(Path("/mnt/data/image.iso")),
                {"259:2", "259:0"},
            )
        resolve.assert_called_once_with("/dev/nvme0n1p2")

    def test_source_backing_resolution_fails_closed_when_mountinfo_has_no_source(self):
        with patch(
            "worker._source_mounts_for_path",
            side_effect=RuntimeError("Nem található csatolási bejegyzés a forrásfájlhoz."),
        ):
            with self.assertRaisesRegex(RuntimeError, "csatolási bejegyzés"):
                worker.source_backing_majmins(Path("/mnt/data/image.iso"))

    def test_source_backing_resolution_fails_closed_for_overlay_filesystem(self):
        with patch(
            "worker._source_mounts_for_path",
            return_value=[("0:42", "/mnt/data", "overlay", "overlay")],
        ):
            with self.assertRaisesRegex(RuntimeError, "háttértára nem igazolható"):
                worker.source_backing_majmins(Path("/mnt/data/image.iso"))

    def test_rejected_filesystem_message_names_type_source_and_remedy(self):
        with patch(
            "worker._source_mounts_for_path",
            return_value=[("0:42", "/mnt/pool", "zfs", "tank/data")],
        ):
            with self.assertRaises(RuntimeError) as caught:
                worker.source_backing_majmins(Path("/mnt/pool/image.iso"))
        message = str(caught.exception)
        self.assertIn("típus: zfs", message)
        self.assertIn("forrás: tank/data", message)
        self.assertIn(
            "Másold az ISO-t helyi, blokkeszközön lévő lemezre (például a saját mappádba), "
            "majd válaszd ki újra.",
            message,
        )

    def test_unknown_and_generic_fuse_filesystems_stay_rejected(self):
        for filesystem_type, source in (
            ("overlay", "overlay"),
            ("zfs", "tank/data"),
            ("fuse", "some-fuse-daemon"),
            ("fuse.mergerfs", "a:b"),
            ("ecryptfs", "/home/.ecryptfs/user/.Private"),
            ("brandnewfs", "none"),
        ):
            with self.subTest(filesystem_type=filesystem_type), patch(
                "worker._source_mounts_for_path",
                return_value=[("0:42", "/mnt/data", filesystem_type, source)],
            ):
                with self.assertRaisesRegex(RuntimeError, "háttértára nem igazolható"):
                    worker.source_backing_majmins(Path("/mnt/data/image.iso"))

    def test_network_and_virtual_filesystems_are_allowed_without_block_backing(self):
        for filesystem_type, source in (
            ("virtiofs", "hostshare"),
            ("vboxsf", "Downloads"),
            ("fuse.sshfs", "user@host:/srv/iso"),
            ("fuse.rclone", "remote:iso"),
            ("fuse.gvfsd-fuse", "gvfsd-fuse"),
            ("fuse.portal", "portal"),
        ):
            with self.subTest(filesystem_type=filesystem_type), patch(
                "worker._source_mounts_for_path",
                return_value=[("0:42", "/mnt/data", filesystem_type, source)],
            ), patch("worker._block_ancestor_majmins") as resolve:
                self.assertEqual(
                    worker.source_backing_majmins(Path("/mnt/data/image.iso")),
                    set(),
                )
                resolve.assert_not_called()

    def test_fuseblk_source_is_resolved_to_its_block_device(self):
        block_stat = type("BlockStat", (), {"st_mode": stat.S_IFBLK})()
        with patch(
            "worker._source_mounts_for_path",
            return_value=[("8:17", "/mnt/win", "fuseblk", "/dev/sdb1")],
        ), patch("worker.os.stat", return_value=block_stat), patch(
            "worker._block_ancestor_majmins", return_value={"8:17", "8:16"}
        ) as resolve:
            self.assertEqual(
                worker.source_backing_majmins(Path("/mnt/win/image.iso")),
                {"8:17", "8:16"},
            )
        resolve.assert_called_once_with("/dev/sdb1")

    def test_fuseblk_source_on_target_disk_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image.iso"
            image.write_bytes(b"iso")
            block_stat = type("BlockStat", (), {"st_mode": stat.S_IFBLK})()
            with patch(
                "worker._source_mounts_for_path",
                return_value=[("8:17", temp, "fuseblk", "/dev/sdb1")],
            ), patch("worker.os.stat", side_effect=fake_dev_stat(block_stat)), patch(
                "worker._block_ancestor_majmins", return_value={"8:17", "8:16"}
            ), patch(
                "worker.device_identity", return_value={"maj_min": "8:16"}
            ):
                with self.assertRaisesRegex(RuntimeError, "célmeghajtó egyik kötetén"):
                    worker.ensure_source_not_on_target(image, "/dev/sdb")

    def test_known_tmpfs_source_is_allowed_without_block_device_backing(self):
        with patch(
            "worker._source_mounts_for_path",
            return_value=[("0:42", "/run", "tmpfs", "tmpfs")],
        ):
            self.assertEqual(
                worker.source_backing_majmins(Path("/run/image.iso")),
                set(),
            )

    def test_autofs_and_cifs_overmount_stack_is_allowed(self):
        with patch(
            "worker._source_mounts_for_path",
            return_value=[
                ("0:46", "/mnt/smb/Kozos", "autofs", "systemd-1"),
                ("0:107", "/mnt/smb/Kozos", "cifs", "//10.0.0.5/Kozos"),
            ],
        ):
            self.assertEqual(
                worker.source_backing_majmins(Path("/mnt/smb/Kozos/image.iso")),
                set(),
            )

    def test_autofs_without_visible_backing_filesystem_fails_closed(self):
        with patch(
            "worker._source_mounts_for_path",
            return_value=[("0:46", "/mnt/smb/Kozos", "autofs", "systemd-1")],
        ):
            with self.assertRaisesRegex(RuntimeError, "autofs"):
                worker.source_backing_majmins(Path("/mnt/smb/Kozos/image.iso"))

    def test_source_mount_lookup_keeps_all_layers_at_the_deepest_mountpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image.iso"
            image.write_bytes(b"image")
            records = [
                ("8:1", "/", "ext4", "/dev/sda1"),
                ("0:46", temp, "autofs", "systemd-1"),
                ("0:107", temp, "cifs", "//10.0.0.5/Kozos"),
                ("0:43", "/proc", "proc", "proc"),
            ]
            with patch("worker._read_mountinfo_records", return_value=records):
                self.assertEqual(
                    worker._source_mounts_for_path(image),
                    [
                        ("0:46", temp, "autofs", "systemd-1"),
                        ("0:107", temp, "cifs", "//10.0.0.5/Kozos"),
                    ],
                )

    def test_source_backing_resolution_fails_closed_when_block_device_is_missing(self):
        with patch(
            "worker._source_mounts_for_path",
            return_value=[("259:2", "/mnt/data", "btrfs", "/dev/does-not-exist[/@]")],
        ), patch(
            "worker.os.stat", side_effect=FileNotFoundError("missing")
        ):
            with self.assertRaisesRegex(RuntimeError, "nem érhető el"):
                worker.source_backing_majmins(Path("/mnt/data/image.iso"))

    def test_mountinfo_detects_a_filesystem_mounted_on_the_whole_disk(self):
        disk = {"type": "disk", "path": "/dev/sdb", "maj:min": "8:16"}
        with patch(
            "worker.inspect_target_layout", return_value=(disk, [disk])
        ), patch(
            "worker._read_mountinfo", return_value=[("8:16", "/media/superfloppy")]
        ), patch(
            "worker.command",
            return_value=subprocess.CompletedProcess(["findmnt"], 1, "", ""),
        ):
            self.assertEqual(
                worker._disk_mount_targets("/dev/sdb"),
                {"/media/superfloppy"},
            )

    def test_mountinfo_mountpoint_escape_sequences_are_decoded(self):
        self.assertEqual(
            worker._decode_mountinfo_field("/media/USB\\040Drive"),
            "/media/USB Drive",
        )

    def test_unmount_disk_includes_mounts_on_the_whole_disk(self):
        with patch(
            "worker._disk_mount_targets",
            side_effect=[{"/media/superfloppy"}, set()],
        ), patch("worker.command") as run, patch("worker.emit"):
            worker.unmount_disk("/dev/sdb")
        self.assertIn(
            (["umount", "--", "/media/superfloppy"],),
            [call.args for call in run.call_args_list],
        )

    def test_assert_disk_unmounted_rejects_a_remaining_mount(self):
        with patch(
            "worker._disk_mount_targets", return_value={"/media/superfloppy"}
        ):
            with self.assertRaisesRegex(RuntimeError, "még csatolva"):
                worker.assert_disk_unmounted("/dev/sdb")

    def test_emit_reports_a_closed_stdout_pipe_without_raising(self):
        old_broken = worker.OUTPUT_BROKEN
        worker.OUTPUT_BROKEN = False
        try:
            with patch("builtins.print", side_effect=BrokenPipeError()):
                self.assertFalse(worker.emit("test"))
            self.assertTrue(worker.OUTPUT_BROKEN)
        finally:
            worker.OUTPUT_BROKEN = old_broken

    def test_emit_handles_other_stdout_os_errors_without_raising(self):
        old_broken = worker.OUTPUT_BROKEN
        worker.OUTPUT_BROKEN = False
        try:
            with patch("builtins.print", side_effect=OSError("closed")):
                self.assertFalse(worker.emit("test"))
            self.assertTrue(worker.OUTPUT_BROKEN)
        finally:
            worker.OUTPUT_BROKEN = old_broken

    def test_uefi_helper_flushes_partition_before_readback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "helper.img"
            partition = root / "partition.img"
            image.write_bytes(b"BMK helper image")
            partition.write_bytes(b"\0" * image.stat().st_size)
            responses = [
                subprocess.CompletedProcess(["blockdev"], 0, f"{image.stat().st_size}\n", ""),
                subprocess.CompletedProcess(["blockdev"], 0, "", ""),
                subprocess.CompletedProcess(["fatlabel"], 0, "BMK_EFI\n", ""),
            ]
            with patch.object(
                worker, "UEFI_NTFS_IMAGE_SIZE", image.stat().st_size
            ), patch("worker.command", side_effect=responses) as run, patch("worker.emit"):
                worker.write_uefi_ntfs_image(image, str(partition))
            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn(["blockdev", "--flushbufs", str(partition)], commands)
            self.assertLess(
                commands.index(["blockdev", "--flushbufs", str(partition)]),
                commands.index(["fatlabel", str(partition)]),
            )
            self.assertEqual(partition.read_bytes(), image.read_bytes())

    def test_uefi_helper_cancellation_does_not_call_fsync(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "helper.img"
            partition = root / "partition.img"
            image.write_bytes(b"BMK")
            partition.write_bytes(b"\0" * 3)
            with patch.object(worker, "UEFI_NTFS_IMAGE_SIZE", 3), patch(
                "worker.command",
                return_value=subprocess.CompletedProcess(["blockdev"], 0, "3\n", ""),
            ), patch(
                "worker.check_cancelled",
                side_effect=worker.OperationCancelled("cancel"),
            ), patch("worker.os.fsync") as fsync, patch("worker.emit"):
                with self.assertRaises(worker.OperationCancelled):
                    worker.write_uefi_ntfs_image(image, str(partition))
            fsync.assert_not_called()



class BtrfsMultiDeviceTests(unittest.TestCase):
    UUID = "0f2e4a8c-1111-2222-3333-444455556666"

    def make_sysfs(self, root: Path, members: dict[str, str], uuid: str | None = None) -> None:
        devices = root / (uuid or self.UUID) / "devices"
        devices.mkdir(parents=True)
        for name, maj_min in members.items():
            (devices / name).mkdir()
            (devices / name / "dev").write_text(maj_min + "\n", encoding="ascii")

    def block_stat(self, major: int, minor: int):
        return type(
            "BlockStat", (), {"st_mode": stat.S_IFBLK, "st_rdev": os.makedev(major, minor)}
        )()

    def run_backing(self, sysfs: Path, ancestors: dict[str, set[str]]):
        with patch.object(worker, "BTRFS_SYSFS_ROOT", sysfs), patch(
            "worker._source_mounts_for_path",
            return_value=[("0:30", "/mnt/pool", "btrfs", "/dev/sda1[/@data]")],
        ), patch("worker.os.stat", return_value=self.block_stat(8, 1)), patch(
            "worker.os.path.exists", return_value=True
        ), patch(
            "worker._block_ancestor_majmins",
            side_effect=lambda path: ancestors.get(path, set()),
        ):
            return worker.source_backing_majmins(Path("/mnt/pool/image.iso"))

    def test_every_member_of_a_two_device_btrfs_is_added_to_the_backing_set(self):
        with tempfile.TemporaryDirectory() as temp:
            sysfs = Path(temp)
            # An unrelated filesystem must not be confused with the source.
            self.make_sysfs(sysfs, {"nvme0n1p2": "259:2"}, "aaaaaaaa-0000-0000-0000-000000000000")
            self.make_sysfs(sysfs, {"sda1": "8:1", "sdb1": "8:17"})
            (sysfs / "features").mkdir()
            backing = self.run_backing(
                sysfs,
                {"/dev/sda1": {"8:1", "8:0"}, "/dev/sdb1": {"8:17", "8:16"}},
            )
        self.assertEqual(backing, {"8:1", "8:0", "8:17", "8:16"})

    def test_two_device_btrfs_with_a_member_on_the_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            sysfs = Path(temp) / "sysfs"
            self.make_sysfs(sysfs, {"sda1": "8:1", "sdb1": "8:17"})
            image = Path(temp) / "image.iso"
            image.write_bytes(b"iso")
            with patch.object(worker, "BTRFS_SYSFS_ROOT", sysfs), patch(
                "worker._source_mounts_for_path",
                # mountinfo names only the member that is NOT on the target.
                return_value=[("0:30", temp, "btrfs", "/dev/sda1[/@data]")],
            ), patch(
                "worker.os.stat", side_effect=fake_dev_stat(self.block_stat(8, 1))
            ), patch(
                "worker.os.path.exists", return_value=True
            ), patch(
                "worker._block_ancestor_majmins",
                side_effect=lambda path: {
                    "/dev/sda1": {"8:1", "8:0"},
                    "/dev/sdb1": {"8:17", "8:16"},
                    "/dev/sdb": {"8:16"},
                }[path],
            ), patch(
                "worker.device_identity", return_value={"maj_min": "8:16"}
            ):
                with self.assertRaisesRegex(RuntimeError, "célmeghajtó egyik kötetén"):
                    worker.ensure_source_not_on_target(image, "/dev/sdb")

    def test_single_device_btrfs_still_resolves(self):
        with tempfile.TemporaryDirectory() as temp:
            sysfs = Path(temp)
            self.make_sysfs(sysfs, {"sda1": "8:1"})
            backing = self.run_backing(sysfs, {"/dev/sda1": {"8:1", "8:0"}})
        self.assertEqual(backing, {"8:1", "8:0"})

    def test_unreadable_member_list_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "no-sysfs"
            with self.assertRaisesRegex(RuntimeError, "tagjainak listája nem olvasható"):
                self.run_backing(missing, {"/dev/sda1": {"8:1", "8:0"}})

    def test_filesystem_not_listed_in_sysfs_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            sysfs = Path(temp)
            self.make_sysfs(sysfs, {"nvme0n1p2": "259:2"})
            with self.assertRaisesRegex(RuntimeError, "tagjainak listája nem olvasható"):
                self.run_backing(sysfs, {"/dev/sda1": {"8:1", "8:0"}})

    def test_member_without_readable_device_number_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            sysfs = Path(temp)
            self.make_sysfs(sysfs, {"sda1": "8:1", "sdb1": "garbage"})
            with self.assertRaisesRegex(RuntimeError, "tagjainak listája nem olvasható"):
                self.run_backing(sysfs, {"/dev/sda1": {"8:1", "8:0"}})

    def test_member_whose_physical_disk_cannot_be_resolved_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            sysfs = Path(temp)
            self.make_sysfs(sysfs, {"sda1": "8:1", "sdb1": "8:17"})
            with self.assertRaisesRegex(RuntimeError, "fizikai meghajtója nem oldható fel"):
                self.run_backing(sysfs, {"/dev/sda1": {"8:1", "8:0"}})


class IsoVolumeLabelTests(unittest.TestCase):
    def test_normalize_iso_label_preserves_valid_name(self):
        self.assertEqual(worker.normalize_iso_volume_label("ESD ISO"), "ESD ISO")
        self.assertEqual(worker.normalize_iso_volume_label("x86-64"), "x86-64")

    def test_normalize_iso_label_replaces_control_and_forbidden_characters(self):
        self.assertEqual(
            worker.normalize_iso_volume_label('  X64:"WIN"/USB?  '),
            "X64__WIN__USB_",
        )

    def test_normalize_iso_label_truncates_to_gpt_name_limit(self):
        self.assertEqual(worker.normalize_iso_volume_label("X" * 50), "X" * 36)

    def test_missing_iso_label_uses_safe_fallback(self):
        self.assertEqual(worker.normalize_iso_volume_label("   "), "BOOTMEDIA")

    def test_read_iso_label_prefers_blkid_volume_id(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "windows.iso"
            image.write_bytes(b"test")
            response = subprocess.CompletedProcess(
                ["blkid"], 0, stdout="WIN10_IOT_X64\n", stderr=""
            )
            with patch("worker.command", return_value=response) as command:
                self.assertEqual(worker.read_iso_volume_label(image), "WIN10_IOT_X64")
            command.assert_called_once()
            self.assertIn("blkid", command.call_args.args[0])

    def test_read_iso_label_falls_back_to_7zip_volume_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "windows.iso"
            image.write_bytes(b"test")
            no_label = subprocess.CompletedProcess(
                ["blkid"], 2, stdout="", stderr="no label"
            )
            seven_zip = subprocess.CompletedProcess(
                ["7z"], 0, stdout="Path = windows.iso\nType = Iso\nVolume = ESD_ISO\n", stderr=""
            )
            with patch("worker.command", side_effect=[no_label, seven_zip]):
                self.assertEqual(worker.read_iso_volume_label(image), "ESD_ISO")

    def test_gpt_first_partition_name_uses_original_iso_label(self):
        layout = worker.calculate_gpt_layout((16 * 1024 * 1024 * 1024) // 512)
        script = worker.make_sfdisk_script(layout, "WIN10_IOT_X64")
        self.assertIn('name="WIN10_IOT_X64"', script)
        self.assertIn('name="BMK_EFI"', script)
        self.assertNotIn('name="BOOTMEDIA"', script)


class UefiNtfsLayoutTests(unittest.TestCase):
    def test_gpt_layout_reserves_exact_one_mib_efi_partition_at_end(self):
        sectors = (32 * 1024 * 1024 * 1024) // 512
        layout = worker.calculate_gpt_layout(sectors)
        self.assertEqual(layout["second_size"], 2048)
        self.assertEqual(layout["second_bytes"], 1024 * 1024)
        self.assertEqual(layout["first_start"], 2048)
        self.assertEqual(layout["second_start"] % 2048, 0)
        self.assertEqual(
            layout["first_start"] + layout["first_size"],
            layout["second_start"],
        )
        self.assertLessEqual(
            layout["second_start"] + layout["second_size"] - 1,
            sectors - worker.GPT_RESERVED_SECTORS,
        )

    def test_too_small_drive_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "túl kicsi"):
            worker.calculate_gpt_layout(4096)

    @unittest.skipUnless(shutil.which("sfdisk"), "sfdisk/util-linux is not available")
    def test_sfdisk_accepts_generated_gpt_script_on_sparse_image(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "disk.img"
            disk_bytes = 8 * 1024 * 1024 * 1024
            with image.open("wb") as stream:
                stream.truncate(disk_bytes)
            layout = worker.calculate_gpt_layout(disk_bytes // 512)
            result = subprocess.run(
                ["sfdisk", "--no-act", "--wipe", "never", str(image)],
                input=worker.make_sfdisk_script(layout),
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("sfdisk"), "sfdisk/util-linux is not available")
    def test_sfdisk_writes_and_reads_back_rufus_compatible_helper_attributes(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "disk.img"
            disk_bytes = 8 * 1024 * 1024 * 1024
            with image.open("wb") as stream:
                stream.truncate(disk_bytes)
            layout = worker.calculate_gpt_layout(disk_bytes // 512)
            iso_label = "WIN10_IOT_X64"
            result = subprocess.run(
                ["sfdisk", "--wipe", "always", str(image)],
                input=worker.make_sfdisk_script(layout, iso_label),
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

            # Run the same post-write validation that the USB worker executes,
            # but only against a temporary sparse image file, never a device.
            worker.verify_gpt_layout(str(image), layout, iso_label)

    def test_sfdisk_script_uses_basic_data_and_no_drive_letter_for_both_partitions(self):
        layout = worker.calculate_gpt_layout((16 * 1024 * 1024 * 1024) // 512)
        script = worker.make_sfdisk_script(layout)
        self.assertIn("label: gpt", script)
        self.assertEqual(script.count(f"type={worker.GPT_BASIC_DATA_GUID}"), 2)
        self.assertIn(f"attrs={worker.GPT_NO_DRIVE_LETTER_ATTR}", script)
        self.assertNotIn("C12A7328-F81F-11D2-BA4B-00A0C93EC93B", script)
        self.assertIn('name="BOOTMEDIA"', script)
        self.assertIn('name="BMK_EFI"', script)

    def test_partition_path_handles_sd_and_nvme_names(self):
        self.assertEqual(worker.partition_path("/dev/sdb", 1), "/dev/sdb1")
        self.assertEqual(worker.partition_path("/dev/nvme1n1", 2), "/dev/nvme1n1p2")
        self.assertEqual(
            worker.partition_path("/dev/disk/by-id/usb-SanDisk_Ultra_1234", 2),
            "/dev/disk/by-id/usb-SanDisk_Ultra_1234-part2",
        )

    def test_git_blob_sha1_matches_git_object_format(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.bin"
            payload = b"BootMediaKit"
            path.write_bytes(payload)
            expected = hashlib.sha1(b"blob 12\0" + payload).hexdigest()
            self.assertEqual(worker.git_blob_sha1(path), expected)



class RawWriteRegressionTests(unittest.TestCase):
    def test_raw_write_forces_stale_partition_table_signature_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "linux.iso"
            device = root / "usb-device"
            payload = bytes(range(256)) * 128
            trailing_data = bytes([0xA5]) * 4096
            image.write_bytes(payload)
            device.write_bytes(bytes([0x5A]) * len(payload) + trailing_data)
            commands = []

            def fake_command(args, **kwargs):
                commands.append(list(args))
                return subprocess.CompletedProcess(args, 0, "", "")

            with patch.object(worker, "TARGET_MODIFIED", False), patch.object(
                worker, "ensure_source_not_on_target"
            ), patch.object(
                worker, "validate_target", return_value=device.stat().st_size
            ), patch.object(
                worker, "require_programs"
            ), patch.object(
                worker, "unmount_disk"
            ), patch.object(
                worker, "assert_disk_unmounted"
            ) as assert_unmounted, patch.object(
                worker, "command", side_effect=fake_command
            ), patch.object(
                worker, "emit"
            ):
                worker.write_raw(image, str(device), True, expected_identity={})

            self.assertEqual(device.read_bytes()[:len(payload)], payload)
            self.assertEqual(device.read_bytes()[len(payload):], trailing_data)
            self.assertIn(
                ["wipefs", "--all", "--force", str(device)],
                commands,
            )
            assert_unmounted.assert_called_once_with(str(device))
            self.assertLess(
                commands.index(["wipefs", "--all", "--force", str(device)]),
                commands.index(["sync"]),
            )


class GuiPipeBrokenTests(unittest.TestCase):
    """The GUI closes or crashes mid-write: stdout becomes a broken pipe."""

    def setUp(self):
        for name in ("TARGET_MODIFIED", "OUTPUT_BROKEN"):
            patcher = patch.object(worker, name, False)
            patcher.start()
            self.addCleanup(patcher.stop)
        worker.CANCEL_EVENT.clear()

    @staticmethod
    def pipe_breaks_once_target_is_modified(*args, **kwargs):
        if worker.TARGET_MODIFIED:
            raise BrokenPipeError()

    def test_windows_writer_stops_at_next_safe_point_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "windows.iso"
            image.write_bytes(b"ISO")
            temp_root = root / "bootmediakit-run"
            commands = []

            def fake_mkdtemp(**kwargs):
                temp_root.mkdir()
                return str(temp_root)

            def fake_command(args, **kwargs):
                commands.append(list(args))
                stdout = ""
                if args[:2] == ["blockdev", "--getss"]:
                    stdout = "512\n"
                elif args[:2] == ["blockdev", "--getsz"]:
                    stdout = f"{16 * 1024**3 // 512}\n"
                return subprocess.CompletedProcess(args, 0, stdout, "")

            def fake_mount_iso(_image, mountpoint):
                mountpoint.mkdir(parents=True)

            iso_mount = temp_root / "iso"
            with patch("worker.require_programs"), patch(
                "worker.ensure_source_not_on_target"
            ), patch("worker.validate_target", return_value=16 * 1024**3), patch(
                "worker.verify_uefi_ntfs_image"
            ), patch("worker.tempfile.mkdtemp", side_effect=fake_mkdtemp), patch(
                "worker.mount_iso", side_effect=fake_mount_iso
            ), patch(
                "worker.scan_windows_iso",
                return_value=(iso_mount / "sources/install.wim", iso_mount / "sources/boot.wim", 4096),
            ), patch("worker.read_iso_volume_label", return_value="WIN_TEST"), patch(
                "worker.prepare_bmk_uefi_ntfs_image", return_value=temp_root / "helper.img"
            ), patch("worker.unmount_disk") as unmount_disk, patch(
                "worker.assert_disk_unmounted"
            ), patch("worker.verify_gpt_layout"), patch(
                "worker.command", side_effect=fake_command
            ), patch(
                "builtins.print", side_effect=self.pipe_breaks_once_target_is_modified
            ):
                with self.assertRaisesRegex(
                    worker.OperationCancelled, "megszakadt a kapcsolat"
                ):
                    worker.write_windows_uefi(image, "/dev/sdz", False, expected_identity={})
                self.assertTrue(worker.TARGET_MODIFIED)
                self.assertTrue(worker.OUTPUT_BROKEN)

            # The destructive boundary was crossed, with the mandatory --force.
            self.assertIn(["wipefs", "--all", "--force", "/dev/sdz"], commands)
            # ...but the writer stopped before formatting anything.
            self.assertFalse(any(args[0] == "mkfs.ntfs" for args in commands))
            self.assertFalse(any(args[0] == "mount" for args in commands))
            # Cleanup: ISO unmounted, target unmounted again, temp dir removed.
            self.assertIn(["umount", "--", str(iso_mount)], commands)
            self.assertGreaterEqual(unmount_disk.call_count, 2)
            self.assertEqual(unmount_disk.call_args.args, ("/dev/sdz",))
            self.assertFalse(temp_root.exists())

    def test_raw_writer_stops_at_next_safe_point_without_fsync(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "linux.iso"
            device = root / "usb-device"
            chunk = 4096
            payload = bytes(range(256)) * (8 * chunk // 256)
            image.write_bytes(payload)
            device.write_bytes(bytes([0x5A]) * len(payload))
            commands = []

            def fake_command(args, **kwargs):
                commands.append(list(args))
                return subprocess.CompletedProcess(args, 0, "", "")

            def pipe_breaks_on_first_progress_event(text, *args, **kwargs):
                if "Lemezkép kiírása… " in json.loads(text)["message"]:
                    raise BrokenPipeError()

            with patch.object(worker, "CHUNK", chunk), patch(
                "worker.ensure_source_not_on_target"
            ), patch(
                "worker.validate_target", return_value=device.stat().st_size
            ), patch("worker.require_programs"), patch("worker.unmount_disk"), patch(
                "worker.assert_disk_unmounted"
            ), patch("worker.command", side_effect=fake_command), patch(
                "worker.os.fsync"
            ) as fsync, patch(
                "builtins.print", side_effect=pipe_breaks_on_first_progress_event
            ):
                with self.assertRaisesRegex(
                    worker.OperationCancelled, "megszakadt a kapcsolat"
                ):
                    worker.write_raw(image, str(device), True, expected_identity={})
                self.assertTrue(worker.TARGET_MODIFIED)
                self.assertTrue(worker.OUTPUT_BROKEN)

            fsync.assert_not_called()
            written = device.read_bytes()
            self.assertEqual(written[:chunk], payload[:chunk])
            self.assertEqual(written[chunk:], bytes([0x5A]) * (len(payload) - chunk))
            self.assertIn(["wipefs", "--all", "--force", str(device)], commands)
            # Nothing after the write loop ran: no final sync, no read-back, no rereadpt.
            self.assertEqual(commands.count(["sync"]), 1)
            self.assertFalse(any(args[0] == "blockdev" for args in commands))

    def test_main_reports_partial_target_on_stderr_and_exits_130(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "linux.iso"
            image.write_bytes(b"ISO test")

            def writer_loses_the_gui(*args, **kwargs):
                worker.TARGET_MODIFIED = True
                worker.emit("progress")
                worker.check_cancelled()

            with patch("worker.os.geteuid", return_value=0), patch(
                "worker.validate_privileged_install"
            ), patch("worker.start_control_reader"), patch(
                "worker.write_raw", side_effect=writer_loses_the_gui
            ), patch(
                "builtins.print", side_effect=self.pipe_breaks_once_target_is_modified
            ), patch("worker._write_stderr_safely") as stderr:
                result = worker.main(
                    ["bootmediakit-worker", "raw", str(image), "/dev/sdz", "0", "{}"]
                )
        self.assertEqual(result, 130)
        stderr.assert_called_once()
        self.assertIn("megszakadt a kapcsolat", stderr.call_args.args[0])
        self.assertIn("részleges állapotban maradhat", stderr.call_args.args[0])


class ProgressCalculationTests(unittest.TestCase):
    def test_windows_copy_progress_uses_full_range_without_sha256(self):
        self.assertEqual(worker.windows_copy_progress_span(False), 54)
        self.assertEqual(42 + worker.windows_copy_progress_span(False), 96)

    def test_windows_copy_progress_reserves_range_for_sha256(self):
        self.assertEqual(worker.windows_copy_progress_span(True), 43)
        self.assertEqual(42 + worker.windows_copy_progress_span(True), 85)


class CopyVerificationTests(unittest.TestCase):
    def test_copy_creates_manifest_and_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            (source / "boot.wim").write_bytes(b"windows setup boot image")
            (source / "nested").mkdir()
            (source / "nested" / "install.esd").write_bytes(b"windows install image")
            total = sum(p.stat().st_size for p in source.rglob("*") if p.is_file())

            manifest = worker.copy_tree_progress(source, destination, total)
            self.assertEqual(len(manifest), 2)
            self.assertTrue((destination / "boot.wim").is_file())
            self.assertTrue((destination / "nested" / "install.esd").is_file())
            worker.verify_copied_files(destination, manifest)

    def test_copy_without_hash_skips_manifest_and_per_file_fsync(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            (source / "boot.wim").write_bytes(b"boot payload")
            total = (source / "boot.wim").stat().st_size

            with patch("worker.os.fsync") as fsync:
                manifest = worker.copy_tree_progress(
                    source, destination, total, hash_files=False
                )

            self.assertEqual(manifest, [])
            self.assertEqual((destination / "boot.wim").read_bytes(), b"boot payload")
            fsync.assert_not_called()

    def test_copy_verification_detects_changed_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "destination"
            destination.mkdir()
            target = destination / "boot.wim"
            target.write_bytes(b"changed")
            expected = hashlib.sha256(b"original").hexdigest()
            manifest = [("boot.wim", len(b"original"), expected)]
            with self.assertRaisesRegex(RuntimeError, "mérethiba|SHA-256"):
                worker.verify_copied_files(destination, manifest)


class NtfsMountTests(unittest.TestCase):
    def test_ntfs3_driver_is_preferred(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("worker.command") as run:
                driver = worker.mount_ntfs_volume("/dev/fake1", Path(temp))
            self.assertEqual(driver, "ntfs3")
            self.assertEqual(run.call_args.args[0][:3], ["mount", "-t", "ntfs3"])
            self.assertEqual(run.call_count, 1)

    def test_ntfs3_falls_back_to_ntfs3g_when_kernel_driver_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch(
                "worker.command",
                side_effect=[RuntimeError("unknown filesystem type ntfs3"), subprocess.CompletedProcess([], 0, "", "")],
            ) as run, patch("worker.shutil.which", return_value="/usr/bin/ntfs-3g"):
                driver = worker.mount_ntfs_volume("/dev/fake1", Path(temp))
            self.assertEqual(driver, "ntfs-3g")
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[0].args[0][:3], ["mount", "-t", "ntfs3"])
            self.assertEqual(run.call_args_list[1].args[0][:3], ["mount", "-t", "ntfs-3g"])


class MbrLayoutTests(unittest.TestCase):
    """MBR layout for the Legacy BIOS mode (0.3.0 T2)."""

    MIB_SECTORS = 2048

    def test_layout_is_one_partition_from_1_mib_aligned_to_1_mib(self):
        total = 64 * self.MIB_SECTORS
        layout = worker.calculate_mbr_layout(total)
        self.assertEqual(layout, {"start": 2048, "size": total - 2048, "bytes": (total - 2048) * 512})

    def test_unaligned_disk_end_is_rounded_down_to_1_mib(self):
        layout = worker.calculate_mbr_layout(64 * self.MIB_SECTORS + 1000)
        self.assertEqual(layout["size"], 63 * self.MIB_SECTORS)
        self.assertEqual(layout["size"] % self.MIB_SECTORS, 0)

    def test_largest_dos_label_disk_is_accepted_and_fits_32_bit_lba(self):
        # util-linux limit: at most 2**32 - 1 sectors for a DOS label.
        layout = worker.calculate_mbr_layout(2**32 - 1)
        self.assertEqual(layout["size"], 2**32 - 4096)
        self.assertLessEqual(layout["start"] + layout["size"], 2**32 - 1)

    def test_2_tib_and_larger_is_rejected(self):
        for total in (2**32, 2**32 + 1, 3 * 2**31 * 2):
            with self.subTest(total=total), self.assertRaisesRegex(ValueError, "2 TiB"):
                worker.calculate_mbr_layout(total)

    def test_too_small_drive_is_rejected(self):
        for total in (2048, 4095):
            with self.subTest(total=total), self.assertRaisesRegex(ValueError, "túl kicsi"):
                worker.calculate_mbr_layout(total)
        with self.assertRaises(ValueError):
            worker.calculate_mbr_layout(0)

    def test_sfdisk_script_is_dos_with_one_active_type_7_partition(self):
        script = worker.make_mbr_sfdisk_script({"start": 2048, "size": 129024, "bytes": 0})
        self.assertEqual(
            script,
            "label: dos\nunit: sectors\nstart=2048, size=129024, type=7, bootable\n",
        )

    # -- verify_mbr_layout with mocked sfdisk --------------------------------

    LAYOUT = {"start": 2048, "size": 129024, "bytes": 129024 * 512}

    @staticmethod
    def sfdisk_json(label="dos", partitions=None) -> str:
        if partitions is None:
            partitions = [{"node": "/dev/sdx1", "start": 2048, "size": 129024, "type": "7", "bootable": True}]
        return json.dumps({"partitiontable": {"label": label, "unit": "sectors", "partitions": partitions}})

    def run_verify(self, stdout: str):
        responses = [
            subprocess.CompletedProcess(["sfdisk"], 0, "No errors detected.\n", ""),
            subprocess.CompletedProcess(["sfdisk"], 0, stdout, ""),
        ]
        with patch("worker.command", side_effect=responses) as run:
            worker.verify_mbr_layout("/dev/sdx", self.LAYOUT)
        return run

    def test_verify_accepts_the_planned_layout_after_sfdisk_verify(self):
        run = self.run_verify(self.sfdisk_json())
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [["sfdisk", "--verify", "/dev/sdx"], ["sfdisk", "--json", "/dev/sdx"]],
        )

    def test_verify_rejects_every_deviation(self):
        good = {"node": "/dev/sdx1", "start": 2048, "size": 129024, "type": "7", "bootable": True}
        cases = {
            "gpt label": (self.sfdisk_json(label="gpt"), "MBR elrendezést"),
            "two partitions": (self.sfdisk_json(partitions=[good, dict(good, start=200000)]), "MBR elrendezést"),
            "no partition": (self.sfdisk_json(partitions=[]), "MBR elrendezést"),
            "wrong start": (self.sfdisk_json(partitions=[dict(good, start=63)]), "eltér"),
            "wrong size": (self.sfdisk_json(partitions=[dict(good, size=2048)]), "eltér"),
            "linux type": (self.sfdisk_json(partitions=[dict(good, type="83")]), "típusa hibás"),
            "not active": (self.sfdisk_json(partitions=[dict(good, bootable=False)]), "aktívnak"),
            "no bootable field": (
                self.sfdisk_json(partitions=[{k: v for k, v in good.items() if k != "bootable"}]),
                "aktívnak",
            ),
            "invalid json": ("{", "visszaolvasni"),
        }
        for name, (stdout, pattern) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(RuntimeError, pattern):
                self.run_verify(stdout)

    def test_verify_stops_when_sfdisk_verify_fails(self):
        with patch("worker.command", side_effect=RuntimeError("sfdisk: bad table")) as run:
            with self.assertRaisesRegex(RuntimeError, "bad table"):
                worker.verify_mbr_layout("/dev/sdx", self.LAYOUT)
        self.assertEqual(run.call_count, 1)

    # -- real sfdisk on sparse image files -------------------------------------

    @unittest.skipUnless(shutil.which("sfdisk"), "sfdisk/util-linux is not available")
    def test_sfdisk_writes_and_verify_reads_back_generated_mbr_on_sparse_image(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "disk.img"
            disk_bytes = 8 * 1024 * 1024 * 1024 + 12345 * 512
            with image.open("wb") as stream:
                stream.truncate(disk_bytes)
            layout = worker.calculate_mbr_layout(disk_bytes // 512)
            result = subprocess.run(
                ["sfdisk", "--wipe", "always", str(image)],
                input=worker.make_mbr_sfdisk_script(layout),
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            worker.verify_mbr_layout(str(image), layout)
            with image.open("rb") as stream:
                mbr = stream.read(512)
            self.assertEqual(mbr[510:512], b"\x55\xaa")
            self.assertEqual(mbr[446], 0x80)
            self.assertEqual(mbr[450], 0x07)

    @unittest.skipUnless(shutil.which("sfdisk"), "sfdisk/util-linux is not available")
    def test_sfdisk_accepts_generated_mbr_script_on_largest_dos_label_sparse_image(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "disk.img"
            with image.open("wb") as stream:
                stream.truncate((2**32 - 1) * 512)
            layout = worker.calculate_mbr_layout(2**32 - 1)
            result = subprocess.run(
                ["sfdisk", "--no-act", "--wipe", "never", str(image)],
                input=worker.make_mbr_sfdisk_script(layout),
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("sfdisk"), "sfdisk/util-linux is not available")
    def test_sfdisk_warns_that_a_2_tib_image_exceeds_the_dos_label_limit(self):
        """Documents why calculate_mbr_layout rejects 2**32 sectors and more."""
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "disk.img"
            with image.open("wb") as stream:
                stream.truncate(2**32 * 512)
            result = subprocess.run(
                ["sfdisk", "--no-act", "--wipe", "never", str(image)],
                input="label: dos\nunit: sectors\nstart=2048, type=7, bootable\n",
                text=True,
                capture_output=True,
                timeout=30,
                env={**os.environ, "LC_ALL": "C"},
            )
            output = result.stdout + result.stderr
            self.assertIn("2199023255040", output, msg=output)

class BiosChainloaderTests(unittest.TestCase):
    """GRUB i386-pc chainloader installation (0.3.0 T3)."""

    DEVICE = "/dev/disk/by-id/usb-Test_Stick_0123-0:0"
    LAYOUT = {"start": 2048, "size": 129024, "bytes": 129024 * 512}
    GOOD_MBR = b"\xeb\x63\x90" + b"\x01" * 437 + bytes(70) + b"\x55\xaa"

    # -- grub_install_args -------------------------------------------------

    def test_args_are_bios_target_explicit_boot_directory_and_device_last(self):
        args = worker.grub_install_args(self.DEVICE, "/run/bootmediakit-abc/usb")
        self.assertEqual(
            args,
            ["grub-install", "--target=i386-pc", "--boot-directory=/run/bootmediakit-abc/usb", self.DEVICE],
        )
        joined = " ".join(args).lower()
        for forbidden in ("efi", "--force", "--removable", "efibootmgr", "--no-nvram"):
            self.assertNotIn(forbidden, joined)

    def test_args_reject_missing_or_invalid_device(self):
        for device in ("", "sdb", "dev/sdb", "/tmp/disk.img", "/dev/../tmp/x", None):
            with self.subTest(device=device), self.assertRaisesRegex(RuntimeError, "céleszköze"):
                worker.grub_install_args(device, "/run/bootmediakit-abc/usb")

    def test_args_reject_missing_or_relative_mountpoint(self):
        for mount in ("", "usb", "run/bootmediakit/usb", None):
            with self.subTest(mount=mount), self.assertRaisesRegex(RuntimeError, "abszolút"):
                worker.grub_install_args(self.DEVICE, mount)

    def test_args_reject_host_root_boot_and_efi_directories(self):
        for mount in ("/", "/boot", "/boot/", "/boot/grub", "/boot/efi", "/efi", "/efi/EFI",
                      "/run/../boot", "//boot"):
            with self.subTest(mount=mount), self.assertRaisesRegex(RuntimeError, "gép saját"):
                worker.grub_install_args(self.DEVICE, mount)

    def test_args_accept_lookalike_names_outside_host_boot_directories(self):
        for mount in ("/bootstrap/usb", "/run/boot", "/mnt/efi-copy", "/run/bootmediakit-x/usb"):
            with self.subTest(mount=mount):
                self.assertEqual(worker.grub_install_args(self.DEVICE, mount)[2], f"--boot-directory={mount}")

    # -- require_bios_grub ---------------------------------------------------

    def make_grub_dir(self, root: Path, skip: tuple[str, ...] = ()) -> Path:
        directory = root / "i386-pc"
        directory.mkdir()
        for name in worker.GRUB_PC_REQUIRED_FILES:
            if name not in skip:
                (directory / name).write_bytes(b"x")
        return directory

    def test_missing_grub_install_names_the_package(self):
        with patch("worker.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, r"sudo pacman -S grub"):
                worker.require_bios_grub()

    def test_missing_or_incomplete_i386_pc_directory_names_the_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incomplete = self.make_grub_dir(root, skip=("ntldr.mod",))
            for directory, detail in ((root / "absent", "nincs"), (incomplete, "ntldr.mod")):
                with self.subTest(detail=detail), patch.object(worker, "GRUB_PC_DIRECTORY", directory), patch(
                    "worker.shutil.which", return_value="/usr/bin/grub-install"
                ), self.assertRaisesRegex(RuntimeError, f"{detail}.*sudo pacman -S grub"):
                    worker.require_bios_grub()

    # -- install_bios_chainloader -------------------------------------------

    def run_install(self, *, command_effect=None, mbr=None, verify_effect=None, grub_files=None,
                    before=None):
        """Run install_bios_chainloader against a temp mountpoint with mocks.

        Returns (events, mountpoint, error). events records the order of
        identity check, grub-install and table verification.
        """
        events: list[str] = []
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        mountpoint = root / "usb"
        mountpoint.mkdir()
        grub_pc = self.make_grub_dir(root)
        files = ("ntfs.mod", "ntldr.mod", "normal.mod") if grub_files is None else grub_files

        def command(args, **kwargs):
            if args[0] == "grub-install":
                events.append("grub-install")
                self.assertEqual(kwargs.get("timeout"), worker.GRUB_INSTALL_TIMEOUT)
                modules = mountpoint / "grub" / "i386-pc"
                modules.mkdir(parents=True)
                for name in files:
                    (modules / name).write_bytes(b"mod")
                if command_effect:
                    command_effect()
            return subprocess.CompletedProcess(args, 0, "", "")

        def validate(device, identity):
            events.append("validate_target")
            return 1

        def verify(device, layout):
            events.append("verify_mbr_layout")
            if verify_effect:
                raise verify_effect

        error = None
        with patch.object(worker, "GRUB_PC_DIRECTORY", grub_pc), patch(
            "worker.shutil.which", return_value="/usr/bin/grub-install"
        ), patch("worker.assert_mount_is_partition", side_effect=lambda *a: events.append("mount_check")), patch(
            "worker.validate_target", side_effect=validate
        ), patch("worker.command", side_effect=command) as run, patch(
            "worker.read_mbr", return_value=self.GOOD_MBR if mbr is None else mbr
        ), patch("worker.verify_mbr_layout", side_effect=verify), patch("worker.emit"):
            if before:
                before()
            try:
                worker.install_bios_chainloader(self.DEVICE, mountpoint, {"serial": "x"}, self.LAYOUT)
            except Exception as exc:  # noqa: BLE001 - returned for assertions
                error = exc
            finally:
                worker.CANCEL_EVENT.clear()
        self.grub_install_calls = [call.args[0] for call in run.call_args_list if call.args[0][0] == "grub-install"]
        return events, mountpoint, error

    def test_install_runs_checks_then_grub_install_then_writes_config_and_verifies(self):
        events, mountpoint, error = self.run_install()
        self.assertIsNone(error)
        self.assertEqual(events, ["mount_check", "validate_target", "grub-install", "verify_mbr_layout"])
        self.assertEqual(
            self.grub_install_calls,
            [["grub-install", "--target=i386-pc", f"--boot-directory={mountpoint}", self.DEVICE]],
        )
        self.assertEqual((mountpoint / "grub" / "grub.cfg").read_text(encoding="ascii"), worker.BIOS_GRUB_CFG)

    def test_grub_cfg_loads_every_module_explicitly_and_chainloads_bootmgr(self):
        self.assertEqual(
            worker.BIOS_GRUB_CFG.splitlines(),
            ["insmod part_msdos", "insmod ntfs", "insmod ntldr", "insmod boot", "ntldr /bootmgr", "boot"],
        )

    def test_grub_cfg_is_fsynced(self):
        with patch("worker.os.fsync") as fsync:
            _events, _mountpoint, error = self.run_install()
        self.assertIsNone(error)
        fsync.assert_called_once()

    def test_missing_grub_stops_before_any_command(self):
        with patch("worker.shutil.which", return_value=None), patch("worker.command") as run, patch(
            "worker.validate_target"
        ) as validate:
            with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(RuntimeError, "pacman -S grub"):
                worker.install_bios_chainloader(self.DEVICE, Path(temp), {"serial": "x"}, self.LAYOUT)
        run.assert_not_called()
        validate.assert_not_called()

    def test_host_boot_directory_is_refused_before_any_command(self):
        with tempfile.TemporaryDirectory() as temp:
            grub_pc = self.make_grub_dir(Path(temp))
            with patch.object(worker, "GRUB_PC_DIRECTORY", grub_pc), patch(
                "worker.shutil.which", return_value="/usr/bin/grub-install"
            ), patch("worker.command") as run, patch("worker.validate_target") as validate:
                with self.assertRaisesRegex(RuntimeError, "gép saját"):
                    worker.install_bios_chainloader(self.DEVICE, Path("/boot"), {"serial": "x"}, self.LAYOUT)
        run.assert_not_called()
        validate.assert_not_called()

    def test_identity_failure_stops_before_grub_install(self):
        def failing_validate(*_args):
            raise RuntimeError("A célmeghajtó fizikai azonossága megváltozott (serial)")

        with tempfile.TemporaryDirectory() as temp:
            grub_pc = self.make_grub_dir(Path(temp))
            with patch.object(worker, "GRUB_PC_DIRECTORY", grub_pc), patch(
                "worker.shutil.which", return_value="/usr/bin/grub-install"
            ), patch("worker.assert_mount_is_partition"), patch(
                "worker.validate_target", side_effect=failing_validate
            ), patch("worker.command") as run:
                with self.assertRaisesRegex(RuntimeError, "azonossága"):
                    worker.install_bios_chainloader(self.DEVICE, Path(temp), {"serial": "x"}, self.LAYOUT)
        run.assert_not_called()

    def test_changed_partition_table_is_an_error(self):
        _events, _mountpoint, error = self.run_install(
            verify_effect=RuntimeError("Az MBR partíció mérete/kezdete eltér a tervezettől")
        )
        self.assertIsInstance(error, RuntimeError)
        self.assertIn("eltér", str(error))

    def test_empty_boot_code_or_missing_signature_is_an_error(self):
        for name, mbr, pattern in (
            ("zero boot code", bytes(510) + b"\x55\xaa", "üres"),
            ("no signature", b"\x01" * 512, "0x55AA"),
        ):
            with self.subTest(name):
                _events, _mountpoint, error = self.run_install(mbr=mbr)
                self.assertRegex(str(error), pattern)

    def test_missing_ntldr_module_after_install_is_an_error(self):
        events, mountpoint, error = self.run_install(grub_files=("ntfs.mod",))
        self.assertRegex(str(error), "ntldr.mod")
        self.assertFalse((mountpoint / "grub" / "grub.cfg").exists())
        self.assertNotIn("verify_mbr_layout", events)

    def test_cancel_before_install_runs_no_grub_install(self):
        events, _mountpoint, error = self.run_install(before=worker.CANCEL_EVENT.set)
        self.assertIsInstance(error, worker.OperationCancelled)
        self.assertEqual(events, [])
        self.assertEqual(self.grub_install_calls, [])

    def test_cancel_during_grub_install_takes_effect_right_after_it(self):
        events, mountpoint, error = self.run_install(command_effect=worker.CANCEL_EVENT.set)
        self.assertIsInstance(error, worker.OperationCancelled)
        self.assertEqual(events, ["mount_check", "validate_target", "grub-install"])
        self.assertFalse((mountpoint / "grub" / "grub.cfg").exists())

    def test_install_logs_that_grub_install_is_not_interruptible(self):
        with tempfile.TemporaryDirectory() as temp:
            grub_pc = self.make_grub_dir(Path(temp))
            with patch.object(worker, "GRUB_PC_DIRECTORY", grub_pc), patch(
                "worker.shutil.which", return_value="/usr/bin/grub-install"
            ), patch("worker.assert_mount_is_partition"), patch("worker.validate_target"), patch(
                "worker.command", side_effect=RuntimeError("stop after emit")
            ), patch("worker.emit") as emit:
                with self.assertRaisesRegex(RuntimeError, "stop after emit"):
                    worker.install_bios_chainloader(self.DEVICE, Path(temp), {"serial": "x"}, self.LAYOUT)
        logs = " ".join(str(call.kwargs.get("log", "")) for call in emit.call_args_list)
        self.assertIn("grub-install futása közben a megszakítás", logs)

    # -- assert_mount_is_partition -------------------------------------------

    def test_mount_check_requires_the_target_partition_device(self):
        devices = {"/dev/sdx1": 0x0811, "/dev/sda2": 0x0802}
        real_stat = os.stat

        def fake_stat(path, *args, **kwargs):
            # Python 3.12's Path.is_symlink() also goes through os.stat.
            if str(path) not in devices:
                if str(path).startswith("/dev/"):
                    raise FileNotFoundError(path)
                return real_stat(path, *args, **kwargs)
            return unittest.mock.Mock(st_mode=stat.S_IFBLK | 0o660, st_rdev=devices[str(path)])

        cases = (
            ("matching source", "/dev/sdx1\n", True),
            ("other device", "/dev/sda2\n", False),
            ("one of two sources differs", "/dev/sdx1\n/dev/sda2\n", False),
            ("unknown source", "tmpfs\n", False),
            ("nothing mounted", "", False),
        )
        with tempfile.TemporaryDirectory() as temp:
            for name, stdout, ok in cases:
                with self.subTest(name), patch(
                    "worker.command", return_value=subprocess.CompletedProcess([], 0, stdout, "")
                ) as run, patch("worker.os.stat", side_effect=fake_stat):
                    if ok:
                        worker.assert_mount_is_partition(Path(temp), "/dev/sdx1")
                    else:
                        with self.assertRaisesRegex(RuntimeError, "nem a pendrive NTFS partíciója"):
                            worker.assert_mount_is_partition(Path(temp), "/dev/sdx1")
                self.assertEqual(
                    run.call_args.args[0], ["findmnt", "-rn", "-o", "SOURCE", "--mountpoint", temp]
                )

    def test_mount_check_rejects_a_symlinked_mountpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / "real"
            real.mkdir()
            link = Path(temp) / "link"
            link.symlink_to(real, target_is_directory=True)
            with patch("worker.command") as run, self.assertRaisesRegex(RuntimeError, "szimbolikus"):
                worker.assert_mount_is_partition(link, "/dev/sdx1")
            run.assert_not_called()


class WindowsBiosWriterTests(unittest.TestCase):
    """write_windows_bios with mocked system commands (0.3.0 T4)."""

    DEVICE = "/dev/sdz"
    DISK_BYTES = 16 * 1024**3

    def setUp(self):
        for name in ("TARGET_MODIFIED", "OUTPUT_BROKEN"):
            patcher = patch.object(worker, name, False)
            patcher.start()
            self.addCleanup(patcher.stop)
        worker.CANCEL_EVENT.clear()
        self.addCleanup(worker.CANCEL_EVENT.clear)

    def run_writer(self, *, verify=True, total_sectors=None, on_command=None, extra_patches=(),
                   print_effect=None):
        """Run write_windows_bios; return (events, commands, temp_root, error)."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        image = root / "windows.iso"
        image.write_bytes(b"ISO")
        temp_root = root / "bootmediakit-run"
        iso_mount = temp_root / "iso"
        events: list[str] = []
        commands: list[list[str]] = []
        sectors = self.DISK_BYTES // 512 if total_sectors is None else total_sectors

        def record(name):
            def effect(*args, **kwargs):
                events.append(name)
            return effect

        def fake_mkdtemp(**kwargs):
            events.append("mkdtemp")
            temp_root.mkdir()
            return str(temp_root)

        def fake_command(args, **kwargs):
            commands.append(list(args))
            events.append("cmd:" + " ".join(args[:2]))
            if on_command:
                on_command(list(args))
            stdout = ""
            if args[:2] == ["blockdev", "--getss"]:
                stdout = "512\n"
            elif args[:2] == ["blockdev", "--getsz"]:
                stdout = f"{sectors}\n"
            return subprocess.CompletedProcess(args, 0, stdout, "")

        def fake_mount_iso(_image, mountpoint):
            events.append("mount_iso")
            mountpoint.mkdir(parents=True)

        def fake_scan(path, boot_mode="uefi"):
            events.append(f"scan:{boot_mode}")
            return path / "sources/install.wim", path / "sources/boot.wim", 4096

        def fake_copy(iso, usb, total, verify_flag, boot_files, message):
            events.append("copy")
            self.copy_args = (iso, usb, total, verify_flag, boot_files, message)

        def fake_chainloader(device, mount, identity, layout):
            events.append("install_bios_chainloader")
            self.chainloader_args = (device, mount, identity, layout)

        patches = [
            patch("worker.require_programs", side_effect=lambda programs: events.append("require_programs")),
            patch("worker.ensure_source_not_on_target", side_effect=record("ensure_source")),
            patch("worker.validate_target", side_effect=lambda *a: events.append("validate_target") or self.DISK_BYTES),
            patch("worker.require_bios_grub", side_effect=record("require_bios_grub")),
            patch("worker.tempfile.mkdtemp", side_effect=fake_mkdtemp),
            patch("worker.mount_iso", side_effect=fake_mount_iso),
            patch("worker.scan_windows_iso", side_effect=fake_scan),
            patch("worker.read_iso_volume_label", return_value="WIN_TEST"),
            patch("worker.unmount_disk", side_effect=record("unmount_disk")),
            patch("worker.assert_disk_unmounted", side_effect=record("assert_disk_unmounted")),
            patch("worker.verify_mbr_layout", side_effect=record("verify_mbr_layout")),
            patch("worker.wait_for_partition_nodes", side_effect=lambda *a, **k: (worker.check_cancelled(), events.append("wait_partitions"))),
            patch("worker.validate_ntfs_boot_sector", side_effect=record("validate_ntfs_boot_sector")),
            patch("worker.mount_ntfs_volume", side_effect=lambda *a: events.append("mount_ntfs") or "ntfs3"),
            patch("worker.copy_windows_files", side_effect=fake_copy),
            patch("worker.install_bios_chainloader", side_effect=fake_chainloader),
            patch("worker.command", side_effect=fake_command),
            patch("builtins.print", side_effect=print_effect),
            *extra_patches,
        ]
        error = None
        import contextlib
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            try:
                worker.write_windows_bios(image, self.DEVICE, verify, {"serial": "x"})
            except Exception as exc:  # noqa: BLE001 - returned for assertions
                error = exc
        self.iso_mount = iso_mount
        return events, commands, temp_root, error

    def test_full_sequence_matches_the_work_description(self):
        events, commands, temp_root, error = self.run_writer()
        self.assertIsNone(error)
        usb_mount = str(temp_root / "usb")
        order = [
            "require_programs", "ensure_source", "validate_target", "require_bios_grub",
            "cmd:blockdev --getss", "cmd:blockdev --getsz", "mkdtemp",
            "ensure_source", "mount_iso", "scan:bios",
            "ensure_source", "validate_target", "unmount_disk",
            "validate_target", "ensure_source", "assert_disk_unmounted",
            "cmd:wipefs --all", "cmd:sfdisk --wipe", "cmd:blockdev --rereadpt", "cmd:partprobe /dev/sdz",
            "cmd:udevadm settle", "verify_mbr_layout", "wait_partitions",
            "cmd:mkfs.ntfs --fast", "validate_ntfs_boot_sector",
            "validate_target", "unmount_disk", "mount_ntfs", "copy", "install_bios_chainloader",
            "cmd:sync --file-system", "cmd:umount --", "cmd:udevadm settle", "verify_mbr_layout",
        ]
        self.assertEqual(events[: len(order)], order)
        self.assertIn(["wipefs", "--all", "--force", self.DEVICE], commands)
        self.assertIn(["umount", "--", usb_mount], commands)
        sfdisk = next(args for args in commands if args[0] == "sfdisk")
        self.assertEqual(sfdisk, ["sfdisk", "--wipe", "never", self.DEVICE])
        mkfs = next(args for args in commands if args[0] == "mkfs.ntfs")
        self.assertEqual(
            mkfs,
            ["mkfs.ntfs", "--fast", "--force", "--label", "WIN_TEST", "--partition-start", "2048",
             "--sector-size", "512", "--heads", "255", "--sectors-per-track", "63",
             "--cluster-size", "4096", "/dev/sdz1"],
        )
        self.assertTrue(worker.TARGET_MODIFIED)
        self.assertFalse(temp_root.exists())

    def test_grub_is_installed_after_the_copy_and_before_the_final_unmount(self):
        events, _commands, temp_root, error = self.run_writer()
        self.assertIsNone(error)
        copy = events.index("copy")
        grub = events.index("install_bios_chainloader")
        final_umount = events.index("cmd:umount --", grub)
        self.assertLess(copy, grub)
        self.assertLess(grub, final_umount)
        self.assertEqual(self.chainloader_args[0], self.DEVICE)
        self.assertEqual(self.chainloader_args[1], temp_root / "usb")
        self.assertEqual(self.chainloader_args[2], {"serial": "x"})
        self.assertEqual(self.chainloader_args[3]["start"], 2048)

    def test_copy_checks_bios_boot_files_and_passes_the_verify_flag(self):
        for verify in (True, False):
            with self.subTest(verify=verify):
                worker.TARGET_MODIFIED = False
                _events, _commands, _temp_root, error = self.run_writer(verify=verify)
                self.assertIsNone(error)
                self.assertEqual(self.copy_args[3], verify)
                self.assertEqual(self.copy_args[4], ("bootmgr", "boot/bcd", "sources/boot.wim"))
                self.assertIn("Legacy BIOS", self.copy_args[5])

    def test_missing_grub_leaves_the_target_untouched(self):
        def no_grub():
            raise RuntimeError(worker.GRUB_MISSING_MESSAGE.format(detail="nincs grub-install"))

        events, commands, temp_root, error = self.run_writer(
            extra_patches=(patch("worker.require_bios_grub", side_effect=no_grub),)
        )
        self.assertRegex(str(error), "pacman -S grub")
        self.assertFalse(worker.TARGET_MODIFIED)
        self.assertEqual(commands, [])
        self.assertNotIn("unmount_disk", events)
        self.assertNotIn("mkdtemp", events)

    def test_disk_of_2_tib_is_refused_before_any_change(self):
        events, commands, _temp_root, error = self.run_writer(total_sectors=2**32)
        self.assertIsInstance(error, ValueError)
        self.assertIn("2 TiB", str(error))
        self.assertFalse(worker.TARGET_MODIFIED)
        self.assertFalse(any(args[0] in ("wipefs", "sfdisk", "mkfs.ntfs") for args in commands))
        self.assertNotIn("mkdtemp", events)

    def test_too_small_disk_for_the_iso_is_refused_before_any_change(self):
        # 4096 bytes of ISO data + 128 MiB reserve does not fit in 100 MiB.
        events, commands, temp_root, error = self.run_writer(total_sectors=100 * 2048)
        self.assertRegex(str(error), "Kevés a pendrive kapacitása")
        self.assertFalse(worker.TARGET_MODIFIED)
        self.assertNotIn("unmount_disk", events)
        self.assertFalse(any(args[0] == "wipefs" for args in commands))
        self.assertFalse(temp_root.exists())

    def test_cancel_after_wipefs_stops_and_cleans_up(self):
        def cancel_on_wipefs(args):
            if args[0] == "wipefs":
                worker.CANCEL_EVENT.set()

        events, commands, temp_root, error = self.run_writer(on_command=cancel_on_wipefs)
        self.assertIsInstance(error, worker.OperationCancelled)
        self.assertTrue(worker.TARGET_MODIFIED)
        self.assertFalse(any(args[0] == "mkfs.ntfs" for args in commands))
        self.assertNotIn("install_bios_chainloader", events)
        self.assertIn(["umount", "--", str(self.iso_mount)], commands)
        self.assertEqual(events.count("unmount_disk"), 2)
        self.assertFalse(temp_root.exists())

    def test_broken_gui_pipe_stops_at_next_safe_point_and_cleans_up(self):
        events, commands, temp_root, error = self.run_writer(
            print_effect=GuiPipeBrokenTests.pipe_breaks_once_target_is_modified
        )
        self.assertIsInstance(error, worker.OperationCancelled)
        self.assertIn("megszakadt a kapcsolat", str(error))
        self.assertTrue(worker.OUTPUT_BROKEN)
        self.assertIn(["wipefs", "--all", "--force", self.DEVICE], commands)
        self.assertFalse(any(args[0] == "mkfs.ntfs" for args in commands))
        self.assertFalse(any(args[0] == "mount" for args in commands))
        self.assertNotIn("install_bios_chainloader", events)
        self.assertIn(["umount", "--", str(self.iso_mount)], commands)
        self.assertGreaterEqual(events.count("unmount_disk"), 2)
        self.assertFalse(temp_root.exists())

    def test_final_log_describes_the_layout_and_legacy_only_boot(self):
        emitted = []
        _events, _commands, _temp_root, error = self.run_writer(
            extra_patches=(patch("worker.emit", side_effect=lambda *a, **k: emitted.append((a, k)) or True),)
        )
        self.assertIsNone(error)
        args, kwargs = emitted[-1]
        self.assertEqual(args[1], 100)
        for phrase in ("MBR", "aktív NTFS", "/grub", "csak Legacy BIOS", "UEFI módban nem"):
            self.assertIn(phrase, kwargs["log"])


class WindowsIsoScanTests(unittest.TestCase):
    def test_scan_accepts_case_insensitive_uefi_and_install_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            efi = root / "EFI" / "BOOT"
            efi.mkdir(parents=True)
            (efi / "BOOTX64.EFI").write_bytes(b"efi-loader")
            sources = root / "Sources"
            sources.mkdir()
            (sources / "Boot.WIM").write_bytes(b"boot-image")
            (sources / "Install.ESD").write_bytes(b"install-image")
            expected_total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())

            install_image, boot_wim, total = worker.scan_windows_iso(root)

            self.assertEqual(install_image.name, "Install.ESD")
            self.assertEqual(boot_wim.name, "Boot.WIM")
            self.assertEqual(total, expected_total)

    def test_scan_rejects_missing_boot_wim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            efi = root / "efi" / "boot"
            efi.mkdir(parents=True)
            (efi / "bootx64.efi").write_bytes(b"efi-loader")
            sources = root / "sources"
            sources.mkdir()
            (sources / "install.esd").write_bytes(b"install")
            with self.assertRaisesRegex(RuntimeError, "boot.wim"):
                worker.scan_windows_iso(root)

    def test_scan_rejects_missing_install_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            efi = root / "efi" / "boot"
            efi.mkdir(parents=True)
            (efi / "bootx64.efi").write_bytes(b"efi-loader")
            sources = root / "sources"
            sources.mkdir()
            (sources / "boot.wim").write_bytes(b"boot")
            with self.assertRaisesRegex(RuntimeError, "install.wim"):
                worker.scan_windows_iso(root)


class WindowsBiosIsoScanTests(unittest.TestCase):
    """scan_windows_iso(boot_mode="bios") for the Legacy BIOS/MBR mode (0.3.0 T1)."""

    @staticmethod
    def make_tree(root: Path, files: dict[str, bytes]) -> None:
        for relative, data in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    BIOS_FILES = {
        "BOOTMGR": b"bootmgr",
        "Boot/BCD": b"bcd",
        "Sources/Boot.WIM": b"boot-image",
        "Sources/install.swm": b"install-image",
    }

    def test_bios_mode_accepts_case_insensitive_files_without_efi_loader(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root, self.BIOS_FILES)
            expected_total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())

            install_image, boot_wim, total = worker.scan_windows_iso(root, boot_mode="bios")

            self.assertEqual(install_image.name, "install.swm")
            self.assertEqual(boot_wim.name, "Boot.WIM")
            self.assertEqual(total, expected_total)

    def test_bios_mode_accepts_wim_and_esd_install_images(self):
        for name in ("install.wim", "INSTALL.ESD"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                files = {key: value for key, value in self.BIOS_FILES.items() if "install" not in key}
                files[f"Sources/{name}"] = b"install-image"
                self.make_tree(root, files)
                install_image, _boot_wim, _total = worker.scan_windows_iso(root, boot_mode="bios")
                self.assertEqual(install_image.name, name)

    def test_default_and_explicit_uefi_mode_still_require_the_efi_loader(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root, self.BIOS_FILES)
            for kwargs in ({}, {"boot_mode": "uefi"}):
                with self.subTest(kwargs=kwargs), self.assertRaisesRegex(RuntimeError, "BOOTX64.EFI"):
                    worker.scan_windows_iso(root, **kwargs)

    def test_bios_mode_rejects_missing_bootmgr(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = dict(self.BIOS_FILES)
            del files["BOOTMGR"]
            files["bootmgr.efi"] = b"efi bootmgr is not the BIOS bootmgr"
            self.make_tree(root, files)
            with self.assertRaisesRegex(RuntimeError, "bootmgr Windows indítókezelő"):
                worker.scan_windows_iso(root, boot_mode="bios")

    def test_bios_mode_rejects_bootmgr_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = dict(self.BIOS_FILES)
            del files["BOOTMGR"]
            files["bootmgr/readme.txt"] = b"not a loader"
            self.make_tree(root, files)
            with self.assertRaisesRegex(RuntimeError, "bootmgr Windows indítókezelő"):
                worker.scan_windows_iso(root, boot_mode="bios")

    def test_bios_mode_names_windows_xp_style_iso_as_unsupported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root, {"I386/NTLDR": b"ntldr", "I386/SETUPLDR.BIN": b"setupldr"})
            with self.assertRaisesRegex(RuntimeError, "XP / Server 2003.*nem támogatja"):
                worker.scan_windows_iso(root, boot_mode="bios")

    def test_bios_mode_rejects_missing_bcd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = dict(self.BIOS_FILES)
            del files["Boot/BCD"]
            files["boot/boot.sdi"] = b"sdi"
            self.make_tree(root, files)
            with self.assertRaisesRegex(RuntimeError, "boot/BCD"):
                worker.scan_windows_iso(root, boot_mode="bios")

    def test_bios_mode_rejects_missing_boot_wim_and_install_image(self):
        for missing, pattern in (("Sources/Boot.WIM", "boot.wim"), ("Sources/install.swm", "install.wim")):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                files = dict(self.BIOS_FILES)
                del files[missing]
                self.make_tree(root, files)
                with self.assertRaisesRegex(RuntimeError, pattern):
                    worker.scan_windows_iso(root, boot_mode="bios")

    def test_bios_mode_refuses_an_existing_grub_entry_in_the_iso_root(self):
        for extra in ({"grub/grub.cfg": b"cfg"}, {"GRUB": b"file"}):
            with self.subTest(extra=list(extra)), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_tree(root, {**self.BIOS_FILES, **extra})
                with self.assertRaisesRegex(RuntimeError, "„grub” nevű.*nem írom felül"):
                    worker.scan_windows_iso(root, boot_mode="bios")

    def test_grub_entry_is_not_an_error_in_uefi_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root, {**self.BIOS_FILES, "efi/boot/bootx64.efi": b"efi", "grub/x": b"x"})
            worker.scan_windows_iso(root)

    def test_bios_mode_still_rejects_symlinks_and_special_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root, self.BIOS_FILES)
            (root / "link.txt").symlink_to(root / "BOOTMGR")
            with self.assertRaisesRegex(RuntimeError, "szimbolikus fájllinket"):
                worker.scan_windows_iso(root, boot_mode="bios")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root, self.BIOS_FILES)
            (root / "support").mkdir()
            (root / "support" / "dirlink").symlink_to(root / "Sources", target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "szimbolikus könyvtárlinket"):
                worker.scan_windows_iso(root, boot_mode="bios")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root, self.BIOS_FILES)
            os.mkfifo(root / "pipe")
            with self.assertRaisesRegex(RuntimeError, "Nem szabályos fájl"):
                worker.scan_windows_iso(root, boot_mode="bios")

    def test_unknown_boot_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                worker.scan_windows_iso(Path(temp), boot_mode="legacy")


class UefiNtfsLabelTests(unittest.TestCase):
    def test_prepare_renamed_helper_preserves_verified_upstream_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            upstream = root / "uefi-ntfs-upstream.img"
            destination = root / "uefi-ntfs-bmk-efi.img"
            original = b"pinned upstream helper image"
            upstream.write_bytes(original)
            responses = [
                subprocess.CompletedProcess(["fatlabel"], 0, "RUFUS_BOOT\n", ""),
                subprocess.CompletedProcess(["fatlabel"], 0, "", ""),
                subprocess.CompletedProcess(["fatlabel"], 0, "BMK_EFI\n", ""),
            ]
            with patch.object(worker, "UEFI_NTFS_IMAGE_SIZE", len(original)), patch(
                "worker.command", side_effect=responses
            ) as run, patch("worker.emit") as emit:
                result = worker.prepare_bmk_uefi_ntfs_image(upstream, destination)
                self.assertFalse(
                    any("RUFUS_BOOT" in str(call) or "BMK_EFI" in str(call) for call in emit.call_args_list),
                    "The internal upstream volume-label operation must not clutter the user log.",
                )

            self.assertEqual(result, destination)
            self.assertEqual(upstream.read_bytes(), original)
            self.assertEqual(destination.read_bytes(), original)
            self.assertEqual(run.call_args_list[0].args[0], ["fatlabel", str(upstream)])
            self.assertEqual(
                run.call_args_list[1].args[0],
                ["fatlabel", str(destination), "BMK_EFI"],
            )
            self.assertEqual(run.call_args_list[2].args[0], ["fatlabel", str(destination)])

    def test_prepare_rejects_unexpected_upstream_label(self):
        with tempfile.TemporaryDirectory() as temp:
            upstream = Path(temp) / "uefi-ntfs.img"
            destination = Path(temp) / "bmk-efi.img"
            upstream.write_bytes(b"pinned helper")
            with patch.object(worker, "UEFI_NTFS_IMAGE_SIZE", upstream.stat().st_size), patch(
                "worker.command",
                return_value=subprocess.CompletedProcess(["fatlabel"], 0, "UNKNOWN\n", ""),
            ):
                with self.assertRaisesRegex(RuntimeError, "elvárt: RUFUS_BOOT"):
                    worker.prepare_bmk_uefi_ntfs_image(upstream, destination)
            self.assertFalse(destination.exists())


class UefiNtfsImageTests(unittest.TestCase):
    def test_helper_image_size_and_hash_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "uefi-ntfs.img"
            path.write_bytes(b"BootMediaKit helper")
            size = path.stat().st_size
            digest = worker.git_blob_sha1(path)
            sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(worker, "UEFI_NTFS_IMAGE_SIZE", size), patch.object(
                worker, "UEFI_NTFS_GIT_BLOB_SHA1", digest
            ), patch.object(worker, "UEFI_NTFS_SHA256", sha256):
                worker.verify_uefi_ntfs_image(path)

    def test_helper_image_with_wrong_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "uefi-ntfs.img"
            path.write_bytes(b"tampered helper")
            with patch.object(worker, "UEFI_NTFS_IMAGE_SIZE", path.stat().st_size), patch.object(
                worker, "UEFI_NTFS_GIT_BLOB_SHA1", "0" * 40
            ):
                with self.assertRaisesRegex(RuntimeError, "Git-blob"):
                    worker.verify_uefi_ntfs_image(path)


    def test_helper_image_with_wrong_sha256_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "uefi-ntfs.img"
            path.write_bytes(b"correct git hash but bad sha256 pin")
            git_hash = worker.git_blob_sha1(path)
            with patch.object(worker, "UEFI_NTFS_IMAGE_SIZE", path.stat().st_size), patch.object(
                worker, "UEFI_NTFS_GIT_BLOB_SHA1", git_hash
            ), patch.object(worker, "UEFI_NTFS_SHA256", "0" * 64):
                with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                    worker.verify_uefi_ntfs_image(path)




class NtfsBootSectorTests(unittest.TestCase):
    def make_valid_boot_sector(self, start_sector=2048):
        boot = bytearray(512)
        boot[3:11] = b"NTFS    "
        struct.pack_into("<H", boot, 11, 512)
        boot[13] = 8
        struct.pack_into("<H", boot, 24, 63)
        struct.pack_into("<H", boot, 26, 255)
        struct.pack_into("<I", boot, 28, start_sector)
        boot[510:512] = b"\x55\xaa"
        return bytes(boot)

    def test_valid_ntfs_bpb_geometry_and_hidden_sectors_are_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "partition.img"
            path.write_bytes(self.make_valid_boot_sector())
            worker.validate_ntfs_boot_sector(str(path), 2048)

    def test_wrong_hidden_sector_offset_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "partition.img"
            path.write_bytes(self.make_valid_boot_sector(start_sector=0))
            with self.assertRaisesRegex(RuntimeError, "HiddenSectors"):
                worker.validate_ntfs_boot_sector(str(path), 2048)

    def test_wrong_chs_geometry_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            boot = bytearray(self.make_valid_boot_sector())
            struct.pack_into("<H", boot, 24, 0)
            path = Path(temp) / "partition.img"
            path.write_bytes(boot)
            with self.assertRaisesRegex(RuntimeError, "BPB geometria"):
                worker.validate_ntfs_boot_sector(str(path), 2048)


class WindowsVerifyArgumentTests(unittest.TestCase):
    def _run_main(self, verify: str):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "windows.iso"
            image.write_bytes(b"ISO test")
            identity = {
                "path": "/dev/sdb", "size": 8 * 1024**3, "maj_min": "8:16",
                "model": "USB Disk", "serial": "ABC123", "wwn": "",
                "tran": "usb", "rm": False, "diskseq": "4", "by_id": "/dev/disk/by-id/usb-ABC",
            }
            with patch("worker.os.geteuid", return_value=0), patch(
                "worker.validate_privileged_install"
            ), patch("worker.start_control_reader"), patch("worker.emit"), patch(
                "worker.write_windows_uefi"
            ) as write:
                result = worker.main(
                    ["bootmediakit-worker", "windows", str(image), "/dev/sdb", verify, json.dumps(identity)]
                )
            self.assertEqual(result, 0)
            write.assert_called_once_with(image.resolve(), "/dev/sdb", verify == "1", identity)

    def test_main_passes_disabled_verification_and_identity_to_windows_writer(self):
        self._run_main("0")

    def test_main_passes_enabled_verification_and_identity_to_windows_writer(self):
        self._run_main("1")

    def test_main_refuses_to_launch_from_uninstalled_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "windows.iso"
            image.write_bytes(b"ISO test")
            with patch("worker.os.geteuid", return_value=0), patch(
                "worker.validate_privileged_install", side_effect=RuntimeError("untrusted path")
            ), patch("worker.emit") as emit, patch("worker.write_windows_uefi") as write:
                result = worker.main([
                    "worker.py", "windows", str(image), "/dev/sdb", "0", "{}"
                ])
            self.assertEqual(result, 1)
            emit.assert_called_once()
            write.assert_not_called()




class KernelCopyTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, "copy_file_range"), "copy_file_range is unavailable")
    def test_unverified_copy_uses_kernel_copy_file_range_when_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            payload = b"kernel-assisted copy test" * 1000
            (source / "boot.wim").write_bytes(payload)
            real_copy_file_range = os.copy_file_range

            with patch(
                "worker.os.copy_file_range", wraps=real_copy_file_range
            ) as copy_range:
                manifest = worker.copy_tree_progress(
                    source, destination, len(payload), hash_files=False
                )

            self.assertGreater(copy_range.call_count, 0)
            self.assertEqual(manifest, [])
            self.assertEqual((destination / "boot.wim").read_bytes(), payload)

    @unittest.skipUnless(
        hasattr(os, "copy_file_range") and hasattr(os, "sendfile"),
        "copy_file_range/sendfile are unavailable",
    )
    def test_copy_file_range_uses_sendfile_fallback_on_cross_filesystem_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            payload = b"sendfile fallback test" * 3000
            (source / "boot.wim").write_bytes(payload)
            real_sendfile = os.sendfile

            with patch(
                "worker.os.copy_file_range",
                side_effect=OSError(errno.EXDEV, "cross-device copy not supported"),
            ), patch("worker.os.sendfile", wraps=real_sendfile) as sendfile, patch(
                "worker.emit"
            ) as emit:
                manifest = worker.copy_tree_progress(
                    source, destination, len(payload), hash_files=False
                )

            self.assertGreater(sendfile.call_count, 0)
            self.assertEqual(manifest, [])
            self.assertEqual((destination / "boot.wim").read_bytes(), payload)
            self.assertTrue(
                any(
                    "fájlrendszerek közötti gyorsmásolás" in str(call)
                    for call in emit.call_args_list
                )
            )
            self.assertFalse(any("Errno 18" in str(call) for call in emit.call_args_list))

    @unittest.skipUnless(hasattr(os, "copy_file_range"), "copy_file_range is unavailable")
    def test_kernel_copy_falls_back_to_streaming_when_both_syscalls_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            payload = b"fallback copy test" * 1000
            (source / "boot.wim").write_bytes(payload)

            with patch(
                "worker.os.copy_file_range",
                side_effect=OSError(errno.EXDEV, "cross-device copy not supported"),
            ), patch(
                "worker.os.sendfile",
                side_effect=OSError(errno.EXDEV, "sendfile cross-device copy not supported"),
            ), patch("worker.emit") as emit:
                manifest = worker.copy_tree_progress(
                    source, destination, len(payload), hash_files=False
                )

            self.assertEqual(manifest, [])
            self.assertEqual((destination / "boot.wim").read_bytes(), payload)
            self.assertFalse(any("Errno 18" in str(call) for call in emit.call_args_list))

    def test_progress_messages_are_throttled_to_percentage_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            payload = bytes(range(100))
            (source / "boot.wim").write_bytes(payload)

            with patch.object(worker, "CHUNK", 1), patch("worker.emit") as emit:
                worker.copy_tree_progress(
                    source, destination, len(payload),
                    base_percent=0, span=10, hash_files=True,
                )

            percent_events = [
                call for call in emit.call_args_list
                if len(call.args) >= 2 and call.args[1] is not None
            ]
            self.assertLessEqual(len(percent_events), 12)


if __name__ == "__main__":
    unittest.main()
