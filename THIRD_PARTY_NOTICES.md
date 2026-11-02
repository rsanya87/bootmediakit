# Third-party notices

BootMediaKit's own application source code is licensed under GNU GPL-3.0-only (see LICENSE). No Rufus application source file has been copied into or linked with BootMediaKit.

BootMediaKit does use a separate, prebuilt UEFI:NTFS helper image from the official Rufus repository. The application downloads this file at installation time from a pinned public upstream commit; the image is not stored in this repository or bundled in the BootMediaKit source archive. The image contains third-party UEFI bootloader and filesystem-driver binaries. Their copyright and license terms remain separate from BootMediaKit's license.

## Pinned UEFI:NTFS helper image

- Upstream repository: https://github.com/pbatard/rufus
- Upstream file: res/uefi/uefi-ntfs.img
- Pinned commit: acf7de640848ab249bedeb6feb59b33001f656b6
- Exact source image size: 1,048,576 bytes
- Source Git blob SHA-1: ac50eed9730af847c43c145a5c17678f54128b33
- Source SHA-256: 72683fa1250eeea772d3399277b434d4e55ba8dd0dc926e52d817e701fc2eb9e
- Upstream image description at the pinned commit: https://github.com/pbatard/rufus/blob/acf7de640848ab249bedeb6feb59b33001f656b6/res/uefi/readme.txt

The upstream image's FAT volume label is RUFUS_BOOT. BootMediaKit first verifies the downloaded source image against its exact size and both pinned hashes. When preparing a USB, it copies the verified image to a temporary file and changes only the FAT volume label to BMK_EFI with the fatlabel utility from dosfstools. The pristine downloaded source image remains unchanged. The signed .efi binaries and filesystem-driver files inside the FAT image are not patched. The temporary image is hashed, written to the small helper partition, and read back for SHA-256 verification; the FAT label is checked again on the written partition.

On the USB, the helper partition's GPT name and FAT volume label are both BMK_EFI. Its GPT type is Microsoft Basic Data with the NoDriveLetter GUID-specific attribute bit 63; it is deliberately not an EFI System Partition.

## Components identified by the upstream Rufus image description

The upstream res/uefi/readme.txt identifies these components and versions:

- UEFI:NTFS bootloader binaries, release 2.8 — source: https://github.com/pbatard/uefi-ntfs ; source files declare GPL-2.0-or-later. License file: https://github.com/pbatard/uefi-ntfs/blob/master/LICENSE.txt
- NTFS UEFI drivers derived from ntfs-3g, release 1.9 — source and license: https://github.com/pbatard/ntfs-3g (GPLv2; see its COPYING file).
- EfiFs exFAT and architecture-specific UEFI drivers, release 1.12 — source: https://github.com/pbatard/efifs ; the project describes its drivers as GPLv3+, with some source files under GPLv2+.
- Rufus project — https://github.com/pbatard/rufus ; Rufus is licensed under GNU GPL version 3 or later. BootMediaKit uses the separately published helper image, not Rufus's Windows application source code.

Refer to the upstream repositories and their license files for the exact terms, corresponding source code, copyright notices and any source-availability obligations that apply when redistributing the binaries. This notice is an attribution and component inventory, not legal advice.

## Other runtime dependencies

BootMediaKit invokes distribution-provided tools rather than embedding them:

- Python 3 and PySide6
- util-linux (lsblk, blockdev, sfdisk, wipefs, mount, umount, sync)
- ntfs-3g / ntfsprogs
- dosfstools (fatlabel)
- parted (partprobe)
- polkit
- 7-Zip

Each dependency remains under its own distribution/upstream license.