# Development log

## 2026-11-01 — 0.1.1-alpha repository baseline

- Project identity changed from the internal name CachyUSB to BootMediaKit.
- The repository baseline is the 0.1.1-alpha source snapshot.
- The Windows ESD conversion and WIM splitting work is part of this baseline.
- The GUI uses a scrollable content area.

## 2026-11-01 — 0.1.2-alpha UEFI:NTFS implementation (development branch)

- Replaced the Windows GPT/FAT32 writer with a two-partition GPT/NTFS + FAT helper layout.
- The large partition is GPT Microsoft Basic Data and is formatted NTFS. The NTFS volume receives the correct partition-start sector.
- The 1 MiB helper partition is placed after the NTFS partition at the end of the disk. It is Microsoft Basic Data (not GPT EFI System) with NoDriveLetter GUID:63, and both its GPT name and FAT volume label are BMK_EFI. The pristine, verified upstream image is copied to a temporary file and only its FAT volume label is changed; the signed EFI binaries remain untouched.
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


## 2026-11-02 — Windows Setup duplicate-ESP compatibility fix

The user confirmed that the 0.1.2 UEFI:NTFS USB boots into Windows Setup but fails during next-phase system-volume preparation. Review found that the 1 MiB FAT UEFI:NTFS helper partition had been incorrectly assigned the GPT EFI System Partition type.

Rufus's source explicitly warns not to declare the UEFI:NTFS helper partition as an ESP on GPT media: Windows Setup may fail when it sees two ESPs on one system. Rufus instead uses Microsoft Basic Data for the helper and sets GPT_BASIC_DATA_ATTRIBUTE_NO_DRIVE_LETTER (GUID-specific attribute bit 63).

BootMediaKit now follows that layout and reads the GPT back after creation to validate the two partition ranges, Microsoft Basic Data types, and GUID:63 NoDriveLetter attribute. The FAT helper still contains the upstream UEFI:NTFS boot image and is intended for the removable-media UEFI boot path; it is deliberately not declared as a second GPT ESP. This fix is strongly supported by the Rufus source and the user's Windows Setup failure, but must still be confirmed by the same-PC physical test.


## 2026-11-02 — BMK_EFI volume branding and 0.1.2 physical validation

The upstream FAT image in the pinned Rufus commit carries the FAT volume label RUFUS_BOOT. The project does not want that identifier exposed on user-created media. The worker now uses dosfstools fatlabel on a temporary copy of the pristine, size/SHA-1/SHA-256-verified upstream image to change only the FAT volume label to BMK_EFI. The GPT partition name is also BMK_EFI. The original downloaded image is left unchanged; the actual written helper partition is read back by SHA-256 and the BMK_EFI label is checked with fatlabel.

The installer now explicitly installs dosfstools. CI exercises the real fatlabel command on a temporary copy of the pinned helper image. The user has tested the updated Windows UEFI:NTFS path on the Samsung RV511: Windows Setup read the installation source, copied files, passed the first reboot and continued from the internal 120 GB SSD. The user also reports substantial speed improvement on two USB 2.0 devices after the NTFS3 and kernel-copy changes. Linux raw/DD MBR/Legacy testing is reported successful.


## 2026-11-03 — 0.1.3-safety-alpha P0 security hardening

Created `dev/0.1.3-safety-alpha` from the UI development branch; the released `main` / 0.1.2 branch remains unchanged.

- Added GUI-to-worker cooperative cancellation over the worker standard input. A dedicated daemon reader watches for `cancel`; disk/file copy and verification loops check a shared event at chunk boundaries. Completed writes are fsynced on cancellation and normal cleanup runs; no forced process kill is used.
- Added a fixed root-owned libexec shell launcher using `/usr/bin/python3 -I` and a dedicated `org.bootmediakit.write` Polkit action bound with `org.freedesktop.policykit.exec.path`.
- Worker checks the installed path, root ownership, non-symlink status and absence of group/world write permission for the worker, wrapper, policy and installation directories. Direct root execution from a user-writable checkout is rejected.
- GUI snapshots the target's size, model, serial/WWN, transport, major:minor, sysfs diskseq and by-id identity. Worker compares this snapshot at operation start and again at the destructive boundary.
- RAW keeps its source fd open and checks the filesystem's block-device ancestry via `findmnt` / `lsblk` before unmounting/wiping. The Windows writer performs the same source/target collision check before writing.
- Protected-device resolution includes system mount backing devices and active swap devices / swap-file backing files. Targets containing LUKS, LVM, RAID or swap metadata are rejected instead of being automatically dismantled.
- Confirmation shows all discovered partitions, filesystem types, labels, sizes and mountpoints. Large (>=128 GiB) or non-removable USB devices require a second confirmation.
- Authorization/worker-start failures are shown as non-destructive; the GUI uses worker events to decide whether the target may be partial.
- Worker block-device parsing uses `lsblk --json`; this removes the whitespace-splitting problem when TRAN is empty.
- Added P0 security and policy-packaging tests; latest CI passes 59 tests.

Physical validation is still pending. CI does not exercise a real Polkit agent, real block-device hot-swap race, or cancellation while writing to physical USB media. Test first with a disposable device on CachyOS; never use the user's backup HDD or a disk containing the source ISO.


## 2026-11-03 — Safety Alpha UI feedback follow-up

- Long ISO metadata now wraps and the scroll area never displays a horizontal scrollbar. The root content, path entry, device combo, detail labels, mode buttons, log and footer now allow the viewport to constrain their width.
- Muted text no longer uses the host theme's potentially too-dark `palette(mid)` color; device details use an explicit light grey for readable contrast under dark KDE palettes.
- The exact `0.1.3-safety-alpha` string is shown directly below the BootMediaKit name in a small blue secondary label.
- Removed the user-visible log entry that described the UEFI helper image's source FAT label and its replacement. The internal verification of the upstream `RUFUS_BOOT` metadata and the temporary-copy relabel to `BMK_EFI` remain unchanged; actual device labels remain `BOOTMEDIA` and `BMK_EFI` in this writer version.
- The cross-filesystem `copy_file_range` / `sendfile` fallback is expected on some source/destination filesystem pairs. It no longer prints raw `[Errno 18] Invalid cross-device link`; the log now explains that a compatible copy method is being used. The fallback and the write path were not changed, preserving current reported transfer performance.
- Added tests for horizontal-overflow prevention, visible version/high-contrast metadata, quiet helper-label handling and benign EXDEV fallback diagnostics.
