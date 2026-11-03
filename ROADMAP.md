# Roadmap

A feature is complete only after automated checks and its relevant real-device tests are recorded.

## 0.1.3 — Stable Arch/CachyOS release

- [x] Linux ISOHybrid/DD writing verified in Legacy BIOS and UEFI modes.
- [x] Windows 10 IoT Enterprise LTSC 2021 x64 UEFI installation completed successfully on physical hardware.
- [x] Preserve the original Windows ISO volume ID on the large NTFS partition; keep `BMK_EFI` exclusive to the 1 MiB helper partition.
- [x] GPT Microsoft Basic Data + NoDriveLetter GUID:63 metadata for the UEFI:NTFS helper partition.
- [x] Verified pinned upstream UEFI:NTFS helper image; only the temporary copy is relabelled.
- [x] Safety checks, dedicated Polkit action, root-owned worker wrapper, target identity validation and cooperative cancellation.
- [x] Screen-aware compact GUI, custom icon, visible version, elapsed timer and partition information tooltip.
- [x] Automated unit, packaging and CI checks.
- [x] Close the original Windows Setup missing-media-driver issue (#2) after successful UEFI installation.

## 0.2.1-beta — Next development stage

The next development cycle will expand test coverage and prepare the project for wider use without changing the tested 0.1.3 writing workflow unnecessarily.

- [ ] Test ISO volume-label preservation with additional Windows ISO images, including labels with spaces and mixed case.
- [ ] Test more Windows versions and hardware/UEFI firmware combinations.
- [ ] Run dedicated Secure Boot enabled/disabled tests and document firmware-specific behavior.
- [ ] Exercise target hot-unplug/replug and source-on-target protection on disposable hardware.
- [ ] Add loop-device integration tests for GPT, NTFS, FAT and failure/cancellation cleanup.
- [ ] Add an Arch PKGBUILD and reproducible package checksums.
- [ ] Improve progress diagnostics and device compatibility reporting without slowing USB 2.0 writes.
- [ ] Evaluate Debian/Ubuntu support; keep distribution-specific dependency installation and Polkit setup separate from the writer.
- [ ] Evaluate Fedora support after Debian/Ubuntu packaging is designed.

## Later distribution and feature support

The project will target one distribution family at a time, after the Arch/CachyOS workflow remains stable.

1. Arch Linux family (CachyOS first) — current stable target.
2. Debian and Ubuntu — planned, after dependency mapping, installer/uninstaller adapters and tests.
3. Fedora — planned, after RPM/DNF packaging and tests.

The GUI and writing logic should remain distribution-neutral. Package installation, dependency detection, desktop integration and Polkit setup should be separate distribution adapters.

## Longer-term ideas

- Windows Legacy BIOS/CSM media.
- Windows To Go and FreeDOS.
- Linux persistence.
- USB device health/capacity tests.
- Image checksums and publisher-signature verification.
- Optional ISO download/catalog support.
- More flexible formatting options.
