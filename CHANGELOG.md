# Changelog

## Unreleased

- Docs: `docs/INVARIANTS.md` (rules no change may break; the three writers are frozen), `docs/LESSONS.md` (mistakes that already happened) and `docs/REGRESSION_CHECKLIST.md` (the maintainer's physical pre-release checks) are now in the repository; `CONTRIBUTING.md` and both READMEs link to them. `ROADMAP.md` gets the 0.4.0 section with its status list (T0).
- Tests: writer fingerprint tests (`tests/test_writer_fingerprint.py`) run `write_raw`, `write_windows_uefi` and `write_windows_bios` through `worker.main()` without root or a device, with a fake command runner that simulates sfdisk, mkfs.ntfs, fatlabel, mount and grub-install on files. The normalised timeline (commands and arguments, sfdisk scripts, safety checks in order, `open`/`fsync` on the target, every JSON event with its Hungarian text, the copied USB content, the pinned writer constants) must match the golden files in `tests/fixtures/writer_fingerprints/`, which were generated from the unchanged v0.3.0 writers. Changing them needs the INVARIANTS A6 gate; `BMK_UPDATE_WRITER_FINGERPRINTS=1` rewrites them and fails on purpose. Further tests pin the cancel boundaries (exit 130, no `fsync`, `target_modified`) and check a byte-exact RAW write and its read-back on a file. Temporarily removing `--force` from `wipefs`, the RAW `fsync`, `insmod ntldr` from `grub.cfg`, changing one Hungarian message or adding `--force` to `grub-install` each failed the tests (checked by hand, not committed) (T1).
- GUI: light/dark appearance (new module `theme.py`, installed by `install.sh` and added to the `py_compile` lists). The style sheet no longer has fixed colours: semantic tokens (text, secondary text, accent, borders, focus ring, selection, primary button, disabled state, progress, warning/error/success) are derived from the active `QPalette` and adjusted to at least 4.5:1 for text and 3:1 for large text and indicators (engineering targets from WCAG 2.x AA, not a conformance claim). The default mode "Rendszer / Automatikus" follows Qt's `QStyleHints.colorScheme`, else an unambiguous palette, and restyles the running window when the system palette changes; if the scheme cannot be determined the window starts dark. A sun/moon button at the top right shows the current appearance, switches between light and dark on click (manual override) and its menu restores the system mode; it has a tooltip and an accessible name. A forced appearance first asks Qt (`QStyleHints.setColorScheme`) and only falls back to Fusion with an own palette if the palette does not follow; in system mode the native style stays. The choice is stored per user with `QSettings` (`~/.config/BootMediaKit/BootMediaKit.conf`); the worker reads no user settings. The status line gets a shape-coded icon (progress, success, warning, error) with an accessible name, so states are not told by colour alone. New GUI texts use `tr()`. Tests no longer read the real user configuration (T2).
- GUI: responsive layout. The fixed `Noto Sans` 10 pt application font is gone; the system font, size and Qt's own high-DPI scaling apply (nothing is multiplied by the device pixel ratio). The 740×900 window cap and the screen-height compact flag are replaced by layout profiles chosen from the measured content size: one column with normal spacing when it fits, otherwise two columns (1 | 2, 3 | progress) with compact spacing, and below the minimum a compact single column. The minimum window size is 880×550 logical pixels, measured offscreen in every visible state (two columns at 880 px need 548 px with a 9 pt and a 10 pt font; see the fix below) and never larger than the screen's available area; it fits 1280×800 at 100 % and 125 % scaling. At or above it the page has no scrollbar; the log takes the spare height and scrolls inside. Below it (e.g. very large fonts) the page scrolls as a last resort. Long file and device names are shortened with "…" with the full text in the tooltip; the mode descriptions wrap instead of being cut at a fixed height. The main controls got accessible names. New offscreen tests (`tests/test_layout.py`) cover the tested sizes and fonts, overlap, the fallback, eliding, focus order and a `QT_SCALE_FACTOR=1.25` run (T3).
- GUI and docs: clear handling of a missing polkit authentication agent. pkexec(1) of polkit 128 documents exit code 126 for a dismissed dialog and 127 for no authorization, failed authentication or an error; without a registered agent pkexec tries its own textual agent, which fails without a terminal. On 127 before the worker started the GUI now shows an error dialog with the possible causes (no agent in the session, wrong password or no admin rights, polkit service not running) and what to do; on 126 it says the dialog was closed. In both cases the target was not touched. Only the exit code is used, never pkexec's text. BootMediaKit brings no agent, starts none and never falls back to `sudo`; tests check that the GUI only runs `pkexec` with the fixed wrapper and read-only `lsblk`, and pin the unchanged polkit action and wrapper. The READMEs and the installer explain the polkit service and agent without naming a single desktop (the READMEs list Arch agent packages as examples: `polkit-kde-agent`, `polkit-gnome`, `lxqt-policykit`, `mate-polkit`). The `.desktop` file is checked for standard keys only, and with `desktop-file-validate` (added to CI) (T4).
- Fix: the menu arrow of the sun/moon appearance button no longer covers the icon. With the style sheet border the menu part of the button was drawn over the icon (seen by the maintainer on KDE Plasma, Wayland); the button now reserves room for it. An offscreen test checks that the whole icon is visible and left of the menu part, in light and dark and with focus; it fails on the previous style sheet with the Fusion and the Breeze style (T2).
- Fix: the minimum window height is 550 instead of 540 logical pixels. 540 had been measured in the start-up state only; in Windows mode, and in RAW mode after switching back (its description is one sentence longer than at start-up), the two-column page needs 548 px with a 9 pt and a 10 pt font, so a scrollbar appeared at the minimum. Found by the T5 pseudo-locale test. The layout tests now run in every visible state (RAW, Windows without ISO, Windows UEFI, Windows Legacy, with and without the "Legacy nem elérhető" hint, danger warning shown) and check the real client size; they fail with 540. 880×550 still fits 1280×800 at 125 % with a 44 px panel and a 40 px frame, with 6 px to spare. `docs/LESSONS.md` records that layout tests must cover every visible state (T3).
- GUI and tests: translatable new texts and a pseudo-locale layout check. Every user-visible text added in 0.4.0 (appearance switch, tooltips, status names, polkit errors, accessible names) uses `tr()` with the Hungarian source text; there is no catalogue yet, so nothing changes on screen. `tests/test_i18n.py` scans the GUI sources and fails on a new text without `tr()` or a `tr()` with a non-literal argument; the 145 older texts are listed in `tests/fixtures/legacy_untranslated_texts.json`, a list that may only shrink (0.8.0 converts them). A pseudo-locale (about 40 % longer, accented texts, markup kept) runs the layout checks in every UI state: no scrollbar from 1024×600 up; at the 880×550 minimum the page may scroll vertically, but the two columns stay and no control is lost or overlapped (approved deviation from the work description, see `ROADMAP.md`). The pseudo-locale found that the verification check box text cannot wrap (a `QCheckBox` never wraps), which forced a single scrolling column at 880 px: the option is now a text-less check box with a wrapping buddy label; a click on the label toggles it, focus and Space stay on the box, the accessible name is the full text, the label follows the disabled state with the theme's disabled colour, and the Hungarian text and the worker argument are unchanged (T5).
- Docs: no version numbers in `.py` comments, docstrings or code texts outside `version.py`; they name the task or point to `ROADMAP.md`/`CHANGELOG.md`. The version guard in `tests/test_packaging.py` reads the whole text of every `.py` file, so the release commit would have failed; the guard is unchanged. New rule `docs/INVARIANTS.md` D8 and a `docs/LESSONS.md` entry (approved by the maintainer).
- Worker: stable message identifiers. `emit()` takes two optional keyword arguments, `msg_id` and `msg_args`, and adds them to the JSON event only when given; the existing fields, their order and the Hungarian texts are unchanged, and the GUI ignores the new fields. All 46 `emit()` calls carry one of 42 identifiers (one identifier per Hungarian message; the same step of the two Windows writers shares one), with the dynamic values (bytes done/total, mount point, image and device path, sizes, ISO label, boot image paths) in `msg_args`; values that are not plain JSON (a `Path`) are sent as text. `docs/MESSAGES.md` lists every identifier with its message, arguments (name, type, meaning) and writer. No command, partition layout, cancel boundary or write step changed: the writer fingerprint goldens are byte for byte unchanged; the comparison leaves the two new fields out, and `tests/test_messages.py` checks them: every `emit()` has a literal documented `msg_id`, argument names match the table, one identifier never covers two messages, in all six writer runs and on cancel and failure every event's identifier, argument types and values match its message, the goldens contain no new field, old calls print exactly the same line, and the GUI shows the same with and without the new fields (T6).
- Fix (T5): the pseudo-locale layout test failed in CI at 1024×600 with a 10 pt font: with DejaVu Sans the page needed 602 px, with Noto Sans (the development machine) 594 px. The compact spacing is tighter (outer margin 8→6, spacing 5→4, card and warning margins 5→4 vertically, spacing inside cards 3→2); control heights, focus marks and colours are unchanged. With pseudo text the worst case at 1024×600 is now 578 px (DejaVu Sans, 10 pt), and a test keeps 1024×590 free of scrollbars, so at least 10 px are left. The layout and pseudo-locale tests run with DejaVu Sans and Noto Sans; a missing font is an error with an install hint, and failure messages name the font. CI installs `fontconfig`, `fonts-dejavu-core` and `fonts-noto-core` and checks both families before the tests. The minimum window size stays 880×550 (the content now needs at most 524 px there). `docs/LESSONS.md` records that offscreen layout tests depend on the font.

## 0.3.0 — 2026-11-24

Feature release: a new Windows Legacy BIOS/MBR installer mode (MBR, one active NTFS partition, GNU GRUB i386-pc chainloader written by the system's `grub-install`). New runtime dependency: `grub`. The Linux DD/RAW and Windows UEFI modes are unchanged.

- Tests: T0 feasibility gate for the Legacy BIOS/MBR Windows mode. A loop-device integration test builds an MBR disk with one active NTFS partition, runs `grub-install --target=i386-pc` (no `--force`) and chainloads a test `bootmgr` with `ntldr /bootmgr`; with `BMK_QEMU=1` it boots the image in QEMU/SeaBIOS and waits for `BMK-BOOT-OK` on the debug port (T0).
- Tests: when the T0 QEMU boot check fails, it now prints the GRUB and QEMU versions, the SeaBIOS log (port 0x402), the guest's VGA text screen and CPU registers, so the stage where booting stops is visible in CI logs (T0).
- Tests: if the failed T0 boot stops at a `grub>` prompt, the test types read-only commands (`set`, `ls -l` of `command.lst` and `ntldr.mod`, `insmod echo`, `insmod ntldr`, a manual `ntldr /bootmgr`) through the QEMU monitor and prints the screen after each. A second QEMU boot check uses media written through ntfs-3g instead of ntfs3 (T0).
- Tests: the T0 `grub.cfg` loads `ntldr` and `boot` explicitly with `insmod`. GRUB 2.14-2ubuntu2.1 does not autoload commands, so `ntldr /bootmgr` failed there with "can't find command". This deviates from the work description's T0 step 5 (approved by the maintainer) and applies to the T3 chainloader too (T0).
- Worker: `scan_windows_iso` takes a boot mode (`uefi` by default, unchanged). `bios` requires `bootmgr`, `boot/BCD`, `sources/boot.wim` and an install image but not the EFI loader, names Windows XP/2003-style ISOs (`i386` without `bootmgr`) as unsupported, and refuses an ISO whose root already has a `grub` entry (T1).
- Worker: MBR layout for the Legacy BIOS mode: `calculate_mbr_layout` (one partition from 1 MiB to the 1 MiB-aligned disk end), `make_mbr_sfdisk_script` (`label: dos`, type `7`, `bootable`) and `verify_mbr_layout` (`sfdisk --verify` and `--json`: label, single partition, start, size, type, active flag). Disks of 2**32 sectors (2 TiB) or more are refused: sfdisk only warns there and would silently cut the partition (T2).
- Worker: `install_bios_chainloader` checks that GRUB i386-pc is installed (else names `sudo pacman -S grub`), that the boot directory is the target's own NTFS mountpoint, re-validates the target identity, runs `grub-install --target=i386-pc --boot-directory=<NTFS mount> <device>` with a timeout, writes and fsyncs `grub/grub.cfg`, and verifies the MBR signature, non-empty boot code, the GRUB modules and the unchanged partition table. `grub_install_args` refuses an empty, relative or host root/`/boot`/`/efi` boot directory and a non-`/dev` device (T3).
- Worker: new `write_windows_bios` writer: all refusals (GRUB missing, 2 TiB, non-512-byte sectors, ISO checks, capacity) happen before the first write; then `wipefs --all --force`, MBR, NTFS with the production geometry, file copy with optional SHA-256 check (ISO files only), GRUB chainloader, unmount and a final MBR check. Steps shared with `write_windows_uefi` (sector count, partition table write, waiting for partition nodes, NTFS formatting, copy and verification, cleanup) moved into helper functions verbatim; the UEFI writer issues the same commands and messages in the same order (T4).
- Worker: new mode `windows-bios` next to `raw` and `windows` (UEFI), with the same argument order; it requires an ISO file and calls `write_windows_bios`. Unknown mode names are still errors. The wrapper and the polkit action pass arguments through unchanged and were not modified (T5).
- GUI: for a recognised Windows ISO in Windows mode a new "Indítási mód" selector offers "UEFI (GPT)" (default) and "Legacy BIOS (MBR)"; otherwise it is disabled and falls back to UEFI. Without `grub-install` and the i386-pc files the worker needs, the Legacy item is disabled and a hint names `sudo pacman -S grub`; the check runs again on start. The confirmation dialog names the boot mode and warns that a Legacy stick does not boot in UEFI mode, a permanent note says Legacy is meant for older machines, and the worker gets `windows-bios`. The Windows button is now "Windows telepítő (NTFS)"; the mode descriptions are top-aligned and fit two lines at the minimum width (T6).
- CI: the package install step retries `apt-get update` and `apt-get install` up to three times (30 s apart) and still fails after the last attempt; the job has a 30-minute and the install step a 20-minute timeout. A runner DNS failure for `security.ubuntu.com` had failed the T6 run, and an earlier attempt hung in this step for over 15 minutes.
- Tests: loop-device integration tests for the production `write_windows_bios` (bind-mounted ISO tree with a test `bootmgr`): `sfdisk --json` (dos, one active type-7 partition), NTFS label, SHA-256 of every copied file, `grub/grub.cfg`, the T0 static MBR checks, no leftover mounts or temp directories, host `/boot/grub` untouched; a QEMU/SeaBIOS boot of the written media with `BMK_QEMU=1`; and a Legacy write over media made by the UEFI writer leaves no primary or backup GPT header. The T0 gate tests stay as an independent reference and share the QEMU boot code. With `BMK_INTEGRATION_REQUIRED=1` and `BMK_QEMU=1` a missing QEMU binary is now an error instead of a skip (T7).
- Installer and docs: `install.sh` installs `grub` and explains that BootMediaKit only uses its `grub-install` and i386-pc modules on the selected USB drive, that installing it does not change the host boot loader, and that the package's own `grub-install`/`grub-mkconfig` hint is not needed for BootMediaKit (the CachyOS `grub` 2:2.16-1.1 install script only prints that hint). Both READMEs list the dependency, describe the Legacy BIOS/MBR mode (layout, boot chain, host safety, Legacy-only boot, refusals, test status) and update the limitations (T8).
- Packaging: `install.sh` is stored as executable (mode 100755) in the repository, so `./install.sh` works on a fresh clone; the README's `chmod +x` step stays harmless.
- Docs: `ROADMAP.md` gets the 0.3.0 section above 0.2.2 with its status, the approved deviations from the work description and the physical test list; the Legacy BIOS item of the 0.2.2 deferred list and of the long-term ideas is closed. `docs/TESTING.md` describes the Legacy BIOS integration tests, `BMK_QEMU=1` and a read-only manual QEMU boot check of a finished USB drive (QEMU as the normal user with a read-only ACL on the device and `snapshot=on`; `readonly=on` is refused for IDE disks by QEMU 11.1). `CONTRIBUTING.md` and both READMEs mention the Legacy writer tests and the `BMK_QEMU` command; tests keep these commands in sync with CI (T9).
- CI: installs `grub-pc-bin`, `grub2-common` and `qemu-system-x86`, and runs the integration tests with `BMK_QEMU=1` (T0).
- CI fix: the integration variables (`BMK_INTEGRATION_REQUIRED`, `BMK_QEMU`, `BMK_UEFI_NTFS_IMAGE`) are passed to `env` after `sudo`, because the runner's `sudo -E` did not forward the step's `env:` block (seen on `ubuntu-26.04` since the 0.2.2 runs). A new step checks under `sudo` that they arrive; packaging tests guard both.
- GUI, worker and docs: a Legacy BIOS stick is no longer described as never booting in UEFI mode. The physical test showed that it does not boot on UEFI firmware without an NTFS driver (OVMF), but a Gigabyte B850 board with CSM disabled started the ISO's own `efi/boot/bootx64.efi` from the NTFS partition. The confirmation dialog, the mode description, the final worker log, both READMEs and `docs/TESTING.md` now say that the stick is made for Legacy BIOS/CSM, may start in UEFI only on firmware that reads NTFS, and that UEFI computers should use the UEFI (GPT) mode. The tests that checked the old wording now check the new one.

## 0.2.2 — 2026-11-10

Maintenance release: no new features, no change to the write sequence or to the Windows-mode GPT layout.

- Source filesystem check: the rejection message now names the filesystem type and source and tells the user to copy the ISO to a local block-device-backed disk. `virtiofs`, `vboxsf`, `fuse.sshfs`, `fuse.rclone`, `fuse.gvfsd-fuse` and `fuse.portal` sources are accepted as network/virtual filesystems that cannot be on the target; `fuseblk` still resolves to its block device; `overlay`, `zfs` and unknown types stay rejected (T1).
- Multi-device Btrfs sources: every member listed under `/sys/fs/btrfs/<UUID>/devices/` now takes part in the source/target collision check; an unreadable member list stops the operation (T2).
- GUI: an unchanged `lsblk` error during automatic device refresh is logged once instead of every 5 seconds; it may be logged again after a successful refresh. Manual refresh still shows the dialog (T3).
- Tests and README: a GUI pipe that breaks during a Windows-mode or RAW write is now covered by regression tests (safe stop at the next cancellation point, cleanup, exit code 130), and the Safety section documents that the USB drive may be left partially written (T4).
- Single version source: new `version.py`, read by the GUI and by the UEFI:NTFS fetcher and installed by `install.sh`; packaging tests keep the READMEs, `CHANGELOG.md` and `docs/TESTING.md` in step with it. The privileged worker does not import it (T5).
- CI: `shellcheck -S warning` on the installer, uninstaller and worker wrapper (T6).
- CI and tests: loop-device integration tests in `tests/integration/` run the real RAW and Windows writers as root against a disk image (stale GPT cleanup, byte-exact RAW write, GPT layout, NTFS/FAT labels, copied-file SHA-256). They are opt-in with `BMK_INTEGRATION=1` and are skipped otherwise (T7).
- Documentation: test commands in the READMEs, `CONTRIBUTING.md` and `docs/TESTING.md` match CI; integration test usage and skip conditions are documented; the 0.2.2 work description is part of `ROADMAP.md` (T8).

## 0.2.1 — 2026-11-05

BootMediaKit 0.2.1 is the first stable release of the 0.2.x line. This release concentrates on disk-write safety, reliability under failure and cancellation, GUI lifecycle stability, and regression coverage. It retains the Arch Linux family as its initial supported platform.

### Reliability and disk safety

- Resolve source/target disk relationships through stacked mounts, autofs/CIFS mount layers and Btrfs subvolumes; reject ambiguous backing-device information instead of guessing.
- Strengthen whole-disk unmount verification before destructive RAW writing.
- Keep stale filesystem/partition signature cleanup ahead of the raw image write and add regression coverage for the command ordering.
- Handle broken GUI/worker event pipes safely and avoid duplicate error reporting.
- Avoid unnecessary disk flushes during cancellation cleanup.
- Flush block-device buffers before UEFI:NTFS helper read-back verification.

### GUI and compatibility

- Discover USB devices asynchronously through Qt's process interface, with a timeout and protection against overlapping refresh requests.
- Shut down Qt widgets and child processes explicitly to avoid interpreter-finalization crashes.
- Remove an SVG filter primitive unsupported by Qt's SVG renderer.
- Preserve the existing screen-aware layout, visible version information, operation timer and compact device-information presentation.

### Validation

- GitHub Actions automated checks passed on the final 0.2.1 source branch: [workflow run 41980736701](https://github.com/rsanya87/bootmediakit/actions/runs/41980736701).
- Linux Mint 22.3 Cinnamon DD/RAW media was physically confirmed to boot in both UEFI and Legacy BIOS/MBR modes.
- Windows 10 and Windows 11 IoT Enterprise LTSC x64 installation media were physically tested; installation completed successfully on the tested system(s).
- The latest standard Windows 11 26H2 x64 ISO reached the Windows Setup disk-selection/partitioning screen with Secure Boot both disabled and enabled. Installation beyond that screen was not completed, so this is not recorded as a full installation test.
- Secure Boot behavior was therefore observed on the tested firmware, but broad compatibility across different firmware implementations is not claimed.

## 0.1.3 — 2026-11-03

BootMediaKit 0.1.3 is the first stable release of the Arch/CachyOS implementation.

### Windows UEFI and Linux RAW/DD

- Create Windows x64 UEFI installation media on GPT with a large NTFS partition and a 1 MiB FAT UEFI:NTFS helper partition at the end of the USB drive.
- Preserve the original Windows ISO volume ID as the first GPT partition name and NTFS volume label. Use `BOOTMEDIA` only as a fallback when the ISO does not expose a usable label. Keep `BMK_EFI` exclusively for the helper partition.
- Keep `install.esd`, `install.wim` and all other Windows files unchanged; no ESD-to-WIM conversion or SWM splitting.
- Retain the Microsoft Basic Data + NoDriveLetter GUID:63 metadata for the FAT helper partition, preventing Windows Setup from seeing a second EFI System Partition.
- Verify the pinned upstream UEFI:NTFS helper image by size and cryptographic hashes; alter only a temporary copy's FAT volume label, not the signed EFI binaries.
- Prefer kernel NTFS3 and kernel-assisted file copying, with ntfs-3g and buffered-copy fallbacks. Hide expected cross-filesystem `EXDEV` fallbacks from the error log.
- Support direct Linux ISO/RAW/DD writing with optional full read-back verification.

### Safety and reliability

- Add a dedicated root-owned worker wrapper and BootMediaKit-specific Polkit action; run Python in isolated mode and keep the GUI unprivileged.
- Revalidate target device identity and reject source images stored on the target physical disk.
- Protect system and swap backing devices; reject LUKS, LVM, RAID and swap target layouts.
- Add cooperative cancellation at safe write boundaries, flushing completed write units and performing normal cleanup.
- Show a detailed destructive confirmation, including partitions, filesystems, labels, sizes and mountpoints; require a second confirmation for large or non-removable USB devices.
- Use structured `lsblk --json` output and distinguish authorization failures from operations that may have modified the target.

### User interface

- Add BootMediaKit application icon, visible version label and elapsed operation timer.
- Use a screen-aware compact layout capped at 740×900 logical pixels without reducing the 10 pt UI font.
- Display partition details in a compact hover information tooltip.

### Validation

- User-tested Linux DD/RAW media booted in both Legacy BIOS and UEFI modes.
- User-tested Windows 10 IoT Enterprise LTSC 2021 x64 in UEFI mode through successful installation.
- User-tested cooperative cancellation on physical USB media.
- Automated GitHub Actions suite: see the release workflow run linked from the repository.

## 0.1.2 — 2026-11-02

### Windows UEFI media rewrite

- Replace the single GPT/FAT32 Windows USB layout with a GPT layout containing a large NTFS Basic Data partition and a 1 MiB FAT UEFI:NTFS helper partition at the end of the device.
- Mark the helper partition as Microsoft Basic Data, not EFI System Partition, and set GPT NoDriveLetter (GUID:63), avoiding the Windows Setup multiple-ESP issue.
- Set both the GPT helper-partition name and FAT volume label to `BMK_EFI`; change only a temporary copy of the verified upstream FAT image, preserving the pristine source and signed EFI binaries.
- Use the Rufus UEFI:NTFS helper image from a pinned upstream Rufus commit, with file-size, Git blob SHA-1 and SHA-256 verification.
- Read back and verify the written UEFI:NTFS helper image before continuing.
- Keep the original Windows `install.esd` / `install.wim` file unchanged; remove the ESD-to-WIM conversion and SWM splitting from the Windows path.
- Add optional full SHA-256 verification of copied Windows ISO files (off by default in Windows mode to avoid an unnecessary second full USB read).
- Preflight the ISO, the target geometry, helper image, and capacity before erasing the target device.
- Format NTFS with the correct partition-start sector required for Windows boot; explicitly set conventional 255/63 BPB geometry and 4 KiB clusters, then validate the NTFS boot sector signature and geometry before copying files.
- Prefer kernel NTFS3 for writing the USB payload, with ntfs-3g fallback.
- Use best-effort kernel `copy_file_range`, then `sendfile`, when hashing is disabled, with transparent streaming fallback if both cross-filesystem paths are unsupported.
- Throttle progress output and sync only the target USB filesystem.
- Scale the copy progress bar to the selected verification mode: without SHA-256 the copy itself reaches 96%; when verification is enabled, space is reserved for the second pass.
- Replace per-file fsync calls with one batched sync; optionally drop clean cached pages before SHA-256 read-back.
- Add tests for GPT layout, partition identifiers, ISO structure scanning, NTFS BPB geometry, copy_file_range fallback, progress throttling, mount-driver fallback and SHA-256 verification.
- Update Arch dependencies (`ntfsprogs`, `dosfstools`) and fetch/verify the pinned upstream UEFI helper image.
- Record the upstream helper components and their separate source/license references in `THIRD_PARTY_NOTICES.md`.

### Validation status

The user tested Windows 10 IoT Enterprise LTSC 2021 x64 media on the same Samsung RV511: Windows Setup copied files, passed the first reboot, and continued from the internal SSD to the next installation phase. Two USB 2.0 devices showed a substantial speed improvement after the NTFS3/kernel-copy optimizations. Linux raw/DD mode was also tested in Legacy/MBR mode. Secure Boot and broader hardware/ISO coverage remain future validation items.

## 0.1.1-alpha — 2026-11-01

- Baseline import of the original BootMediaKit GUI, raw writer and Windows FAT32/SWM workflow.
- ESD conversion to WIM and SWM splitting.
- Scrollable GUI and Arch-based installation.
