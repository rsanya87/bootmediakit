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

`tests/integration/` runs the real `worker.write_raw`, `worker.write_windows_uefi` and `worker.write_windows_bios` functions against a loop device backed by a disk image file. No physical drive is touched; all test files live on a private tmpfs that is unmounted afterwards.

```bash
sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

With `BMK_QEMU=1` the Legacy BIOS tests also boot the written disk image in QEMU with SeaBIOS (this is what CI runs):

```bash
sudo -E env BMK_INTEGRATION=1 BMK_QEMU=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

Skip conditions: every integration test is skipped unless `BMK_INTEGRATION=1` is set, the process is root, and `losetup`, `sfdisk`, `wipefs`, `mkfs.ext4`, `mkfs.ntfs` and `fatlabel` are available. A normal, non-root `unittest discover -s tests` run does not enter this directory. CI sets `BMK_INTEGRATION_REQUIRED=1`, which turns a missing precondition into an error so the step cannot pass by skipping.

The Legacy BIOS tests (`test_loop_windows_bios.py`) additionally need `grub-install` and the `/usr/lib/grub/i386-pc` directory (Arch: `grub`; Debian/Ubuntu CI: `grub-pc-bin` and `grub2-common`); the writer tests also need every program in `worker.WINDOWS_BIOS_PROGRAMS`. The ntfs-3g variants of the T0 tests are skipped when `ntfs-3g` is missing. The QEMU boot tests are skipped unless `BMK_QEMU=1` is set; with `BMK_QEMU=1`, a missing `qemu-system-x86_64`/`qemu-system-i386` is a skip, or an error under `BMK_INTEGRATION_REQUIRED=1`.

The worker itself additionally needs `lsblk`, `blockdev`, `findmnt`, `udevadm`, `partprobe`, `blkid`, `7z` and a working NTFS mount (kernel `ntfs3` or `ntfs-3g`); a missing one is reported as a test error, not a skip.

What the tests do:

