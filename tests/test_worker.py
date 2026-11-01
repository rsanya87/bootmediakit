import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import worker
from iso_utils import is_windows_install_iso


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

    def test_sfdisk_script_uses_basic_data_and_efi_system_types(self):
        layout = worker.calculate_gpt_layout((16 * 1024 * 1024 * 1024) // 512)
        script = worker.make_sfdisk_script(layout)
        self.assertIn("label: gpt", script)
        self.assertIn(worker.GPT_BASIC_DATA_GUID, script)
        self.assertIn(worker.GPT_ESP_GUID, script)
        self.assertIn('name="BOOTMEDIA"', script)
        self.assertIn('name="BOOTMEDIA_EFI"', script)

    def test_partition_path_handles_sd_and_nvme_names(self):
        self.assertEqual(worker.partition_path("/dev/sdb", 1), "/dev/sdb1")
        self.assertEqual(worker.partition_path("/dev/nvme1n1", 2), "/dev/nvme1n1p2")

    def test_git_blob_sha1_matches_git_object_format(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.bin"
            payload = b"BootMediaKit"
            path.write_bytes(payload)
            expected = hashlib.sha1(b"blob 12\0" + payload).hexdigest()
            self.assertEqual(worker.git_blob_sha1(path), expected)


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


class UefiNtfsImageTests(unittest.TestCase):
    def test_helper_image_size_and_hash_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "uefi-ntfs.img"
            path.write_bytes(b"BootMediaKit helper")
            size = path.stat().st_size
            digest = worker.git_blob_sha1(path)
            with patch.object(worker, "UEFI_NTFS_IMAGE_SIZE", size), patch.object(
                worker, "UEFI_NTFS_GIT_BLOB_SHA1", digest
            ):
                worker.verify_uefi_ntfs_image(path)

    def test_helper_image_with_wrong_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "uefi-ntfs.img"
            path.write_bytes(b"tampered helper")
            with patch.object(worker, "UEFI_NTFS_IMAGE_SIZE", path.stat().st_size), patch.object(
                worker, "UEFI_NTFS_GIT_BLOB_SHA1", "0" * 40
            ):
                with self.assertRaisesRegex(RuntimeError, "ellenőrzőösszege"):
                    worker.verify_uefi_ntfs_image(path)



if __name__ == "__main__":
    unittest.main()
