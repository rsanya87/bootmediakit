# Testing

## BootMediaKit 0.2.2 — Stable release (2026-11-10)

0.2.2 is a maintenance release. The write sequence and the Windows-mode GPT layout are unchanged from 0.2.1.

### Automated checks

The GitHub Actions suite passed on the final pre-release source commit: [run 42714445280](https://github.com/rsanya87/bootmediakit/actions/runs/42714445280). The release commit after it changes only the version number and documentation. In addition to the 0.2.1 checks, the workflow now runs:

- `shellcheck -S warning` on the installer, uninstaller and privileged worker wrapper.
- 129 unit, packaging and offscreen GUI tests.
- Three loop-device integration tests as root that run the real RAW and Windows writers against disk images (see [Loop-device integration tests](#loop-device-integration-tests)).

The same unit and integration tests also passed on the maintainer's CachyOS system (Python 3.14, util-linux 2.42).

### Physical validation confirmed for 0.2.2

- **Linux DD/RAW with read-back verification:** Linux Mint 22.3 media booted from physical USB in Legacy BIOS/MBR mode and in UEFI mode.
- **RAW over a former Windows-mode drive:** the same RAW write was made on a drive that carried the Windows-mode two-partition GPT immediately before; the result booted in both modes. On first boot Linux Mint created its own `writable` partition in the free space after the image; this is done by the live system, not by BootMediaKit.
- **Windows 10/11 IoT Enterprise LTSC, UEFI:** the media was created, the first partition carries the ISO volume label and the second is named `BMK_EFI`; the media boots as it did with 0.2.1.
- **Installed application:** `install.sh` installs `version.py`; the application starts and exits cleanly on CachyOS.

### Release acceptance record

- Linux DD/RAW boot in UEFI and Legacy BIOS/MBR modes, read-back enabled: passed.
- RAW write over a previous Windows-mode GPT: passed.
- Windows IoT LTSC media creation, partition names and boot: passed.
- `sfdisk -d` confirmation of the `GUID:63` attribute and Windows Setup up to its first reboot: not reported for 0.2.2 (verified on 0.2.1; covered for the attribute by the integration test).
- Windows 11 26H2 standard ISO with Secure Boot off and on: not repeated for 0.2.2 (verified on 0.2.1 to the disk-selection screen).
- The new source-filesystem rejection message on a FUSE/network/overlay source, an ISO on a `fuseblk` (ntfs-3g) disk, and device refresh during unplug/replug: not physically tested; covered by unit tests only.

Do not treat mocked unit tests or loop-device tests as proof of physical hardware behavior. Destructive tests must use disposable media only. Never use a drive containing the source ISO or user data as a test target.

## BootMediaKit 0.2.1 — Historical release test record (2026-11-05)

### Automated checks

The GitHub Actions suite passed on the final release-candidate source commit: [run 41980736701](https://github.com/rsanya87/bootmediakit/actions/runs/41980736701). The workflow covers:

- Python compilation for the GUI, worker, ISO helpers and UI helpers.
- Shell syntax checks for the installer, uninstaller and privileged worker wrapper.
- Download and hash verification of the pinned UEFI:NTFS helper image.
- A real-tool dry-run of NTFS formatting arguments.
- A test that brands a temporary copy of the UEFI:NTFS helper image `BMK_EFI` while leaving the pristine source unchanged.
- Unit, packaging and offscreen GUI tests for device safety, source/target collision detection, cancellation boundaries, Polkit packaging, GUI lifecycle, ISO metadata and GPT partition handling.

To run the checks locally, see [Running the automated tests](#running-the-automated-tests) below.

### Physical validation confirmed for 0.2.1

- **Linux DD/RAW:** Linux Mint 22.3 Cinnamon media booted successfully from physical USB in UEFI mode and in Legacy BIOS/MBR mode.
- **Windows IoT LTSC:** Windows 10 and Windows 11 IoT Enterprise LTSC x64 installation media completed UEFI installation successfully on the tested system(s).
- **Windows 11 26H2 standard ISO:** Windows Setup reached the disk-selection/partitioning screen with Secure Boot disabled and also with Secure Boot enabled. Installation beyond the partition-selection screen was not completed and is not claimed as a passed full-install test.
- **Secure Boot scope:** the successful 26H2 Setup launch confirms the observed boot path on the test firmware only. It does not establish compatibility with every UEFI implementation, certificate database or revocation state.

### Release acceptance record

- Linux DD/RAW boot in UEFI and Legacy BIOS/MBR modes: passed.
- Windows 10 and Windows 11 IoT Enterprise LTSC UEFI installations: passed.
- Windows 11 26H2 standard ISO, Secure Boot off and on, through Setup disk selection: passed to that stage.
- Windows 11 26H2 installation beyond disk selection: not tested.
- Additional firmware, non-Arch distributions, physical hot-unplug/replug races and source-on-target rejection remain outside this release's verified test matrix.

Do not treat mocked unit tests as proof of physical hardware behavior. Destructive tests must use disposable media only. Never use a drive containing the source ISO or user data as a test target.

## Running the automated tests

### Static checks, unit tests and offscreen GUI tests

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py version.py
bash -n install.sh uninstall.sh bootmediakit-worker
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

The GUI tests (`tests/test_app.py`) need `PySide6`. CI also lints the shell scripts:

```bash
shellcheck -S warning install.sh uninstall.sh bootmediakit-worker
```

### Loop-device integration tests

`tests/integration/` runs the real `worker.write_raw` and `worker.write_windows_uefi` functions against a loop device backed by a disk image file. No physical drive is touched; all test files live on a private tmpfs that is unmounted afterwards.

```bash
sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

Skip conditions: every integration test is skipped unless `BMK_INTEGRATION=1` is set, the process is root, and `losetup`, `sfdisk`, `wipefs`, `mkfs.ext4`, `mkfs.ntfs` and `fatlabel` are available. A normal, non-root `unittest discover -s tests` run does not enter this directory. CI sets `BMK_INTEGRATION_REQUIRED=1`, which turns a missing precondition into an error so the step cannot pass by skipping.

The worker itself additionally needs `lsblk`, `blockdev`, `findmnt`, `udevadm`, `partprobe`, `blkid`, `7z` and a working NTFS mount (kernel `ntfs3` or `ntfs-3g`); a missing one is reported as a test error, not a skip.

What the tests do:

- **RAW (`test_loop_raw.py`):** a 128 MiB image with an old two-partition GPT (ext4 on the first partition) is attached with `losetup --partscan`; a 40 MiB pseudo-random image with an MBR is written with `write_raw` and read-back verification. The test compares the written bytes with the source (`cmp`), checks that `wipefs` finds neither the primary nor the backup GPT signature (only the source's `dos` table), and that the kernel dropped the stale second partition. A second test keeps a stale partition open exclusively during the write; `wipefs` then fails without `--force`, so the test notices if that flag is dropped.
- **Windows (`test_loop_windows.py`):** a directory with the essential Windows Setup file names is bind-mounted in place of an ISO (`worker.mount_iso` and `worker.read_iso_volume_label` are replaced), and `write_windows_uefi` runs with SHA-256 verification on a 384 MiB image. The test checks the GPT (`sfdisk --json`: two Microsoft Basic Data partitions, the second named `BMK_EFI` with `GUID:63`), the NTFS label, the FAT label and the SHA-256 of every copied file. The pinned UEFI:NTFS image is taken from `BMK_UEFI_NTFS_IMAGE`, from the installed copy, or downloaded and verified with `fetch_uefi_ntfs.py`.

The loop device is a stand-in: `tests/integration/loop_helpers.py` makes `worker.lsblk_tree` report exactly the test's loop device as a removable `disk`. `validate_target` and every other safety check run unmodified. This substitution exists only in the test helper.

Known limits and problems:

- If the kernel or udev does not create the partition nodes (`/dev/loopNp1`, …) within 20 seconds, the test **fails** with a message pointing here; it does not pass silently. This happens in containers without udev and with kernels that have no partition-table parsers. Run the tests on a normal host or VM, or make sure `udevadm settle` works and `/dev` is a devtmpfs.
- These tests are not a substitute for physical USB tests. They give no evidence about partitions actually *used* by the kernel (mounted, swap, LUKS), about USB-specific properties (`rm`, `tran=usb`), about firmware boot, or about Windows Setup.

## BootMediaKit 0.1.3 — Historical release test record

### Automated checks

The 0.1.3 GitHub Actions workflow ran:

- Python compilation for the GUI, worker, ISO helpers and UI helpers.
- Shell syntax checks for the installer, uninstaller and privileged worker wrapper.
- Download and hash verification of the pinned UEFI:NTFS helper image.
- A real-tool dry-run of NTFS formatting arguments.
- Unit and packaging tests for disk identity, source/target collision detection, protected volume rejection, cancellation boundaries, Polkit packaging, responsive UI, ISO label parsing and GPT partition naming.

### Physical validation reported by the user

- **Linux DD/RAW:** a Linux ISO written in DD mode booted successfully on tested hardware in both Legacy BIOS and UEFI modes.
- **Windows UEFI:** Windows 10 IoT Enterprise LTSC 2021 x64 booted from the created USB and completed installation in UEFI mode.
- **Cancellation:** the user cancelled a physical USB creation operation; the worker stopped safely and the USB remained usable for a subsequent attempt.
- **Write performance:** successful creation was reported on different USB 2.0 drives, with elapsed times varying by the individual drive.
- **Polkit and application installation:** the installed package was used on CachyOS; the GUI and privileged worker completed a Windows USB creation.

### Still requiring broader validation

- Secure Boot enabled/disabled on multiple firmware implementations.
- Physical target hot-unplug/replug race testing.
- Physical source-on-target rejection test.
- LUKS/LVM/RAID/swap rejection on disposable devices.
- Additional Windows ISO families and non-CachyOS distributions.

Do not claim physical hardware behavior based only on unit tests.
