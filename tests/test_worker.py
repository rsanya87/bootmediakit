import tempfile
import unittest
from unittest.mock import patch
import subprocess
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import worker


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
            self.assertIsNone(worker.find_case_insensitive(Path(temp), "sources/install.wim"))

    def test_windows_iso_detector_recognizes_install_wim(self):
        result = subprocess.CompletedProcess(["7z"], 0, "Path = test.iso\nPath = sources\\install.wim\n", "")
        with patch("shutil.which", return_value="/usr/bin/7z"), patch("subprocess.run", return_value=result):
            from iso_utils import is_windows_install_iso
            self.assertTrue(is_windows_install_iso(Path("fake.iso")))

    def test_windows_iso_detector_ignores_regular_linux_iso(self):
        result = subprocess.CompletedProcess(["7z"], 0, "Path = test.iso\nPath = casper/filesystem.squashfs\n", "")
        with patch("shutil.which", return_value="/usr/bin/7z"), patch("subprocess.run", return_value=result):
            from iso_utils import is_windows_install_iso
            self.assertFalse(is_windows_install_iso(Path("fake.iso")))


class WimHandlingTests(unittest.TestCase):
    def test_esd_export_uses_all_images_and_lzx_wim_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            esd = root / "install.esd"
            output = root / "install.wim"
            esd.write_bytes(b"source")

            def fake_run(args, *, title, percent):
                if args[1] == "export":
                    output.write_bytes(b"converted-wim")

            with patch("worker.run_wimlib", side_effect=fake_run) as run:
                worker.export_esd_to_wim(esd, output)

            self.assertTrue(output.is_file())
            first_call = run.call_args_list[0].args[0]
            self.assertEqual(first_call[1], "export")
            self.assertEqual(first_call[3], "all")
            self.assertIn("--compress=LZX", first_call)

    def test_split_wim_returns_ordered_swm_parts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wim = root / "install.wim"
            out = root / "install.swm"
            wim.write_bytes(b"wim")

            def fake_run(args, *, title, percent):
                (root / "install2.swm").write_bytes(b"second")
                (root / "install.swm").write_bytes(b"first")

            with patch("worker.run_wimlib", side_effect=fake_run):
                parts = worker.split_wim(wim, out)

            self.assertEqual([p.name for p in parts], ["install.swm", "install2.swm"])

    def test_split_wim_rejects_parts_over_fat32_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wim = root / "install.wim"
            out = root / "install.swm"
            wim.write_bytes(b"wim")

            def fake_run(args, *, title, percent):
                with (root / "install.swm").open("wb") as f:
                    f.truncate(worker.FAT32_MAX_FILE + 1)

            with patch("worker.run_wimlib", side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, "4 GiB fölé"):
                    worker.split_wim(wim, out)


if __name__ == "__main__":
    unittest.main()