- **RAW (`test_loop_raw.py`):** a 128 MiB image with an old two-partition GPT (ext4 on the first partition) is attached with `losetup --partscan`; a 40 MiB pseudo-random image with an MBR is written with `write_raw` and read-back verification. The test compares the written bytes with the source (`cmp`), checks that `wipefs` finds neither the primary nor the backup GPT signature (only the source's `dos` table), and that the kernel dropped the stale second partition. A second test keeps a stale partition open exclusively during the write; `wipefs` then fails without `--force`, so the test notices if that flag is dropped.
- **Windows (`test_loop_windows.py`):** a directory with the essential Windows Setup file names is bind-mounted in place of an ISO (`worker.mount_iso` and `worker.read_iso_volume_label` are replaced), and `write_windows_uefi` runs with SHA-256 verification on a 384 MiB image. The test checks the GPT (`sfdisk --json`: two Microsoft Basic Data partitions, the second named `BMK_EFI` with `GUID:63`), the NTFS label, the FAT label and the SHA-256 of every copied file. The pinned UEFI:NTFS image is taken from `BMK_UEFI_NTFS_IMAGE`, from the installed copy, or downloaded and verified with `fetch_uefi_ntfs.py`.

- **Windows Legacy BIOS (`test_loop_windows_bios.py`):** both groups use a test `bootmgr`: a few bytes of 16-bit real-mode code that writes `BMK-BOOT-OK` to the QEMU debug port (`0xE9`) and halts. With `BMK_QEMU=1` the image boots in `qemu-system-x86_64 -machine pc` (SeaBIOS, TCG, `snapshot=on`) and the test waits up to 60 s for that text; on failure it prints the GRUB and QEMU versions, the SeaBIOS log, the VGA text screen and, at a `grub>` prompt, the output of read-only GRUB commands.
  - `LoopWindowsBiosFeasibilityTests` (the T0 gate) builds the media itself, without the production writer: MBR with one active type-7 partition, NTFS with the production geometry, the kernel `ntfs3` or `ntfs-3g` driver, `grub-install --target=i386-pc` without `--force`, and a `grub.cfg` that runs `ntldr /bootmgr`. It checks the `55 AA` signature, non-empty MBR boot code, `core.img` in the gap before the partition, the unchanged partition table, the GRUB modules, and that the host's `/boot/grub` did not change. It stays as a writer-independent reference, so a GRUB or distribution change can be told apart from a writer bug.
  - `LoopWindowsBiosWriterTests` runs `write_windows_bios` with SHA-256 verification on a 256 MiB image; a directory with mixed-case Windows Setup file names (no EFI loader) is bind-mounted in place of the ISO. It checks `sfdisk --json` (`dos`, one active type-`7` partition from sector 2048 with the size `calculate_mbr_layout` gives), the NTFS label, the same static MBR checks, `grub/grub.cfg` against `worker.BIOS_GRUB_CFG`, the SHA-256 of every copied file and that only `/grub` was added, that no mount or `/run/bootmediakit-*` directory is left, and that the host's `/boot/grub` did not change. A second test first writes the image with `write_windows_uefi`, then with `write_windows_bios`, and checks that neither `wipefs` nor a direct read finds the primary or the backup GPT header. A third boots the written image in QEMU.

The loop device is a stand-in: `tests/integration/loop_helpers.py` makes `worker.lsblk_tree` report exactly the test's loop device as a removable `disk`. `validate_target` and every other safety check run unmodified. This substitution exists only in the test helper.

Known limits and problems:

- If the kernel or udev does not create the partition nodes (`/dev/loopNp1`, …) within 20 seconds, the test **fails** with a message pointing here; it does not pass silently. This happens in containers without udev and with kernels that have no partition-table parsers. Run the tests on a normal host or VM, or make sure `udevadm settle` works and `/dev` is a devtmpfs.
- These tests are not a substitute for physical USB tests. They give no evidence about partitions actually *used* by the kernel (mounted, swap, LUKS), about USB-specific properties (`rm`, `tran=usb`), about firmware boot, or about Windows Setup. The QEMU boot only shows that SeaBIOS, GRUB and the `ntldr` chainload reach a test `bootmgr`; it says nothing about the real Windows Boot Manager or Setup.

### Manual QEMU boot check of a finished USB drive

Before rebooting a physical computer, a finished Windows Legacy BIOS drive can be booted in QEMU with SeaBIOS. The check below never writes to the drive: QEMU runs as your normal user with **read-only** access to the device, and `snapshot=on` sends the guest's writes to a temporary file. (`readonly=on` is not used because QEMU refuses read-only IDE disks: "Block node is read-only".)

1. Plug in the drive, do not mount it, and find its device name (`/dev/sdX` below) by size, model and `TRAN` = `usb`:

   ```bash
   lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS
   ```

2. Give your user read-only access to that device node. The entry disappears when the drive is unplugged. This only limits QEMU if your user is not in the `disk` group (check with `id -nG`); members of that group can already write to every disk, so do not run the check from such an account:

   ```bash
   sudo setfacl -m u:"$USER":r /dev/sdX
   ```

3. Boot it in QEMU (`-machine pc` uses SeaBIOS, i.e. Legacy BIOS):

   ```bash
   qemu-system-x86_64 -machine pc -accel kvm -cpu host -m 4096 -drive file=/dev/sdX,format=raw,if=ide,snapshot=on -boot c
   ```

   Without KVM use `-accel tcg -cpu max` instead of `-accel kvm -cpu host`; Windows Setup is then very slow. Expected result: the Windows Setup screen appears. Close the QEMU window there; do not install. Do not use the QEMU monitor's `commit` command (or `Ctrl-A s`), which would try to write the temporary changes back.

4. Remove the access entry (or unplug the drive):

   ```bash
   sudo setfacl -x u:"$USER" /dev/sdX
   ```

The same QEMU command shows that the drive does **not** boot in UEFI mode if `-machine pc` is replaced by `-machine q35 -bios /usr/share/edk2/x64/OVMF.4m.fd` (Arch package `edk2-ovmf`; the firmware path can differ between distributions). Neither check replaces a test on the real computer.

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
