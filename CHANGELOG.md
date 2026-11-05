# Changelog

## 0.2.1 — 2026-11-05 (Release Candidate 1)

BootMediaKit 0.2.1 focuses on reliability, device-safety checks, GUI lifecycle stability and regression coverage. This is a release candidate, not the final public release.

### Reliability and safety

- Resolve source/target disk relationships through stacked mounts, autofs/CIFS mount layers and Btrfs subvolumes; reject ambiguous backing-device information instead of guessing.
- Strengthen whole-disk unmount verification before destructive RAW writing.
- Keep stale filesystem/partition signature cleanup ahead of the raw image write and add a regression test for its command ordering.
- Handle broken GUI/worker event pipes safely and avoid duplicate error reporting.
- Avoid unnecessary disk flushes during cancellation cleanup.
- Flush block-device buffers before UEFI:NTFS helper read-back verification.

### GUI and compatibility

- Discover USB devices asynchronously through Qt's process interface, with a timeout and protection against overlapping refresh requests.
- Shut down Qt widgets and child processes explicitly to avoid interpreter-finalization crashes.
- Remove an SVG filter primitive unsupported by Qt's SVG renderer.

### Validation status for RC1

- The GitHub Actions suite passed on the RC1 commit in the `release/0.2.1-rc1` branch: [run 41980555416](https://github.com/rsanya87/bootmediakit/actions/runs/41980555416).
- Linux Mint 22.3 Cinnamon DD/RAW media was physically boot-tested successfully after the latest RAW-writer update.
- Windows x64 UEFI media must be retested on the RC build before final release.
- Secure Boot, additional Windows ISO families and additional Linux distributions remain outside the verified release scope.

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
