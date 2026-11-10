# Changelog

## Unreleased

- Tests: T0 feasibility gate for the Legacy BIOS/MBR Windows mode. A loop-device integration test builds an MBR disk with one active NTFS partition, runs `grub-install --target=i386-pc` (no `--force`) and chainloads a test `bootmgr` with `ntldr /bootmgr`; with `BMK_QEMU=1` it boots the image in QEMU/SeaBIOS and waits for `BMK-BOOT-OK` on the debug port (T0).
- CI: installs `grub-pc-bin`, `grub2-common` and `qemu-system-x86`, and runs the integration tests with `BMK_QEMU=1` (T0).

## 0.2.2 — 2026-11-10

Maintenance release: no new features, no change to the write sequence or to the Windows-mode GPT layout.

- Source filesystem check: the rejection message now names the filesystem type and source and tells the user to copy the ISO to a local block-device-backed disk. `virtiofs`, `vboxsf`, `fuse.sshfs`, `fuse.rclone`, `fuse.gvfsd-fuse` and `fuse.portal` sources are accepted as network/virtual filesystems that cannot be on the target; `fuseblk` still resolves to its block device; `overlay`, `zfs` and unknown types stay rejected (T1).
- Multi-device Btrfs sources: every member listed under `/sys/fs/btrfs/<UUID>/devices/` now takes part in the source/target collision check; an unreadable member list stops the operation (T2).
- GUI: an unchanged `lsblk` error during automatic device refresh is logged once instead of every 5 seconds; it may be logged again after a successful refresh. Manual refresh still shows the dialog (T3).
- Tests and README: a GUI pipe that breaks during a Windows-mode or RAW write is now covered by regression tests (safe stop at the next cancellation point, cleanup, exit code 130), and the Safety section documents that the USB drive may be left partially written (T4).
- Single version source: new `version.py`, read by the GUI and by the UEFI:NTFS fetcher and installed by `install.sh`; packaging tests keep the READMEs, `CHANGELOG.md` and `docs/TESTING.md` in step with it. The privileged worker does not import it (T5).
- CI: `shellcheck -S warning` on the installer, uninstaller and worker wrapper (T6).
- CI and tests: loop-device integration tests in `tests/integration/` run the real RAW and Windows writers as root against a disk image (stale GPT cleanup, byte-exact RAW write, GPT layout, NTFS/FAT labels, copied-file SHA-256). They are opt-in with `BMK_INTEGRATION=1` and are skipped otherwise (T7).
- Documentation: test commands in the READMEs, `CONTRIBUTING.md` and `docs/TESTING.md` match CI; integration test usage and skip conditions are documented; the 0.2.2 work description is part of `ROADMAP.md` (T8).

## 0.2.1 — 2026-11-05

BootMediaKit 0.2.1 is the first stable release of the 0.2.x line. This release concentrates on disk-write safety, reliability under failure and cancellation, GUI lifecycle stability, and regression coverage. It retains the Arch Linux family as its initial supported platform.

### Reliability and disk safety

- Resolve source/target disk relationships through stacked mounts, autofs/CIFS mount layers and Btrfs subvolumes; reject ambiguous backing-device information instead of guessing.
- Strengthen whole-disk unmount verification before destructive RAW writing.
- Keep stale filesystem/partition signature cleanup ahead of the raw image write and add regression coverage for the command ordering.
- Handle broken GUI/worker event pipes safely and avoid duplicate error reporting.
- Avoid unnecessary disk flushes during cancellation cleanup.
- Flush block-device buffers before UEFI:NTFS helper read-back verification.

### GUI and compatibility

- Discover USB devices asynchronously through Qt's process interface, with a timeout and protection against overlapping refresh requests.
- Shut down Qt widgets and child processes explicitly to avoid interpreter-finalization crashes.
- Remove an SVG filter primitive unsupported by Qt's SVG renderer.
- Preserve the existing screen-aware layout, visible version information, operation timer and compact device-information presentation.

### Validation

