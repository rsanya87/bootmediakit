# Roadmap

This roadmap separates confirmed capabilities from planned work. A feature is not considered complete until its automated checks and relevant real-device tests are documented.

## 0.1.2-alpha — Windows installation reliability

**Priority: blocking issue**

- [ ] Reproduce the Windows Setup “required media driver is missing” dialog with the reported Windows 10 IoT Enterprise LTSC 2021 x64 ISO.
- [ ] Record the exact USB partition table, filesystem, volume labels, file list, file sizes, and boot mode created by BootMediaKit.
- [ ] Compare those details against a working Rufus-created USB from the same ISO and target PC.
- [ ] Verify that all `install*.swm` parts are present, named correctly, contiguous, and accepted by Windows Setup.
- [ ] Check setup-source accessibility after boot (drive letter, `sources` directory, `boot.wim` and install image availability).
- [ ] Evaluate a Rufus-like UEFI:NTFS implementation or a dual-partition FAT32+NTFS Windows layout.
- [ ] Do not remove the existing FAT32/SWM path until an alternative passes real UEFI/Windows Setup tests.
- [ ] Add regression tests for every confirmed failure mode.
- [ ] Add optional read-back verification for Windows file-copy mode.

## Stabilize the Arch/CachyOS line

- [ ] Validate raw image writing with multiple Linux hybrid ISOs.
- [ ] Validate Windows UEFI media creation across at least two Windows ISO families and two USB devices.
- [ ] Test cancellation, write failures, insufficient space, USB removal, and polkit denial.
- [ ] Improve device hot-plug detection and device identity display.
- [ ] Test scaled KDE/Qt displays and smaller window sizes.
- [ ] Provide reproducible test logs and release checksums.

## Later distribution support

The project will target one distribution family at a time, after the Arch/CachyOS workflow is stable.

1. Arch Linux family (CachyOS first) — current development target.
2. Debian and Ubuntu — planned; needs package mapping, install/uninstall support, and tests on both.
3. Fedora — planned; needs RPM/DNF dependency and packaging work.

The UI and writing logic should remain distribution-neutral. Package installation, dependency detection, desktop integration, and polkit setup should be implemented in separate distribution adapters.

## Longer-term ideas

- MBR/Legacy BIOS Windows media.
- NTFS and UEFI:NTFS support.
- Windows To Go and FreeDOS.
- Linux persistence.
- USB device health/capacity tests.
- Image checksums and signature verification.
- Optional ISO download/catalog support.
- More flexible formatting options.
