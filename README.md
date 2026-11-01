# BootMediaKit

BootMediaKit is an open-source Linux desktop application for creating bootable USB media from ISO and raw disk-image files. The interface is built with Python and PySide6. Disk-writing operations are delegated to a narrowly scoped privileged worker.

**Development version:** `0.1.2-alpha`  
**Current platform target:** Arch Linux family (initial development and testing on CachyOS)  
**Application license:** GNU GPL-3.0-only

> This is an alpha release candidate for hardware testing, not a stable Rufus replacement. The new Windows UEFI:NTFS path has automated tests, but must still be validated with real USB devices, UEFI firmware and Windows Setup.

## Current capabilities

- Write ISO, IMG, BIN, and RAW images directly to a selected USB drive.
- Optional full read-back verification for raw image writes.
- Detect common Windows installation ISOs to help prevent accidental raw writing.
- Prepare x64 UEFI Windows installation media using a GPT disk with:
  - a large NTFS Basic Data partition containing the original Windows ISO files;
  - a 1 MiB FAT EFI System Partition at the end of the drive, containing the UEFI:NTFS boot image.
- Keep `install.esd`, `install.wim`, and all other Windows setup files unchanged. No ESD-to-WIM conversion or SWM splitting is needed in this mode.
- Verify the upstream UEFI:NTFS image before use and verify the written helper partition by reading it back.
- Optionally read back every copied Windows setup file and compare its SHA-256 hash (enabled by default in the GUI).
- Show progress and operation logs in the GUI.
- Use polkit elevation only for the destructive disk-writing worker.

## Windows UEFI:NTFS workflow

The application follows the same general layout described by the UEFI:NTFS project and used by Rufus: a large NTFS data partition, then a small FAT partition at the very end of the USB device. UEFI first runs the FAT-side UEFI:NTFS loader; that loader loads its NTFS UEFI driver, locates the NTFS partition on the same device and starts the Windows x64 EFI bootloader there.

The helper image is downloaded during installation from the official Rufus repository at a pinned commit. The installer checks the exact byte size and Git blob SHA-1 before installing it. At write time, BootMediaKit checks the same values and performs a read-back check after writing the helper partition.

The Windows files are copied without converting the install image. This avoids the FAT32 4 GiB file-size limit and avoids changing Microsoft's ESD/WIM payload.

### Secure Boot

The upstream UEFI:NTFS helper image contains Secure Boot-signed x64 UEFI:NTFS components. This does **not** guarantee that every machine will boot it with Secure Boot enabled: firmware trust databases, Microsoft third-party UEFI CA settings, and revocation lists vary. A firmware may require third-party UEFI certificates to be enabled, or may reject a revoked signature. BootMediaKit does not disable Secure Boot or alter firmware settings.

### Current scope and limitations

- Windows target: **UEFI x64 only**.
- Legacy BIOS/CSM, Windows To Go, FreeDOS, Linux persistence and Windows 11 setup customization are not implemented.
- The current layout requires a 512-byte logical-sector USB device.
- The current installer targets Arch-based distributions only. Debian/Ubuntu and Fedora support are future work.
- Real Windows Setup testing is still required. A previous 0.1.1-alpha FAT32/SWM attempt showed a “required media driver is missing” dialog on the reported PC; the same ISO reportedly worked when prepared with Rufus. The 0.1.2 UEFI:NTFS implementation is designed to address the file-system and boot-chain limitations, but the issue remains open until tested on that same machine.
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
- `ntfs-3g` — mounting NTFS volumes from Linux
- `ntfsprogs` — `mkfs.ntfs` formatter (Arch split package)
- `polkit` — narrowly scoped privilege elevation
- `7zip` — Windows ISO detection

KDE users need an active polkit authentication agent.

## Run the automated tests

```bash
python3 -m py_compile app.py worker.py iso_utils.py fetch_uefi_ntfs.py
bash -n install.sh uninstall.sh
python3 -m unittest discover -s tests -v
```

The unit tests cover target safety, GPT partition layout, partition naming, sfdisk type declarations, ISO structure scanning, file-copy manifests and SHA-256 verification. They do not replace real USB, firmware or Windows Setup tests.

## Development direction

The immediate priority is to make the Arch/CachyOS implementation reliable before adding other distributions. Debian/Ubuntu and Fedora are planned only after the Arch-family workflow is validated. See [ROADMAP.md](ROADMAP.md), [CHANGELOG.md](CHANGELOG.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

## Safety

Writing to a USB device erases its contents. Always check the selected device path, model and capacity before confirming a write. Use a drive with no data you need. The application validates the target again immediately before writing and refuses the system disk, but software cannot eliminate the risk of selecting the wrong device.

## Third-party components

The UEFI:NTFS helper image is retrieved from the pinned upstream Rufus source, not re-licensed as BootMediaKit code. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for upstream locations and license notes.
