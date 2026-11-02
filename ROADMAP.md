# Roadmap

A feature is complete only after automated checks and its relevant real-device tests are recorded.

## 0.1.2-alpha — Windows UEFI:NTFS reliability

- [x] Replace the single-partition GPT/FAT32 layout with GPT + large NTFS partition + 1 MiB FAT EFI helper partition at the end.
- [x] Use the pinned Rufus UEFI:NTFS image with download-time hash verification.
- [x] Verify the helper image again before writing and read it back after writing.
- [x] Keep the original install.esd / install.wim unchanged.
- [x] Calculate the final GPT layout and check target capacity before erasing.
- [x] Create NTFS with the correct partition-start sector value.
- [x] Copy the original Windows ISO files and optionally verify every file using SHA-256.
- [x] Update Arch dependencies for the ntfs-3g / ntfsprogs package split.
- [x] Add automated tests for layout arithmetic, partition types, ISO structure, file verification, and NTFS driver fallback.
- [x] Prefer kernel NTFS3 and batch writes to improve low-end USB performance; retain ntfs-3g fallback.
- [x] Attempt kernel-assisted `copy_file_range`, then `sendfile`, when SHA-256 read-back is disabled; transparently fall back to buffered copying.
- [x] Sync only the USB filesystem and throttle progress output.
- [x] Set and validate NTFS BPB partition offset and CHS geometry.
- [x] Match Rufus's GPT UEFI:NTFS helper metadata: Microsoft Basic Data type plus NoDriveLetter GUID:63, avoiding a second ESP visible to Windows Setup.
- [x] Read back and verify the actual GPT type, partition geometry and no-drive-letter attribute before formatting/copying.
- [ ] Run the corrected 0.1.2 installer on CachyOS and confirm that the UEFI:NTFS helper image downloads and verifies.
- [ ] Measure 0.1.2 USB creation time on both of the user's USB 2.0 sticks and compare with Rufus; test SHA-256 read-back both off and on.
- [ ] Create a Windows 10 IoT Enterprise LTSC 2021 x64 USB on a disposable drive.
- [ ] Boot it on the same physical PC that failed with 0.1.1 and confirm Windows Setup can read the source without the missing-media-driver dialog.
- [ ] Test with Secure Boot enabled and disabled; document firmware-specific behavior.
- [ ] Compare the resulting partition layout and boot sequence with a Rufus-created USB.
- [ ] Only close GitHub issue #2 after the same-machine test passes.

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

The GUI and writing logic should remain distribution-neutral. Package installation, dependency detection, desktop integration and polkit setup should be separate distribution adapters.

## Longer-term ideas

- MBR/Legacy BIOS Windows media.
- Windows To Go and FreeDOS.
- Linux persistence.
- USB device health/capacity tests.
- Image checksums and signature verification.
- Optional ISO download/catalog support.
- More flexible formatting options.
