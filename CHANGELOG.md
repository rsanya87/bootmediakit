# Changelog

## 0.1.3-safety-alpha — P0 security hardening

- Add a cooperative cancellation protocol between the unprivileged GUI and the privileged worker. The worker checks cancellation at safe chunk/file boundaries; it flushes completed write units and performs normal cleanup instead of being killed mid-write.
- Add a dedicated `org.bootmediakit.write` Polkit action bound to a fixed root-owned `/usr/libexec/bootmediakit/bootmediakit-worker` wrapper. The wrapper launches Python with isolated mode (`-I`).
- Refuse root worker execution from a source checkout or any installation with non-root-owned or group/world-writable worker, wrapper, policy or installation directories.
- Snapshot and revalidate target identity (size, model, serial/WWN, major:minor, diskseq and `/dev/disk/by-id` where available) immediately before destructive operations.
- Reject RAW or Windows source images stored on the target physical disk before unmounting or wiping it.
- Protect physical devices backing system mountpoints and active swap (including swap files); refuse targets containing LUKS, LVM, RAID or swap layers.
- Display target partitions, filesystem types, labels, sizes and mountpoints in the destructive confirmation; require a second confirmation for large or non-removable USB devices.
- Distinguish Polkit authorization/worker-start failures from actual write failures; do not claim the target may be partial if the worker never started.
- Replace worker field splitting with structured `lsblk --json` parsing, also fixing empty-transport column shifts.
- Add P0 safety and packaging tests; current CI runs 59 tests.

**Validation limitation:** CI verifies static rules, packaging and unit behavior. The installed Polkit agent, real device-swap race, source-on-target rejection against actual hardware, and cancellation on a disposable physical USB drive still require CachyOS testing.


## 0.1.3-alpha — UI refinement

- Reduce default window size and compact panel padding/spacing without shrinking the standard 10 pt UI font.
- Place raw-image and Windows installer mode buttons side by side.
- Add a live elapsed-time display for the actual worker operation; authentication-dialog wait time is excluded.
- Replace the placeholder icon with an original BootMediaKit bootable USB mark for window, taskbar and application menu.
- Add elapsed-time formatting unit tests.


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