- GitHub Actions automated checks passed on the final 0.2.1 source branch: [workflow run 41980736701](https://github.com/rsanya87/bootmediakit/actions/runs/41980736701).
- Linux Mint 22.3 Cinnamon DD/RAW media was physically confirmed to boot in both UEFI and Legacy BIOS/MBR modes.
- Windows 10 and Windows 11 IoT Enterprise LTSC x64 installation media were physically tested; installation completed successfully on the tested system(s).
- The latest standard Windows 11 26H2 x64 ISO reached the Windows Setup disk-selection/partitioning screen with Secure Boot both disabled and enabled. Installation beyond that screen was not completed, so this is not recorded as a full installation test.
- Secure Boot behavior was therefore observed on the tested firmware, but broad compatibility across different firmware implementations is not claimed.

## 0.1.3 — 2026-11-03

BootMediaKit 0.1.3 is the first stable release of the Arch/CachyOS implementation.

### Windows UEFI and Linux RAW/DD

- Create Windows x64 UEFI installation media on GPT with a large NTFS partition and a 1 MiB FAT UEFI:NTFS helper partition at the end of the USB drive.
- Preserve the original Windows ISO volume ID as the first GPT partition name and NTFS volume label. Use `BOOTMEDIA` only as a fallback when the ISO does not expose a usable label. Keep `BMK_EFI` exclusively for the helper partition.
- Keep `install.esd`, `install.wim` and all other Windows files unchanged; no ESD-to-WIM conversion or SWM splitting.
- Retain the Microsoft Basic Data + NoDriveLetter GUID:63 metadata for the FAT helper partition, preventing Windows Setup from seeing a second EFI System Partition.
- Verify the pinned upstream UEFI:NTFS helper image by size and cryptographic hashes; alter only a temporary copy's FAT volume label, not the signed EFI binaries.
- Prefer kernel NTFS3 and kernel-assisted file copying, with ntfs-3g and buffered-copy fallbacks. Hide expected cross-filesystem `EXDEV` fallbacks from the error log.
- Support direct Linux ISO/RAW/DD writing with optional full read-back verification.

### Safety and reliability

- Add a dedicated root-owned worker wrapper and BootMediaKit-specific Polkit action; run Python in isolated mode and keep the GUI unprivileged.
- Revalidate target device identity and reject source images stored on the target physical disk.
- Protect system and swap backing devices; reject LUKS, LVM, RAID and swap target layouts.
- Add cooperative cancellation at safe write boundaries, flushing completed write units and performing normal cleanup.
- Show a detailed destructive confirmation, including partitions, filesystems, labels, sizes and mountpoints; require a second confirmation for large or non-removable USB devices.
- Use structured `lsblk --json` output and distinguish authorization failures from operations that may have modified the target.

### User interface

- Add BootMediaKit application icon, visible version label and elapsed operation timer.
- Use a screen-aware compact layout capped at 740×900 logical pixels without reducing the 10 pt UI font.
- Display partition details in a compact hover information tooltip.

### Validation

- User-tested Linux DD/RAW media booted in both Legacy BIOS and UEFI modes.
- User-tested Windows 10 IoT Enterprise LTSC 2021 x64 in UEFI mode through successful installation.
- User-tested cooperative cancellation on physical USB media.
- Automated GitHub Actions suite: see the release workflow run linked from the repository.

## 0.1.2 — 2026-11-02

### Windows UEFI media rewrite

- Replace the single GPT/FAT32 Windows USB layout with a GPT layout containing a large NTFS Basic Data partition and a 1 MiB FAT UEFI:NTFS helper partition at the end of the device.
- Mark the helper partition as Microsoft Basic Data, not EFI System Partition, and set GPT NoDriveLetter (GUID:63), avoiding the Windows Setup multiple-ESP issue.
- Set both the GPT helper-partition name and FAT volume label to `BMK_EFI`; change only a temporary copy of the verified upstream FAT image, preserving the pristine source and signed EFI binaries.
- Use the Rufus UEFI:NTFS helper image from a pinned upstream Rufus commit, with file-size, Git blob SHA-1 and SHA-256 verification.
- Read back and verify the written UEFI:NTFS helper image before continuing.
- Keep the original Windows `install.esd` / `install.wim` file unchanged; remove the ESD-to-WIM conversion and SWM splitting from the Windows path.
- Add optional full SHA-256 verification of copied Windows ISO files (off by default in Windows mode to avoid an unnecessary second full USB read).
- Preflight the ISO, the target geometry, helper image, and capacity before erasing the target device.
- Format NTFS with the correct partition-start sector required for Windows boot; explicitly set conventional 255/63 BPB geometry and 4 KiB clusters, then validate the NTFS boot sector signature and geometry before copying files.
- Prefer kernel NTFS3 for writing the USB payload, with ntfs-3g fallback.
- Use best-effort kernel `copy_file_range`, then `sendfile`, when hashing is disabled, with transparent streaming fallback if both cross-filesystem paths are unsupported.
- Throttle progress output and sync only the target USB filesystem.
- Scale the copy progress bar to the selected verification mode: without SHA-256 the copy itself reaches 96%; when verification is enabled, space is reserved for the second pass.
- Replace per-file fsync calls with one batched sync; optionally drop clean cached pages before SHA-256 read-back.
- Add tests for GPT layout, partition identifiers, ISO structure scanning, NTFS BPB geometry, copy_file_range fallback, progress throttling, mount-driver fallback and SHA-256 verification.
- Update Arch dependencies (`ntfsprogs`, `dosfstools`) and fetch/verify the pinned upstream UEFI helper image.
- Record the upstream helper components and their separate source/license references in `THIRD_PARTY_NOTICES.md`.

### Validation status

The user tested Windows 10 IoT Enterprise LTSC 2021 x64 media on the same Samsung RV511: Windows Setup copied files, passed the first reboot, and continued from the internal SSD to the next installation phase. Two USB 2.0 devices showed a substantial speed improvement after the NTFS3/kernel-copy optimizations. Linux raw/DD mode was also tested in Legacy/MBR mode. Secure Boot and broader hardware/ISO coverage remain future validation items.

## 0.1.1-alpha — 2026-11-01

- Baseline import of the original BootMediaKit GUI, raw writer and Windows FAT32/SWM workflow.
- ESD conversion to WIM and SWM splitting.
- Scrollable GUI and Arch-based installation.
