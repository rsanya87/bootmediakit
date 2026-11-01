# Changelog

## 0.1.1-alpha — 2026-11-01

Baseline import from the internal CachyUSB 0.1.1-alpha build. This repository import applies a project-name and installation-identifier change to BootMediaKit; the application workflow is otherwise kept at the 0.1.1 baseline.

- Convert oversized, non-encrypted `install.esd` files to LZX-compressed WIM, validate the converted image, and split it into FAT32-compatible SWM parts.
- Process large WIM/ESD content before changing the USB partition table.
- Check actual split-file sizes and target-drive capacity before erasing the USB drive.
- Use `/var/tmp` for large WIM/ESD processing and check available scratch space first.
- Make the GUI content scrollable to support smaller windows and displays.
- Add automated tests for ESD export and SWM splitting.
- Rename the application, executable, desktop entry, temporary-file prefixes, and install paths from CachyUSB to BootMediaKit.

## Earlier development

The original 0.1.0-alpha internal baseline provided raw image writing and the first Windows UEFI/FAT32 workflow. It is not tagged in this repository; the maintained Git history begins with the 0.1.1-alpha baseline.
