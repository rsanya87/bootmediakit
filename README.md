# BootMediaKit

BootMediaKit is an open-source Linux desktop application for creating bootable USB media from ISO and raw disk-image files. The interface is built with Python and PySide6. Disk-writing operations are delegated to a dedicated root-owned worker wrapper through a BootMediaKit-specific Polkit action. The GUI itself remains unprivileged.

**Version:** `0.2.2` (stable release, 2026-11-10)  
**Current platform target:** Arch Linux family (initial development and testing on CachyOS)  
**Application license:** GNU GPL-3.0-only

> 0.2.2 is a maintenance release: it adds no features and does not change the write sequence or the Windows-mode GPT layout. Its automated GitHub Actions checks passed, including loop-device integration tests of the real RAW and Windows writers. Physically re-validated for 0.2.2: Linux Mint 22.3 DD/RAW media written with read-back verification booted in UEFI and Legacy BIOS/MBR modes, including on a drive that previously carried the Windows-mode two-partition GPT; Windows 10/11 IoT Enterprise LTSC media was created with the expected partition names and booted. The complete Windows 10/11 IoT Enterprise LTSC installations and the standard Windows 11 26H2 Setup launch with Secure Boot enabled and disabled (to the disk-selection screen only) were verified on 0.2.1 and were not repeated in full. These results describe the tested configurations, not universal firmware compatibility. BootMediaKit is not a full Rufus feature replacement.

## Current capabilities

- Dedicated root-owned worker wrapper and Polkit action; the GUI itself never runs as root.
- Cooperative cancellation at safe write boundaries, without killing the privileged worker during I/O.
- Source/target physical-disk collision checks and a second target-identity validation immediately before destructive writes.
- Protection of system and active swap backing devices; refusal of targets containing LUKS, LVM, RAID or swap layers.
- Partition/filesystem/label details in the destructive confirmation, plus a second confirmation for large or non-removable USB devices.


- Screen-aware PySide6 interface capped at 740×900, with a compact laptop profile for 1366×768 displays while retaining the 10 pt font size.
- Live elapsed-time display for the actual USB creation operation.
- Original BootMediaKit application icon for the window, taskbar and application menu.
- Readable device metadata on dark KDE themes; full partition details appear in a hover tooltip from a compact information icon.

- Write ISO, IMG, BIN, and RAW images directly to a selected USB drive.
- Optional full read-back verification for raw image writes.
- Detect common Windows installation ISOs to help prevent accidental raw writing.
- Prepare x64 UEFI Windows installation media using a GPT disk with:
  - a large NTFS Basic Data partition containing the original Windows ISO files;
  - a 1 MiB FAT `BMK_EFI` UEFI:NTFS helper partition at the end of the drive. Its GPT type is Microsoft Basic Data (not EFI System), with NoDriveLetter (GUID-specific bit 63); its GPT partition name and FAT volume label are both `BMK_EFI`.
- Keep `install.esd`, `install.wim`, and all other Windows setup files unchanged. No ESD-to-WIM conversion or SWM splitting is needed in this mode.
- Verify the upstream UEFI:NTFS image before use and verify the written helper partition by reading it back.
- Preserve the source Windows ISO volume label on the large NTFS partition; reserve `BMK_EFI` for the small helper partition.
- Prefer the in-kernel NTFS3 driver for Windows ISO file copying, with ntfs-3g as a compatibility fallback.
- Use best-effort in-kernel `copy_file_range`, then `sendfile`, when full SHA-256 verification is disabled; fall back to streaming copies when the source/destination filesystems do not support either fast path.
- Throttle progress events and flush only the USB filesystem rather than calling a host-wide sync.
- Copy Windows files with batched disk flushing rather than forcing an fsync after every file.
- Optionally read back every copied Windows setup file and compare its SHA-256 hash. To keep Windows USB creation faster, this extra full read-back is off by default in Windows mode and can be enabled in the GUI.
- Show progress and operation logs in the GUI.
- Use polkit elevation only for the destructive disk-writing worker.

## Windows UEFI:NTFS workflow

The application follows the same general layout described by the UEFI:NTFS project and used by Rufus: a large NTFS data partition, then a small FAT helper partition at the very end of the USB device. On GPT, Rufus marks that helper partition as Microsoft Basic Data (not EFI System Partition) and sets the NoDriveLetter attribute (GUID-specific bit 63). This avoids a documented Windows Setup failure when a second ESP is present. UEFI first runs the FAT-side UEFI:NTFS loader; that loader loads its NTFS UEFI driver, locates the NTFS partition on the same device and starts the Windows x64 EFI bootloader there.

The pristine helper image is downloaded during installation from the official Rufus repository at a pinned commit and verified by exact size, Git blob SHA-1 and SHA-256. When preparing a USB, BootMediaKit copies that verified image to a temporary file and changes only its FAT volume label from the upstream `RUFUS_BOOT` to `BMK_EFI` using `fatlabel`; the signed EFI binaries are not modified. The temporary image is SHA-256 checked against a read-back of the written helper partition, and the partition label is read back as `BMK_EFI`.

