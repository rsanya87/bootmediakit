# Changelog

## 0.1.2-alpha — 2026-11-01 (development branch)

### Windows UEFI media rewrite

- Replace the single GPT/FAT32 Windows USB layout with a GPT layout containing a large NTFS Basic Data partition and a 1 MiB FAT EFI System Partition at the end of the device.
- Use the Rufus UEFI:NTFS helper image from a pinned upstream Rufus commit, with file-size and Git blob SHA-1 verification.
- Read back and verify the written UEFI:NTFS helper image before continuing.
- Keep the original Windows `install.esd` / `install.wim` file unchanged; remove the ESD-to-WIM conversion and SWM splitting from the Windows path.
- Add full optional SHA-256 verification of the copied Windows ISO files (enabled by default).
- Preflight the ISO, the target geometry, helper image, and capacity before erasing the target device.
- Format NTFS with the correct partition-start sector required for Windows boot.
- Add tests for GPT layout, partition identifiers, ISO structure scanning, copy manifests and SHA-256 verification.
- Update the Arch installer to include the split `ntfsprogs` package and fetch the pinned UEFI helper image.

### Important status

This is an alpha test build. The previous 0.1.1-alpha Windows Setup failure is still open until a real UEFI boot and Windows Setup run on the reported target PC confirms the fix. No stable release is being declared.

## 0.1.1-alpha — 2026-11-01

- Baseline import of the original BootMediaKit GUI, raw writer and Windows FAT32/SWM workflow.
- ESD conversion to WIM and SWM splitting.
- Scrollable GUI and Arch-based installation.
