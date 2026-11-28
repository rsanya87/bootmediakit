# Third-party notices

BootMediaKit's own application source code is licensed under GNU GPL-3.0-only; the full license text is in [LICENSE](LICENSE). No Rufus application source file has been copied into or linked with BootMediaKit.

This file is an attribution and component inventory. It records facts that were checked against the upstream sources named below; it is not legal advice. For the exact terms, copyright notices, corresponding source code and any source-availability obligations, refer to the upstream repositories and their license files.

## Pinned UEFI:NTFS helper image

BootMediaKit's Windows UEFI mode uses a separate, prebuilt FAT image published in the Rufus repository. The image contains third-party UEFI bootloader and filesystem-driver binaries; their copyright and license terms are separate from BootMediaKit's license.

| Field | Value |
|---|---|
| Upstream repository | https://github.com/pbatard/rufus |
| Upstream file | `res/uefi/uefi-ntfs.img` |
| Pinned commit | `acf7de640848ab249bedeb6feb59b33001f656b6` |
| Last upstream change to the file before the pinned commit | `2350489fe902bdc71d37f255a7684fe06a0ab2d0` ("[uefi] update uefi-ntfs driver to latest and add RISC-V 64 support") |
| Size | 1,048,576 bytes |
| Git blob SHA-1 | `ac50eed9730af847c43c145a5c17678f54128b33` |
| SHA-256 | `72683fa1250eeea772d3399277b434d4e55ba8dd0dc926e52d817e701fc2eb9e` |
| FAT volume label (upstream) | `RUFUS_BOOT` |
| Upstream description | https://github.com/pbatard/rufus/blob/acf7de640848ab249bedeb6feb59b33001f656b6/res/uefi/readme.txt |

The Rufus project itself is licensed under the GNU GPL version 3 or later (its `LICENSE.txt` and source headers at the pinned commit). BootMediaKit uses only the separately published helper image, not Rufus's Windows application source code.

### Components in the image

The upstream `readme.txt` at the pinned commit names three components and their releases. The license column is taken from the license files and source-file headers of each upstream repository at that release tag.

| Component | Release | Files in the image | License (as declared upstream) | Source for this release |
|---|---|---|---|---|
| UEFI:NTFS bootloader | 2.8 | `EFI/Boot/bootx64.efi`, `bootia32.efi`, `bootaa64.efi`, `bootarm.efi`, `bootriscv64.efi` | GPL-2.0-or-later: the source files (`boot.c`, `boot.h`, `path.c`, `system.c`) say "version 2 of the License, or (at your option) any later version"; the repository's `LICENSE.txt` is the GPL version 2 text. | https://github.com/pbatard/uefi-ntfs/releases/tag/v2.8 (tag `v2.8`) |
| NTFS UEFI driver derived from ntfs-3g | 1.9 | `EFI/Rufus/ntfs_x64.efi`, `ntfs_ia32.efi`, `ntfs_aa64.efi` | Mixed, see the note below. The repository's `COPYING` is the GPL version 2 text and `COPYING.LIB` the GNU Library GPL version 2 text; `uefi-driver/uefi_driver.inf` declares `SPDX-License-Identifier: GPL-2.0-or-later`. | https://github.com/pbatard/ntfs-3g/releases/tag/1.9 (tag `1.9`) |
| EfiFs drivers (exFAT for all architectures; NTFS for ARM and RISC-V) | 1.12 | `EFI/Rufus/exfat_x64.efi`, `exfat_ia32.efi`, `exfat_aa64.efi`, `exfat_arm.efi`, `exfat_riscv64.efi`, `ntfs_arm.efi`, `ntfs_riscv64.efi` | GPL-3.0-or-later; the project README states that the non-`grub_` sources under `src/` are GPL-2.0-or-later. The repository's `LICENSE` is the GPL version 3 text. EfiFs is based on the GNU GRUB read-only filesystem drivers. | https://github.com/pbatard/efifs/releases/tag/v1.12 (tag `v1.12`) |

