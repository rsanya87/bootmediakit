# Third-party notices

BootMediaKit's own source code is licensed under GNU GPL-3.0-only. The program also downloads and uses a separate third-party FAT filesystem image from the Rufus project for UEFI:NTFS boot support. That image is **not BootMediaKit-authored code** and keeps the applicable upstream component licenses.

## UEFI:NTFS helper image

- Upstream repository: https://github.com/pbatard/rufus
- Upstream file: `res/uefi/uefi-ntfs.img`
- Pinned Rufus commit: `acf7de640848ab249bedeb6feb59b33001f656b6`
- Git blob SHA-1: `ac50eed9730af847c43c145a5c17678f54128b33`
- Exact image size: 1,048,576 bytes
- Upstream description: https://github.com/pbatard/rufus/blob/master/res/uefi/readme.txt

The installer downloads this file directly from the pinned commit and verifies its exact size and Git blob object hash before placing it under `/usr/share/bootmediakit/uefi/`. The privileged writer verifies the same hash before writing and reads the helper partition back after writing.

The image is a collection of UEFI boot components. Per the upstream Rufus description, it includes:

- UEFI:NTFS bootloader binaries (release 2.8, including Secure Boot-signed x64 components). Source and license: https://github.com/pbatard/uefi-ntfs
- NTFS UEFI drivers derived from ntfs-3g (release 1.9, with Microsoft Secure Boot signatures on the read-only binaries). Source and license: https://github.com/pbatard/ntfs-3g
- Additional EfiFs exFAT and architecture-specific drivers. Source and license: https://github.com/pbatard/efifs

Consult the upstream repositories and license files for the full license terms and corresponding source code. In particular, the UEFI:NTFS and ntfs-3g components are GPLv2-family software; EfiFs components are GPLv3-family software. These separate components are not relicensed by BootMediaKit's GPL-3.0-only license.

## Other runtime dependencies

BootMediaKit invokes system programs rather than embedding them:

- Python 3 and PySide6
- util-linux tools such as `lsblk`, `blockdev`, `sfdisk`, `wipefs`, `mount`, and `umount`
- ntfs-3g and ntfsprogs
- polkit
- 7-Zip

Each dependency remains under its own distribution/upstream license. Install dependencies using the package manager for your Linux distribution.
