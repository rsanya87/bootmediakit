# Testing

## 0.1.3-safety-alpha P0 hardening

The current branch adds the following P0-focused automated tests:

- Device identity rejects changed disk sequence, capacity and major:minor values.
- Source image on the same physical disk as the target is rejected; a different source disk is accepted.
- LUKS and swap targets are refused before unmounting.
- Cancellation flag and safe-boundary copy cancellation behavior.
- Direct worker execution from an untrusted source checkout is rejected.
- Polkit XML action path, root-wrapper launch command, installer ownership/mode and GUI wrapper invocation are validated.

CI currently runs 61 unit/packaging tests (including responsive GUI source-contract checks, clean EXDEV fallback logging and quiet upstream label verification). Physical validation still required: install on CachyOS, confirm the polkit dialog, test cancellation on a disposable USB (during both RAW and Windows file-copy stages), confirm a different USB device cannot be substituted after selection, and confirm a source image stored on the target disk is refused without modifying it.

## 0.1.2 release validation

Run from the repository root:

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py
bash -n install.sh uninstall.sh bootmediakit-worker
python3 -m unittest discover -s tests -v
```

The GitHub Actions workflow runs these static and unit checks on pushes to development branches and on pull requests.

### Unit-test scope

- Block-device safety validation rejects invalid paths and non-block devices.
- Case-insensitive lookup of UEFI and Windows setup files.
- Windows ISO detection.
- GPT partition layout calculation and alignment.
- Parse the generated GPT layout with real `sfdisk --no-act` against a sparse image file.
- Validate NTFS boot-sector OEM ID, bytes/sector, cluster geometry, HiddenSectors, heads/sectors-per-track and 0x55AA signature.
- Exercise best-effort `copy_file_range`, `sendfile` fallback, buffered fallback when both are unsupported, and throttled progress reporting.
- Verify that the Windows SHA-256 checkbox value is passed from the CLI entry point to the writer.
- Validate the actual `mkfs.ntfs` flags with `--no-action` against a temporary file.
- GPT Microsoft Basic Data type identifiers on both partitions.
- The 1 MiB FAT BMK_EFI helper partition's GPT name, volume label and GUID:63 NoDriveLetter attribute (and that it is not typed as an EFI System Partition).
- Creating a temporary BMK_EFI-labelled helper image from a hash-verified pristine upstream source image; ensure the original source remains unchanged.
- Linux `sdX` and NVMe partition naming.
- Git object hash calculation used to pin the helper image.
- Windows ISO scan for EFI bootloader, boot.wim and install image.
- File-copy manifest generation, no-hash fast-copy path, and SHA-256 read-back verification.
- Kernel NTFS3 mount preference and ntfs-3g fallback.
- Dynamic copy-progress range when the optional SHA-256 second pass is disabled or enabled.
- Detection of a changed copied file.

Current automated test suite: 37 unit tests plus GitHub Actions checks using the real sfdisk, mkfs.ntfs and fatlabel utilities. CI downloads the pinned UEFI helper image, verifies its exact size and both hashes, then changes only a temporary copy's FAT label from RUFUS_BOOT to BMK_EFI. Unit tests use temporary files and mocked tools; CI's FAT-label check uses the real dosfstools command. These checks do not write to a real USB drive.

## Physical test results and remaining validation

1. Install on CachyOS. Confirm that `ntfs-3g`, `ntfsprogs`, `dosfstools` and other dependencies are present and the pristine helper image downloads with the pinned hashes. **User test passed.**
2. Confirm the downloaded image is exactly 1,048,576 bytes and matches the pinned Git blob SHA-1 and SHA-256. **CI passed.**
3. Use a disposable USB drive. Check the device path, model, capacity and all partitions before confirming.
4. Create a Windows 10 IoT Enterprise LTSC 2021 x64 USB from the same ISO used for the 0.1.1 failure report.
5. Inspect the GPT layout: both partitions must be Microsoft Basic Data; partition 1 is NTFS and partition 2 is FAT named BMK_EFI with GUID:63 NoDriveLetter and the 1 MiB helper image. The helper partition must not be typed as EFI System Partition.
6. Confirm the install.esd is copied unchanged (same size and SHA-256 as the ISO source file).
7. **User test passed through first reboot:** on the Samsung RV511, boot the USB in UEFI mode, Windows Setup loaded the installation image, copied files, passed the first reboot and continued from the 120 GB internal SSD. Final desktop/first-login confirmation is still desirable.
8. Record Secure Boot enabled/disabled results separately. Do not claim Secure Boot compatibility if the firmware rejects an upstream signature.
9. The user reports significantly faster creation on two USB 2.0 sticks after the kernel NTFS3/copy optimizations. Exact elapsed times and USB 3.x comparison remain outstanding.
10. If Setup reports `GetMachineInfo: Couldn't find info for boot disk` or `CanBeSystemVolume`, first confirm the 120 GB SSD's disk number and GPT status with `diskpart list disk`; repeat the installation with non-target internal HDDs temporarily disconnected.
11. Optionally repeat using a second USB stick and Windows ISO.

## Test result discipline

Do not describe mocked unit tests as proof that media creation works on physical hardware. The same-machine Windows Setup source-access and first-reboot test has passed. Keep issue #2 open for final install confirmation and Secure Boot follow-up; broader platform coverage is still future work.


### UI feedback follow-up

- Check on KDE dark theme that disk details, serial/WWN, partition filesystems, labels and mountpoints are readable.
- Choose an ISO with a long filename/path; verify the metadata wraps and no horizontal scrollbar appears. Vertical scrolling remains available when the window is shorter than the full form.
- Verify the small `0.1.3-safety-alpha` string appears below the BootMediaKit title.
- During Windows writing, an expected `EXDEV` fallback may occur between ISO9660/loop and NTFS. The operation must continue and the user log must not contain raw `[Errno 18]` output.
- Verify helper FAT-label relabeling still yields the `BMK_EFI` volume on the USB, while no upstream `RUFUS_BOOT` relabel message is printed in the user log.
