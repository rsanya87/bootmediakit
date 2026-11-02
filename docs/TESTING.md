# Testing

## 0.1.2-alpha development checks

Run from the repository root:

```bash
python3 -m py_compile app.py worker.py iso_utils.py fetch_uefi_ntfs.py
bash -n install.sh uninstall.sh
python3 -m unittest discover -s tests -v
```

The GitHub Actions workflow runs these static and unit checks on pushes to development branches and on pull requests.

### Unit-test scope

- Block-device safety validation rejects invalid paths and non-block devices.
- Case-insensitive lookup of UEFI and Windows setup files.
- Windows ISO detection.
- GPT partition layout calculation and alignment.
- Parse the generated GPT layout with real `sfdisk --no-act` against a sparse image file.
- Validate the actual `mkfs.ntfs` flags with `--no-action` against a temporary file.
- GPT Basic Data and EFI System partition type identifiers.
- Linux `sdX` and NVMe partition naming.
- Git object hash calculation used to pin the helper image.
- Windows ISO scan for EFI bootloader, boot.wim and install image.
- File-copy manifest generation, no-hash fast-copy path, and SHA-256 read-back verification.
- Kernel NTFS3 mount preference and ntfs-3g fallback.
- Detection of a changed copied file.

Current automated test suite: 22 unit tests plus dry-run checks using the real sfdisk and mkfs.ntfs utilities in GitHub Actions. GitHub Actions also downloads the pinned UEFI helper image and verifies its exact size and both hashes. Unit tests use temporary files and mocked tools. They do not write to a real USB drive.

## Required manual tests before merge/release

1. Install the branch on a clean/current CachyOS system. Confirm that `ntfs-3g`, `ntfsprogs`, and other dependencies are present and that the UEFI helper image downloads with the pinned hash.
2. Confirm the downloaded image is exactly 1,048,576 bytes and matches the pinned Git blob SHA-1.
3. Use a disposable USB drive. Check the device path, model, capacity and all partitions before confirming.
4. Create a Windows 10 IoT Enterprise LTSC 2021 x64 USB from the same ISO used for the 0.1.1 failure report.
5. Inspect the GPT layout: partition 1 must be Microsoft Basic Data / NTFS; partition 2 must be EFI System / FAT and contain the 1 MiB helper image.
6. Confirm the install.esd is copied unchanged (same size and SHA-256 as the ISO source file).
7. Boot the USB in UEFI mode on the same physical PC. Confirm UEFI:NTFS launches Windows Boot Manager and Windows Setup can load the installation image.
8. Record Secure Boot enabled/disabled results separately. Do not claim Secure Boot compatibility if the firmware rejects an upstream signature.
9. Record USB creation time and transfer rate on both a USB 2.0 stick and, if available, a USB 3.x stick. Compare the Windows verification checkbox off/on.
10. Optionally repeat using a second USB stick and Windows ISO.

## Test result discipline

Do not describe mocked unit tests as proof that media creation works on physical hardware. Do not close GitHub issue #2 until the same-machine test passes. Do not merge to `main` or publish a 0.1.2 release before the user confirms successful boot and Windows Setup source access.
