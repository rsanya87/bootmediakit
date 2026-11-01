# BootMediaKit

BootMediaKit is an open-source Linux desktop application for creating bootable USB media from ISO and raw disk-image files. The interface is built with Python and PySide6. Disk-writing operations are delegated to a narrowly scoped privileged worker.

**Current version:** `0.1.1-alpha`  
**Current platform target:** Arch Linux family (initial development and testing on CachyOS)  
**License:** GNU GPL-3.0-only

> This is an early alpha. It is not yet a full Rufus replacement, and not all ISO images, USB devices, or UEFI firmware have been validated.

## Current capabilities

- Write ISO, IMG, BIN, and RAW images directly to a selected USB drive.
- Optional full read-back verification for raw image writes.
- Detect common Windows installation ISOs to help prevent accidental raw writing.
- Prepare an x64 UEFI Windows installation USB using GPT and FAT32.
- Split oversized `install.wim` files into FAT32-compatible `.swm` parts.
- Convert an oversized, non-encrypted `install.esd` to WIM, then split it into `.swm` parts.
- Prepare large WIM/ESD content and check target capacity before modifying the USB device.
- Show operation progress and logs in the GUI.
- Use polkit elevation only for the destructive disk-writing worker.

## Known limitations

- The Windows installation workflow is under investigation: a Windows 10 IoT Enterprise LTSC 2021 x64 ISO that boots and installs when written with Rufus produced a Windows Setup “required media driver is missing” dialog when written with BootMediaKit 0.1.1-alpha on the same target PC. The root cause has not yet been established. See [ROADMAP.md](ROADMAP.md).
- Windows USB creation currently uses a single GPT/FAT32 EFI System Partition. UEFI:NTFS and a dual-partition Windows layout are not implemented yet.
- Legacy BIOS/CSM, Windows To Go, FreeDOS, Linux persistence, and Windows 11 setup customization are not implemented.
- The Windows file-copy workflow does not yet perform a full file-by-file read-back verification.
- Encrypted ESD files larger than the FAT32 file limit are not supported by the current conversion workflow.
- The installer uses `pacman`; Debian/Ubuntu and Fedora installers are future work and are not supported by this release.

## Install on Arch-based systems

Install the dependencies and application with:

```bash
chmod +x install.sh
./install.sh
```

Launch from the desktop application menu or run:

```bash
bootmediakit
```

The installer requires the following Arch packages: `pyside6`, `parted`, `dosfstools`, `wimlib`, `polkit`, and `7zip`. KDE users need an active polkit authentication agent.

## Run the automated tests

```bash
python3 -m unittest discover -s tests -v
```

The current unit tests cover safety validation, Windows ISO detection, and mocked WIM/ESD export/splitting operations. They do **not** replace physical USB, real ISO conversion, UEFI firmware, or Windows Setup testing.

## Development direction

The immediate priority is to make the Arch/CachyOS implementation reliable before adding other distributions. Debian/Ubuntu and Fedora support are planned after the Arch-family workflow has been validated. See [ROADMAP.md](ROADMAP.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Safety

Writing to a USB device erases its contents. Always verify the selected device path, model, and capacity before confirming a write. Test only with a drive that contains no data you need. The application has protective checks, but no software can eliminate the risk of selecting the wrong device.
