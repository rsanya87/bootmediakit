# Development log

## 2026-11-01 — 0.1.1-alpha repository baseline

- Project identity changed from the internal name CachyUSB to BootMediaKit.
- The repository baseline is the 0.1.1-alpha source snapshot.
- The Windows ESD conversion and WIM splitting work is part of this baseline.
- The GUI uses a scrollable content area.

## 2026-11-01 — 0.1.2-alpha UEFI:NTFS implementation (development branch)

- Replaced the Windows GPT/FAT32 writer with a two-partition GPT/NTFS + FAT helper layout.
- The large partition is GPT Microsoft Basic Data and is formatted NTFS. The NTFS volume receives the correct partition-start sector.
- The 1 MiB helper partition is placed after the NTFS partition at the end of the disk and has the GPT EFI System type. The verified upstream UEFI:NTFS image is copied there byte-for-byte.
- The UEFI helper is fetched by an installer script from a pinned Rufus source commit. The downloader checks the exact file size, Git blob SHA-1 and SHA-256; the writer checks the same image and verifies the partition after writing.
- Windows ISO content is copied without converting or splitting `install.esd` / `install.wim`.
- The source files are hashed during copy when full verification is selected; the UI offers a complete SHA-256 read-back verification, off by default in Windows mode to avoid a second full pass over slow USB media.
- Added layout and copy/verification unit tests.
- The user-reported 0.1.1 Windows Setup error remains unresolved until a new physical USB boots on the same target PC and Windows Setup can read the source.

## Upstream implementation references

- Rufus embeds the FAT UEFI:NTFS partition image under `res/uefi/uefi-ntfs.img`.
- Upstream source is pinned to Rufus commit `acf7de640848ab249bedeb6feb59b33001f656b6`.
- Image Git blob SHA-1: `ac50eed9730af847c43c145a5c17678f54128b33`.
- Image SHA-256: `72683fa1250eeea772d3399277b434d4e55ba8dd0dc926e52d817e701fc2eb9e`.
- Image SHA-256: `72683fa1250eeea772d3399277b434d4e55ba8dd0dc926e52d817e701fc2eb9e`.
- Image size: 1,048,576 bytes.
- The image README describes UEFI:NTFS loader 2.8 and NTFS UEFI drivers 1.9, plus additional EfiFs drivers. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## User-reported failure that motivated 0.1.2

A Windows 10 IoT Enterprise LTSC 2021 x64 ISO (Hungarian, October 2025 integrated image) was written using BootMediaKit 0.1.1-alpha with GPT/FAT32 and ESD-to-WIM conversion/SWM splitting. On the target PC, Windows Setup displayed the “required media driver is missing” dialog. The same ISO reportedly proceeds correctly when prepared by Rufus on the same PC.

This is a confirmed failure report for one ISO/device/firmware combination. The 0.1.2 architecture addresses the 4 GiB FAT32 limitation and uses the same general UEFI:NTFS layout as Rufus, but the exact failure is not considered resolved until a real device boot test passes.


## 2026-11-02 — USB write performance follow-up

The user's physical test showed that a Windows USB on two USB 2.0 sticks took approximately 45 minutes, considerably slower than Rufus. Code inspection found two avoidable costs in the 0.1.2 writer:

- The previous copy loop called `fsync()` after every individual ISO file. This can be extremely slow on inexpensive flash drives. The revised code flushes the file stream normally and performs one batched `sync` after the tree is copied.
- The writer used the userspace FUSE `ntfs-3g` driver unconditionally. The revised code prefers the in-kernel `ntfs3` driver and falls back to `ntfs-3g` only if NTFS3 cannot mount the volume.

The optional SHA-256 read-back pass reads the entire Windows payload a second time. It is now off by default in Windows mode to reduce creation time, but can be enabled by the user. If enabled, the writer syncs before verification and requests eviction of clean file-cache pages before the read-back pass.

The real USB speed test remains outstanding. The target user's measured creation time should be recorded after this optimization on the same 8 GB USB 2.0 sticks.


## 2026-11-02 — Dynamic progress bar

The user noticed that Windows file copy completed around 85% and jumped towards completion even when the optional full SHA-256 read-back was disabled. The copy progress range is now calculated from the selected mode: copy reaches 96% with verification disabled; with verification enabled it ends at 85% and the second full read-back pass uses the remaining progress range. Added unit tests for both ranges.


## 2026-11-02 — Windows boot and copy-path review

A second review of the current `dev/0.1.2-alpha` branch identified additional validation and performance improvements:

- The NTFS formatter now receives an explicit partition-start sector, 512-byte sector size, 255 heads, 63 sectors per track and 4096-byte clusters. The generated NTFS boot sector is read back and checked for OEM ID, sector size, cluster geometry, HiddenSectors, geometry and the 0x55AA marker.
- When full SHA-256 read-back is disabled, the file copier attempts Linux `copy_file_range` for kernel-assisted copies. Unsupported cross-filesystem combinations fall back to streaming I/O without losing bytes. Hash-enabled copies continue to stream and calculate the source SHA-256 at the same time.
- Progress events are throttled to percentage changes.
- The writer uses `sync --file-system <USB mountpoint>` instead of flushing every mounted filesystem on the computer.
- The final cleanup now attempts to unmount the USB even if a targeted sync fails.

### User's Windows Setup log — interpretation

The user confirmed that the Windows installation target is a separate 120 GB SSD. The log also enumerates a WDC WD3200BEVT 320 GB HDD as another internal disk; this secondary disk is not the chosen installation target and its first area is intentionally left unused due to a bad sector region.

The photographed log includes:
- `GetMachineInfo: Couldn't find info for boot disk [2]`
- repeated `CanBeSystemVolume` blocks for candidate disk regions
- `PrepareSystemVolume: Failed to prepare boot disk and system volume`
- The WDC WD3200BEVT appears as another enumerated disk (disk 1 in the photographed DiskInfo section).

This resembles a known Windows Setup failure pattern where Windows PE misidentifies the system/boot disk when several internal HDDs/SSDs are present. This is not yet proven to be the root cause on this laptop. The next safe diagnostic is to verify the 120 GB SSD's disk number and GPT status using `diskpart list disk`, then repeat the install with the non-target WDC HDD temporarily disconnected. Do not clean or format the secondary HDD for this test.

See [Microsoft UEFI/GPT partition guidance](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/configure-uefigpt-based-hard-drive-partitions?view=windows-11) and the Windows Setup multiple-disk diagnostic case documented in the issue discussion. The user must still confirm the same-machine physical installation test before the 0.1.2 PR can be merged.


The copy fast path now tries `copy_file_range` first. On cross-filesystem errors such as `EXDEV`, it tries Linux `sendfile` before falling back to the buffered stream loop. The GitHub Actions runner exercises the cross-filesystem fallback path; actual ISO9660-loop to USB-NTFS3 throughput still has to be measured on the user's CachyOS system.
