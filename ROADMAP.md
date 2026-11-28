English | [Magyar](ROADMAP.hu.md)

# Roadmap

BootMediaKit is a graphical, open-source USB creator for Linux: it writes disk images raw (DD/RAW) and makes Windows installation USB drives for UEFI (GPT) or Legacy BIOS (MBR) boot. It currently supports the Arch Linux family (CachyOS first).

This overview shows the direction; it is not a promise: the plan can change with the test results, and it gives no dates. Released changes are recorded in [CHANGELOG.md](CHANGELOG.md).

## Where we started

- **0.1.3 (2026-11-03):** the first stable Arch/CachyOS release. Raw (DD/RAW) writing of Linux disk images; Windows x64 UEFI installer on GPT with one large NTFS partition and one UEFI:NTFS helper partition; its own polkit action and a root-owned worker; the graphical interface runs without privileges.
- **0.2.1 (2026-11-05):** the first stable release of the 0.2.x line: safer disk writing, more reliable error and cancel handling, a more stable interface, broader regression tests.
- **0.2.2 (2026-11-10):** a maintenance release without new features: a more precise source file system check, a single version source, shell checks in CI, and loop-device integration tests with the real writers.
- **0.3.0 (2026-11-24):** a new Windows Legacy BIOS/MBR mode: one active NTFS partition with the GNU GRUB (i386-pc) chainloader installed on the computer. The Linux RAW and the Windows UEFI modes did not change.
- **0.4.0 (2026-11-27):** a responsive interface independent of the desktop environment: it follows the system's light/dark setting with a dark fallback and a manual switch, has a documented 880×550 minimum window size, and gives a clear error without an authentication agent. Fingerprint tests pin the behaviour of the three disk writers; it did not change. Physically checked under KDE Plasma, GNOME, XFCE, Cinnamon, MATE and LXQt.

The detailed development records of the closed versions: [docs/history/](docs/history/).

## Where we are

**0.5.0 – in development.** Goal: checking Windows 7 (Legacy only) and Windows 8/8.1 (Legacy and UEFI); support will cover only the versions actually tried. The previous release, 0.4.0, was completed on 2026-11-27.

The detailed development status: [docs/progress.md](docs/progress.md).

## Versions

| Version | Goal | Status |
|---|---|---|
| 0.4.0 | Responsive interface independent of the desktop environment, with a light/dark theme; the disk writers' behaviour pinned by tests; identifiers on the worker messages | done |
| 0.5.0 | Checking Windows 7 (Legacy only) and Windows 8/8.1 (Legacy and UEFI) | in development |
| 0.6.0 | Reliability regression closure before packaging: open physical tests, installation, upgrade, removal | planned |
| 0.7.0 | Common installation contract: file list, dependency inventory, only the files needed at run time in the package | planned |
| 0.8.0 | Hungarian language catalogue and translation infrastructure | planned |
| 0.8.1 | English language and a language selector ("HU / EN") | planned |
| 0.8.2 | Room for more languages without code changes | planned |
| 0.9.0 | Distribution-independent runtime capability layer | planned |
| 0.9.1 | Native Arch/CachyOS package (PKGBUILD) | planned |
| 0.9.2 | Debian/Ubuntu DEB package | planned |
| 0.9.3 | Documentation and publication package, in Hungarian and English | planned |
| 1.0.0 | Final, distributable release | planned |

An intermediate fix version (for example 0.5.1) is made only for a real bug that needs a separate fix.

## Decisions made

- **Windows 7:** only in Legacy BIOS (MBR) mode. The official Windows 7 SP1 ISO has no UEFI boot loader (`efi/boot/bootx64.efi`), and changing the installer image is not a goal.
- **Windows 8 and 8.1:** in both Legacy and UEFI mode. Support will cover only the versions actually tried.
- **32-bit UEFI:** 32-bit (IA32) UEFI is not supported; x86 Windows media is supported in Legacy BIOS mode only.
- **Distributions in 1.0.0:** Arch/CachyOS and Debian/Ubuntu, with native packages. The project adds one distribution family at a time and extends only after the previous one is stable.
- **Fedora (RPM):** not part of 1.0.0; it will be considered again after a bug-free 1.0.0.
- **AppImage:** not planned.
- **Flatpak:** not a goal, because the program works directly with block devices.
- The graphical interface and the disk-writing logic stay distribution-independent; package installation, dependency detection, desktop integration and polkit setup go into a separate, per-distribution layer.

## Deliberately not part of 1.0.0

- Linux persistence
- Windows To Go
- ISO download and ISO catalogue
- Writing several USB drives in parallel
- Combined BIOS+UEFI Windows USB drive
- Customising the Windows installer or converting WIM/ESD
- 32-bit UEFI
- Windows 7 in UEFI mode
- Fedora RPM, AppImage, Flatpak
- A promise of general support for every desktop environment and distribution

## Longer-term ideas

They may come after 1.0.0; none of them is a commitment.

- Combined BIOS+UEFI Windows USB drive with a single MBR
- Windows To Go and FreeDOS
- Linux persistence
- Health and capacity tests of USB drives
- Checking disk image checksums and publisher signatures
- Optional ISO download and ISO catalogue
- More flexible formatting options

## More documents

- [CHANGELOG.md](CHANGELOG.md): the changes of each release
- [docs/progress.md](docs/progress.md): the detailed development status of the current version
- [docs/history/](docs/history/): the development records of the closed versions
- [CONTRIBUTING.md](CONTRIBUTING.md): contributing
