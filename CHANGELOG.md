# Changelog

## 0.1.2-alpha — 2026-11-02 (development branch)

### Windows UEFI media rewrite

- Replace the single GPT/FAT32 Windows USB layout with a GPT layout containing a large NTFS Basic Data partition and a 1 MiB FAT EFI System Partition at the end of the device.
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
- Update the Arch installer to include the split `ntfsprogs` package and fetch the pinned UEFI helper image.

### Important status

This is an alpha test build. The previous 0.1.1-alpha Windows Setup failure is still open until a real UEFI boot and Windows Setup run on the reported target PC confirms the fix. No stable release is being declared.

## 0.1.1-alpha — 2026-11-01

- Baseline import of the original BootMediaKit GUI, raw writer and Windows FAT32/SWM workflow.
- ESD conversion to WIM and SWM splitting.
- Scrollable GUI and Arch-based installation.