The Windows files are copied without converting the install image. This avoids the FAT32 4 GiB file-size limit and avoids changing Microsoft's ESD/WIM payload. The kernel NTFS3 driver is preferred on CachyOS/Linux kernels that provide it; ntfs-3g remains a fallback for compatibility. When the extra SHA-256 pass is disabled, BootMediaKit attempts Linux `copy_file_range`, then `sendfile`, for kernel-assisted file copies; filesystems that do not support either cross-filesystem path transparently fall back to regular streaming copy. Progress output is throttled and only the USB filesystem is synced, not every filesystem on the host. A second SHA-256 read-back pass is optional because it reads the full USB payload again and can significantly increase time on low-end USB 2.0 sticks.

### Secure Boot

The upstream UEFI:NTFS helper image contains Secure Boot-signed x64 UEFI:NTFS components. This does **not** guarantee that every machine will boot it with Secure Boot enabled: firmware trust databases, Microsoft third-party UEFI CA settings, and revocation lists vary. A firmware may require third-party UEFI certificates to be enabled, or may reject a revoked signature. BootMediaKit does not disable Secure Boot or alter firmware settings.

On the hardware used for release validation, the standard Windows 11 26H2 x64 installer reached the Windows Setup disk-selection screen with Secure Boot both enabled and disabled. The installation was not continued beyond that point. This confirms the observed boot path on that test firmware only; other systems may differ.

### Current scope and limitations

- Windows target: **UEFI x64 only**. Linux ISOHybrid/DD images can boot in Legacy BIOS and UEFI when the source image supports those modes.
- Windows Legacy BIOS/CSM, Windows To Go, FreeDOS, Linux persistence and Windows 11 setup customization are not implemented.
- The current layout requires a 512-byte logical-sector USB device.
- The current installer targets Arch-based distributions only. Debian/Ubuntu and Fedora support are future work.
- Physical UEFI installation tests for Windows 10 and Windows 11 IoT Enterprise LTSC x64 completed successfully on the tested system(s). The standard Windows 11 26H2 x64 ISO was also tested with Secure Boot enabled and disabled and reached the Setup disk-selection screen; installation beyond that point was not verified.
- USB file verification checks file sizes and SHA-256 hashes after copying. It does not validate the Windows ISO publisher signature or the authenticity of the ISO itself.

## Install on Arch-based systems

The installer requires an internet connection to retrieve the pinned UEFI:NTFS helper image from the official Rufus repository and verify it.

```bash
chmod +x install.sh
./install.sh
```

Launch from the desktop menu or run:

```bash
bootmediakit
```

Arch dependencies:

- `pyside6` — graphical interface
- `util-linux` — `lsblk`, `blockdev`, `sfdisk`, `wipefs`, `mount`, and `umount`
- `parted` — `partprobe` to notify the kernel about the new partition table
- `ntfs-3g` — mounting NTFS volumes from Linux
- `ntfsprogs` — `mkfs.ntfs` formatter (Arch split package)
- `dosfstools` — `fatlabel` to set and verify the `BMK_EFI` FAT volume label
- `polkit` — narrowly scoped privilege elevation
- `7zip` — Windows ISO detection

KDE users need an active polkit authentication agent.

## Run the automated tests

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py version.py
bash -n install.sh uninstall.sh bootmediakit-worker
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

The GUI tests (`tests/test_app.py`) need `PySide6`; CI additionally runs `shellcheck -S warning install.sh uninstall.sh bootmediakit-worker`.

The unit tests cover target safety, source/target collision detection, GPT partition layout, partition naming, sfdisk type declarations, ISO structure scanning, file-copy manifests, SHA-256 verification, cancellation and packaging. Optional loop-device integration tests run the real RAW and Windows writers against a disk image as root:

```bash
sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

They are skipped without `BMK_INTEGRATION=1`, root and the required tools; see [docs/TESTING.md](docs/TESTING.md). Neither level replaces real USB, firmware or Windows Setup tests.

## Development direction

The immediate priority is to make the Arch/CachyOS implementation reliable before adding other distributions. Debian/Ubuntu and Fedora are planned only after the Arch-family workflow is validated. See [ROADMAP.md](ROADMAP.md), [CHANGELOG.md](CHANGELOG.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

## Windows Setup with multiple internal drives

A Windows Setup log containing `GetMachineInfo: Couldn't find info for boot disk`, `CanBeSystemVolume`, or `The selected disk is not the computer's boot disk` can indicate that Windows PE has misidentified the boot/system disk when several internal HDDs or SSDs are connected. This is a Windows Setup disk-selection issue, not proof that the USB source is corrupt. Verify the disk numbers and capacities with `diskpart` / `list disk`; for diagnosis, temporarily disconnect non-target internal drives and leave only the intended Windows target disk connected. Do not run `clean` on a disk unless you intend to erase it. For UEFI Windows installation, the target disk must use GPT. See [Microsoft's UEFI/GPT partition guidance](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/configure-uefigpt-based-hard-drive-partitions?view=windows-11).

## Safety

Writing to a USB device erases its contents. Always check the selected device path, model and capacity before confirming a write. Use a drive with no data you need. The application validates the target again immediately before writing and refuses the system disk, but software cannot eliminate the risk of selecting the wrong device.

If the graphical interface is closed or its connection to the worker is lost while writing, the worker stops safely at the next write boundary, but the USB drive may be left partially written. In that case the device must be written again before use.

## Third-party components

BootMediaKit does not contain copied Rufus application source code. It downloads a separately licensed UEFI:NTFS helper image from the pinned upstream Rufus repository at install time; that image contains third-party UEFI bootloader and filesystem-driver binaries. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution, source repositories and license references.