The image also contains a 177-byte `README.txt`. The mapping of files to components follows the upstream `readme.txt` ("NTFS UEFI drivers, derived from ntfs-3g"; "exFAT (and ARM/RISC NTFS) UEFI drivers from EfiFs"; "UEFI:NTFS bootloader binaries"). The upstream `readme.txt` states that the ntfs-3g drivers and the UEFI:NTFS bootloaders are the release binaries with Microsoft's Secure Boot signature added (except the 32-bit ARM bootloader `bootarm.efi`), and that the EfiFs drivers are the release binaries without a Secure Boot signature.

**Note on the ntfs-3g driver license.** At tag `1.9`, `uefi-driver/uefi_driver.c` declares "version 3 of the License, or (at your option) any later version" (GPL-3.0-or-later). The other UEFI driver sources checked (`uefi-driver/uefi_bridge.c`, `uefi_file.c`, `uefi_logging.c`, `uefi_support.c`, the headers in `include/uefi-driver/`, `include/ntfs-3g/uefi_compat.h`, `libntfs-3g/uefi_compat.c` and `libntfs-3g/uefi_io.c`) declare GPL-2.0-or-later. The remaining ntfs-3g library sources were not reviewed file by file.

### How BootMediaKit obtains and uses the image

- The image is **not** stored in this repository and not included in the BootMediaKit source archive. `install.sh` runs `fetch_uefi_ntfs.py`, which downloads it at installation time from the pinned commit and accepts it only if the size, the Git blob SHA-1 and the SHA-256 all match the values above.
- When preparing a USB drive, BootMediaKit copies the verified image to a temporary file and changes only the FAT volume label, from `RUFUS_BOOT` to `BMK_EFI`, with `fatlabel` from dosfstools. The downloaded image stays unchanged. The `.efi` binaries and the other files inside the FAT image are not modified.
- The temporary image is written to the small helper partition at the end of the drive and read back for a SHA-256 comparison; the FAT label is checked again on the written partition. On the drive, the helper partition's GPT name and FAT volume label are both `BMK_EFI`; its GPT type is Microsoft Basic Data with the NoDriveLetter attribute (GUID-specific bit 63), not an EFI System Partition.
- Building the image into a distributable BootMediaKit package (instead of downloading it at installation time) would require shipping the corresponding source code and license files of the components above alongside it. This is not done today.

## What ends up on the media BootMediaKit creates

- **Windows UEFI (GPT):** the files of the user's Windows ISO, copied unchanged (the install image is not converted), and the `BMK_EFI` helper partition described above.
- **Windows Legacy BIOS (MBR):** the files of the user's Windows ISO, copied unchanged, and GNU GRUB (i386-pc) from the host system. BootMediaKit does not ship GRUB: it runs the host's own `grub-install --target=i386-pc` against the USB drive, which writes GRUB's boot code and modules from the host's GRUB installation to the drive, and BootMediaKit then writes a short `grub.cfg` that chainloads `/bootmgr`. GRUB remains under the license of the host distribution's GRUB package.
- **Linux RAW/DD:** the user's image, written byte for byte.
- The Windows files come from the user's own ISO; BootMediaKit does not distribute them. Microsoft's terms apply to them.

## Runtime dependencies (not bundled)

BootMediaKit invokes distribution-provided programs and libraries rather than embedding them. On Arch-based systems `install.sh` installs them with pacman (Python 3 comes in as a dependency of PySide6):

- Python 3 and PySide6 (Qt for Python) with Qt
- util-linux (lsblk, blockdev, sfdisk, wipefs, mount, umount, sync)
- parted (partprobe)
- dosfstools (fatlabel)
- ntfs-3g / ntfsprogs
- polkit
- 7-Zip
- GNU GRUB (i386-pc; for the Windows Legacy BIOS mode)

Each dependency remains under its own distribution/upstream license.
