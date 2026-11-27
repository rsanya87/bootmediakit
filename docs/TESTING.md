# Testing

## BootMediaKit 0.3.0 — Stable release (2026-11-24)

0.3.0 adds the Windows Legacy BIOS/MBR mode. The Linux DD/RAW write sequence and the Windows UEFI GPT layout are unchanged from 0.2.2; their existing unit and integration tests pass unmodified.

### Automated checks

The GitHub Actions suite passed on the final pre-release source commit: [run 45436385317](https://github.com/rsanya87/bootmediakit/actions/runs/45436385317). The release commit after it changes only the version number and documentation. In addition to the 0.2.2 checks, the workflow now runs:

- 213 unit, packaging and offscreen GUI tests (129 in 0.2.2).
- Ten loop-device integration tests as root (three in 0.2.2): the T0 GRUB chainload gate with ntfs3 and ntfs-3g, the production `write_windows_bios` writer, a Legacy write over Windows UEFI media (no primary or backup GPT header left), and the existing RAW and Windows UEFI writer tests.
- With `BMK_QEMU=1`, three QEMU/SeaBIOS boots of Legacy media (T0 ntfs3, T0 ntfs-3g, production writer), each printing `BMK-BOOT-OK` from the test `bootmgr`.

The loop-device integration tests (10/10) also passed on the maintainer's CachyOS system during development (T7).

### Physical validation confirmed for 0.3.0

Reported by the maintainer on 2026-11-11 and 2026-11-24:

- **Windows Legacy BIOS on real hardware:** Windows 10 IoT Enterprise LTSC x64 and Windows 11 IoT Enterprise LTSC (x64; Windows 11 exists only as x64) Legacy media booted on a very old Core 2 Duo laptop; Windows Setup reached the partitioning screen. Installation was not continued.
- **Windows 7 SP1:** `hu_windows_7_professional_with_sp1_vl_build_x64_dvd_u_677833` written in Legacy (MBR) mode; Setup started.
- **Legacy layout:** `sfdisk -d` showed `label: dos`, `sector-size: 512` and one partition `start=2048, type=7, bootable`.
- **Legacy over former GPT media:** after a Legacy write on a drive that carried the Windows UEFI layout, `wipefs` showed only a `dos` entry, no `gpt`.
- **Manual QEMU check:** the finished Legacy drive showed Windows Setup in QEMU/SeaBIOS. With OVMF it did not boot.
- **UEFI-only firmware:** on a Gigabyte B850 D3HP with CSM disabled the Legacy drive was listed with a `UEFI:` prefix and started Windows Setup in UEFI mode (`PEFirmwareType` 0x2), presumably because the firmware's NTFS driver reads the ISO's own `efi\boot\bootx64.efi`. This is not treated as a defect; the GUI, the worker log and the READMEs say that the drive is made for Legacy BIOS/CSM and may start in UEFI only on firmware that reads NTFS.
- **Regression:** Windows UEFI mode (`sfdisk` output as expected, Setup started from UEFI on the maintainer's main computer) and Linux Mint DD/RAW (booted from UEFI and from a Legacy computer).
- **Host boot loader:** after the Windows UEFI test the maintainer's CachyOS system booted normally; the `grub` package was installed and Legacy writes had been made before.
- **Without GRUB:** after removing the `grub` package the Legacy option was greyed out with the correct note and hint; after reinstalling it the option was selectable again.
- **Verification:** SHA-256 verification (Windows) and full read-back (Linux RAW) worked; on a partly failing USB drive both reported a verification error.

### Release acceptance record

- Windows 10/11 IoT Enterprise LTSC x64 Legacy BIOS boot to Setup partitioning: passed.
- Windows 7 SP1 x64 Legacy BIOS, Setup start: passed.
- `sfdisk -d` MBR layout and `wipefs` after a former GPT: passed.
- Manual QEMU/SeaBIOS boot of the finished drive: passed.
- UEFI-only behaviour: does not boot without an NTFS driver (OVMF); started on a Gigabyte B850 with NTFS-reading firmware. Documentation reworded accordingly.
- Regression of Windows UEFI and Linux DD/RAW modes: passed.
- Host boot loader untouched; Legacy option disabled without GRUB: passed.
- Not physically tested: complete Windows installation from Legacy media (Setup was stopped at partitioning or the first screen); the items left open in 0.2.2 (Windows 11 26H2 Secure Boot off/on, the source-filesystem rejection message from a FUSE/network/overlay source, a `fuseblk` source, device refresh during unplug/replug).

Do not treat mocked unit tests or loop-device tests as proof of physical hardware behavior. Destructive tests must use disposable media only. Never use a drive containing the source ISO or user data as a test target.

## BootMediaKit 0.2.2 — Historical release test record (2026-11-10)

0.2.2 is a maintenance release. The write sequence and the Windows-mode GPT layout are unchanged from 0.2.1.

### Automated checks

The GitHub Actions suite passed on the final pre-release source commit: [run 42714445280](https://github.com/rsanya87/bootmediakit/actions/runs/42714445280). The release commit after it changes only the version number and documentation. In addition to the 0.2.1 checks, the workflow now runs:

- `shellcheck -S warning` on the installer, uninstaller and privileged worker wrapper.
- 129 unit, packaging and offscreen GUI tests.
- Three loop-device integration tests as root that run the real RAW and Windows writers against disk images (see [Loop-device integration tests](#loop-device-integration-tests)).

The same unit and integration tests also passed on the maintainer's CachyOS system (Python 3.14, util-linux 2.42).

### Physical validation confirmed for 0.2.2

- **Linux DD/RAW with read-back verification:** Linux Mint 22.3 media booted from physical USB in Legacy BIOS/MBR mode and in UEFI mode.
- **RAW over a former Windows-mode drive:** the same RAW write was made on a drive that carried the Windows-mode two-partition GPT immediately before; the result booted in both modes. On first boot Linux Mint created its own `writable` partition in the free space after the image; this is done by the live system, not by BootMediaKit.
- **Windows 10/11 IoT Enterprise LTSC, UEFI:** the media was created, the first partition carries the ISO volume label and the second is named `BMK_EFI`; the media boots as it did with 0.2.1.
- **Installed application:** `install.sh` installs `version.py`; the application starts and exits cleanly on CachyOS.

### Release acceptance record

- Linux DD/RAW boot in UEFI and Legacy BIOS/MBR modes, read-back enabled: passed.
- RAW write over a previous Windows-mode GPT: passed.
- Windows IoT LTSC media creation, partition names and boot: passed.
- `sfdisk -d` confirmation of the `GUID:63` attribute and Windows Setup up to its first reboot: not reported for 0.2.2 (verified on 0.2.1; covered for the attribute by the integration test).
- Windows 11 26H2 standard ISO with Secure Boot off and on: not repeated for 0.2.2 (verified on 0.2.1 to the disk-selection screen).
- The new source-filesystem rejection message on a FUSE/network/overlay source, an ISO on a `fuseblk` (ntfs-3g) disk, and device refresh during unplug/replug: not physically tested; covered by unit tests only.

Do not treat mocked unit tests or loop-device tests as proof of physical hardware behavior. Destructive tests must use disposable media only. Never use a drive containing the source ISO or user data as a test target.

## BootMediaKit 0.2.1 — Historical release test record (2026-11-05)

### Automated checks

The GitHub Actions suite passed on the final release-candidate source commit: [run 41980736701](https://github.com/rsanya87/bootmediakit/actions/runs/41980736701). The workflow covers:

- Python compilation for the GUI, worker, ISO helpers and UI helpers.
- Shell syntax checks for the installer, uninstaller and privileged worker wrapper.
- Download and hash verification of the pinned UEFI:NTFS helper image.
- A real-tool dry-run of NTFS formatting arguments.
- A test that brands a temporary copy of the UEFI:NTFS helper image `BMK_EFI` while leaving the pristine source unchanged.
- Unit, packaging and offscreen GUI tests for device safety, source/target collision detection, cancellation boundaries, Polkit packaging, GUI lifecycle, ISO metadata and GPT partition handling.

To run the checks locally, see [Running the automated tests](#running-the-automated-tests) below.

### Physical validation confirmed for 0.2.1

- **Linux DD/RAW:** Linux Mint 22.3 Cinnamon media booted successfully from physical USB in UEFI mode and in Legacy BIOS/MBR mode.
- **Windows IoT LTSC:** Windows 10 and Windows 11 IoT Enterprise LTSC x64 installation media completed UEFI installation successfully on the tested system(s).
- **Windows 11 26H2 standard ISO:** Windows Setup reached the disk-selection/partitioning screen with Secure Boot disabled and also with Secure Boot enabled. Installation beyond the partition-selection screen was not completed and is not claimed as a passed full-install test.
- **Secure Boot scope:** the successful 26H2 Setup launch confirms the observed boot path on the test firmware only. It does not establish compatibility with every UEFI implementation, certificate database or revocation state.

### Release acceptance record

- Linux DD/RAW boot in UEFI and Legacy BIOS/MBR modes: passed.
- Windows 10 and Windows 11 IoT Enterprise LTSC UEFI installations: passed.
- Windows 11 26H2 standard ISO, Secure Boot off and on, through Setup disk selection: passed to that stage.
- Windows 11 26H2 installation beyond disk selection: not tested.
- Additional firmware, non-Arch distributions, physical hot-unplug/replug races and source-on-target rejection remain outside this release's verified test matrix.

Do not treat mocked unit tests as proof of physical hardware behavior. Destructive tests must use disposable media only. Never use a drive containing the source ISO or user data as a test target.

## Running the automated tests

### Static checks, unit tests and offscreen GUI tests

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py theme.py fetch_uefi_ntfs.py version.py
bash -n install.sh uninstall.sh bootmediakit-worker
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

Runtime dependencies (the Arch packages `install.sh` installs, also listed in both READMEs and `CONTRIBUTING.md`): `pyside6`, `util-linux`, `parted`, `ntfs-3g`, `ntfsprogs`, `dosfstools`, `polkit`, `7zip`, `grub`. Test-only: the fonts DejaVu Sans and Noto Sans (Arch: `ttf-dejavu`, `noto-fonts`; Ubuntu CI: `fonts-dejavu-core`, `fonts-noto-core`, `fontconfig`), `shellcheck`, `desktop-file-utils`, and QEMU for the integration boot checks.

The GUI tests (`tests/test_app.py`) need `PySide6`. The modules of `tests/`, all run by this command without root:

- `test_worker.py`: unit tests of the privileged worker with mocked commands (target and source safety checks, Btrfs multi-device members, ISO labels, the UEFI GPT and Legacy MBR layouts, GRUB chainloader arguments and checks, RAW write and read-back, copy and SHA-256 verification, NTFS mounting, cancel and a broken GUI pipe, the worker modes). Proof level: unit/mock.
- `test_app.py`: offscreen GUI tests (start-up and shutdown stability, the GRUB availability check, the boot mode selector and the worker arguments it produces, the verification check box and the mode buttons).
- `test_ui_helpers.py`: the pure GUI helper functions (elapsed time, window profiles).
- `test_desktop_polkit.py`: the GUI's handling of pkexec exit codes 126/127 without starting any process other than `pkexec` with the fixed wrapper and `lsblk`, the unchanged polkit action and wrapper (pinned hashes), and the `.desktop` file (standard keys, `desktop-file-validate`).
- `test_packaging.py`: the installer, the polkit action scope and the root wrapper, the single version source, the documented test commands against CI, that CI cannot pass the integration step or the unit step by skipping, that the GUI quality suites below are discovered, that every test module is described here, and that the installer installs every local module the GUI needs and no test helper. It also checks the project documents: the public `ROADMAP.md`, the internal `docs/progress.md` and the closed release sections in `docs/history/` exist, `ROADMAP.md` and `docs/progress.md` name no file outside the repository (`roadmap/`), and every relative link and anchor in the Markdown files of the repository root and `docs/` resolves (external `http`/`https` links are not checked, no network is needed; fenced code blocks are skipped).
- `test_messages.py`: the worker message identifiers (`docs/MESSAGES.md`): an AST scan of every `emit()` call, `emit()` output with and without the new fields, the identifiers and arguments of every event in the six writer runs and on cancel and failure, and that the GUI ignores the new fields.
- `test_writer_fingerprint.py`, `test_theme.py`, `test_layout.py`, `test_i18n.py`: see the next section.

In CI the unit step fails if any test is skipped (`OK (skipped=…)`), so a missing tool or font cannot silently weaken the GUI, layout or packaging checks. CI also lints the shell scripts:

```bash
shellcheck -S warning install.sh uninstall.sh bootmediakit-worker
```

### Writer fingerprint, theme, layout and pseudo-locale tests (0.4.0)

All of them run in the normal `unittest discover -s tests` run, without root.

- **Writer fingerprints (`tests/test_writer_fingerprint.py`):** each frozen writer runs through `worker.main()` against files, with a fake command runner; the normalised timeline must match `tests/fixtures/writer_fingerprints/`. See `docs/INVARIANTS.md` A6 before changing a golden file; `BMK_UPDATE_WRITER_FINGERPRINTS=1` rewrites them and fails on purpose. Proof level: unit/mock.
- **Theme (`tests/test_theme.py`):** contrast of every colour-token pair (4.5:1 text, 3:1 large text and indicators) on light, dark, high-contrast and desktop-like palettes; system detection, dark fallback, the quick switch and its `QSettings` persistence (a temporary file, never the user's configuration); the fixed light palette equals Fusion's light palette and stays light under a dark Qt colour scheme (KDE-like and adw-gtk3-dark-like desktops); the switch matrix (`ThemeSwitchMatrixTests`): every mode pair in both directions on a light, a Breeze-like dark and an adw-gtk3-dark-like system, with DejaVu Sans and Noto Sans, gives the same window as a fresh start (grab, every widget's palette, style sheet, tooltip), also after a system scheme change while running; every widget is polished again on every switch; Qt's colour scheme override is never called; the results on a dark KDE-like desktop are unchanged. The system palettes are simulated; the real gtk3 and KDE platform themes were checked by hand offscreen (`QT_QPA_PLATFORMTHEME=gtk3` with adw-gtk3 6.5 and isolated GNOME settings, `QT_QPA_PLATFORMTHEME=kde`), not in CI.
- **Layout (`tests/test_layout.py`):** offscreen windows at the minimum size and at 1024×600, 1280×720 and 1366×700 logical pixels with 9 and 10 pt fonts, in every visible state (`UI_STATES`: RAW, Windows without ISO, Windows UEFI, Windows Legacy, with and without the "Legacy nem elérhető" hint) and with the real client size checked: no page scrollbar, no cut-off text on any visible button, label or combo box (`cut_off_texts`; elided labels excluded), every key control visible, inside the viewport and not overlapping another; the log scrolls inside; below the minimum (and with a 14 pt font at the minimum) the page scrolls and every control can still be scrolled into view; a run with `QT_SCALE_FACTOR=1.25` gives the same logical result.
- **Translatable texts and pseudo-locale (`tests/test_i18n.py`, helpers `tests/text_scan.py` and `tests/pseudo_locale.py`):** an AST scan of `app.py`, `theme.py` and `ui_helpers.py` fails on any user-visible text literal outside `tr()` unless it is one of the texts from before 0.4.0 listed in `tests/fixtures/legacy_untranslated_texts.json` (142 texts, 145 when the list was made; the list may only shrink, 0.8.0 converts them); every `tr()` argument must be a plain literal. The pseudo-locale makes every text about 40 % longer with accented letters, through a `QTranslator` for `tr()` texts and by replacing the older texts on the widgets, keeping markup and `{placeholders}`. With it, in every UI state and with 9 and 10 pt fonts: from 1024×600 up there is no page scrollbar and the full layout checks pass; at the 880×550 minimum the two columns stay, there is no horizontal scrollbar and no overlap, and every key control can be scrolled fully into view (the vertical scroll fallback is allowed there; approved deviation, see `docs/progress.md`). The pseudo-locale is a deliberate exaggeration, not a translation.
- **Target state after the worker ends (`tests/test_target_state.py`):** fail-closed (INVARIANTS B3). The event order of the six writer runs is read from the fingerprint golden files (read only); the worker is made to end after every event (118 points) in five ways (killed by SIGINT, SIGKILL or SIGTERM, exit 1 or 130 without a closing event): the GUI never says that the target was not changed and always shows the "unknown, may be partial" text (`gui.result.target_unknown`), also when the RAW writer dies during `wipefs`, whose event still says `target_modified: false`. A closing event (cancelled or failed) with a normal exit is trusted in both directions; a crash after it is not; a worker that never started is "untouched"; success stays success. The GUI text identifiers in `docs/MESSAGES.md` and `gui_text()` must match. Proof level: unit (GUI offscreen, events from the golden files, no worker process).
- **Ctrl+C in the terminal (`tests/test_terminal_interrupt.py`):** the real `main()` runs in a separate Python process with a shell in place of pkexec: it prints a password prompt, then the GUI and the shell get SIGINT together, like a terminal's process group. The program must exit with 130 without SIGSEGV or a `KeyboardInterrupt` traceback, the `finished` slot must run, the shell must stop on SIGINT and no dialog may open; also with the window closed at the same moment and without a running operation. The SIGINT handler only sets a flag, and the timer acts on it on the confirmed-close path. After Ctrl+C during an operation one line goes to the terminal (stderr), saying no more than the GUI's fail-closed target state: at the password prompt the worker never started ("a célmeghajtóhoz nem nyúltunk"), after the worker started without a closing event "A célmeghajtó részleges állapotban maradhat."; without an operation nothing is printed. Proof level: offscreen Qt with a real child process and real signals; not a polkit agent or a real pkexec.
- **Wrapping check box (`tests/test_app.py`):** the verification option is a text-less `QCheckBox` with a wrapping buddy label: a click on the label toggles it and gives the box focus, Space works on the box, the accessible name is the full text in both modes, a disabled box disables the label (disabled text colour at least 3:1 against the panel on the light and dark palette), and the setting still reaches the worker argument.

The minimum window size, 880×550 logical pixels (`MIN_WINDOW_WIDTH`/`MIN_WINDOW_HEIGHT` in `app.py`), was measured offscreen for the two-column layout at 880 px width in every visible state of the window: RAW, Windows without a recognised ISO, Windows UEFI, Windows Legacy, RAW and Windows with the "Legacy nem elérhető" hint, always with the danger warning shown. With the compact spacing tightened in T5 they need at most 524 px of height with a 9 pt and a 10 pt font (Noto Sans 524 px, DejaVu Sans 514 px); before that change 548 px. The first value, 880×540, had been measured in the start-up state only; after a mode change the page scrolled at it. The layout tests run in all these states (`UI_STATES` in `tests/test_layout.py`) and check the real client size of the window. 880×550 fits a 1280×800 screen at 125 % scaling (1024×640 logical) with a 44 px panel and a 40 px window frame (at most 556 px), so only 6 px are left; the desktop checks therefore measure it on KDE Plasma and XFCE. Offscreen measurements depend on the fonts of the machine: the layout and pseudo-locale tests therefore run with DejaVu Sans (wider; with it the T5 CI failure could be reproduced exactly) and Noto Sans, both must be installed (Ubuntu: `fonts-dejavu-core`, `fonts-noto-core`, `fontconfig`; Arch: `ttf-dejavu`, `noto-fonts`), and a missing one is an error, not a skip; CI installs and checks them. Desktop checks record the Qt logical work area, the desktop, Qt/PySide6 version, X11/Wayland, theme and scale. On Wayland Qt does not know the panels: `QScreen.availableGeometry()` equals the whole output (measured on GNOME 51.1 by the maintainer and on KDE Plasma on the development machine). When that is the case, the window keeps `WAYLAND_PANEL_RESERVE` = 60 logical px of height free (`ui_helpers.py`). It was 48 px (KDE Plasma's default 44 px panel plus 4 px, an estimate); it became 60 px after the maintainer's KDE log showed that KWin keeps 58 px free (`configure_bounds`, see below), with the maintainer's approval. It also covers GNOME's top bar (about 32 px in the maintainer's log); for other desktops and panel sizes it is still an estimate. Measured offscreen at a 1020×576 logical output (GNOME at 133 %), every UI state, DejaVu Sans and Noto Sans, 9 and 10 pt, at the real client size: with no frame (client 1020×516) the two-column layout stays and scrolls at most 8 px (Noto Sans 9 pt; 1 px with Noto Sans 10 pt, none with DejaVu Sans); with the 33 px frame of the VM (client 987×483) it scrolls at most 7 px with DejaVu Sans 9 pt, 31 px with DejaVu Sans 10 pt, 41 px with Noto Sans 9 pt and 34 px with Noto Sans 10 pt (with 48 px: none, 19, 29 and 22 px). No text is cut off, no horizontal scrollbar. On KDE Plasma at 1280×720 (client 1280×660) and at 120 % (1067×540) there is no scrolling with either font. The maintainer accepted the extra scrolling on GNOME at 133 %. The tests (`WaylandScaleChangeTests`, `UsableWorkAreaTests` in `tests/test_layout.py`) simulate the screen by patching `QScreen` and emit the real signals; the real compositor's answer is checked by the maintainer.

### Desktop test matrix (0.4.0)

The GUI must work the same under KDE Plasma, GNOME, XFCE, Cinnamon, MATE, LXQt and other Qt-capable sessions. The writer does not depend on the desktop, so a desktop needs no full write regression; the mandatory items of `docs/REGRESSION_CHECKLIST.md` are run on the main computer before a release. Only results reported by the maintainer are recorded here; everything else is "not tested".

Record for every check: desktop environment and version, distribution, Qt and PySide6 versions, X11 or Wayland, theme (light, dark, high contrast), display resolution and scale, the Qt logical work area and the system font. The logical work area and font, without root:

```bash
python3 -c 'from PySide6.QtWidgets import QApplication; a=QApplication([]); s=a.primaryScreen(); print(s.availableGeometry(), s.devicePixelRatio(), a.font().family(), a.font().pointSizeF())'
```

What to check: colours and automatic light/dark following, the sun/moon switch and restoring "Rendszer / Automatikus", the polkit dialog, the file dialog, the icon in the window, task bar, menu and window switcher, and at 1280×800 and 1366×768 with 100 % and 125 % scale no page scrollbar (with 150 % and 200 % and a larger font: nothing cut off or covered); the 880×550 minimum on KDE Plasma and XFCE (only 6 px to spare at 1280×800 with 125 %); after start-up: moving the window to a smaller monitor, undocking a laptop, and changing the resolution or scale while the program runs: the window stays inside the screen and "USB elkészítése" and "Megszakítás" stay reachable.

| Desktop | Theme | Session | Status |
|---|---|---|---|
| KDE Plasma (CachyOS, main computer) | light and dark | Wayland | reported: live theme switching (light, dark, automatic, manual light on the dark desktop), resolution/scale changes, moving the window to the smaller monitor, 1280×800 and 1366×768 at 100 % and 125 %, the 880×550 minimum at 1280×800 with 125 % (work area and frame not recorded), polkit dialog, file dialog, icons; pending: the write tests (`docs/REGRESSION_CHECKLIST.md`), 150 % and 200 % with a larger font (the remaining visual test), the remaining pixel value |
| GNOME, GTK theme `adw-gtk3-dark` | automatic (`color-scheme` default / prefer-dark / prefer-light), manual light and dark | Wayland only (the GNOME in the VM has no X11 session) | reported: automatic mode with `color-scheme` default, prefer-dark and prefer-light as expected, manual and automatic switching in every pair, the runtime scale change at 1360×768 (100 % → 133 %); cancel during the password prompt: not applicable on GNOME, the agent's dialog is modal, so Megszakítás and closing cannot be pressed during the prompt (approved by the maintainer, 2026-11-27); the correct-password branch was measured on XFCE; the polkit dialog, file dialog and icon in the dock and the overview: reported (the maintainer's test table, 2026-11-27) |
| GNOME, GTK theme `Adwaita` | automatic (`color-scheme` default / prefer-dark / prefer-light), manual light and dark | Wayland only (the GNOME in the VM has no X11 session) | reported: automatic mode with `color-scheme` default, prefer-dark and prefer-light as expected, manual and automatic switching in every pair, the runtime scale change at 1360×768 (100 % → 133 %); cancel during the password prompt: not applicable on GNOME, the agent's dialog is modal, so Megszakítás and closing cannot be pressed during the prompt (approved by the maintainer, 2026-11-27); the correct-password branch was measured on XFCE; the polkit dialog, file dialog and icon in the dock and the overview: reported (the maintainer's test table, 2026-11-27) |
| XFCE 4.20 (xfce4-session 4.20.4), VM | light and dark (GTK theme `adw-gtk3-dark`) | X11 | reported (the maintainer's test table, 2026-11-27): start and polkit password prompt, light and dark system theme with automatic mode, manual light/dark and back to automatic, file dialog and icons, 1280×800 and 1366×768 at 100 % and 125 % without a page scrollbar, the 880×550 minimum at 1280×800 with 125 % (work area and frame not recorded), resolution change while running; Megszakítás during the password prompt with the graphical agent, then Mégse, and then the correct password (see below). Recorded: polkit agent polkit-gnome, system font Sans 10 pt, Qt work area 1920×1053 at 1920×1080 (y = 27), Qt colour scheme dark |
| Cinnamon 6.8.2, VM | light and dark (GTK theme `Adwaita` when recorded) | X11 | reported (the maintainer's test table, 2026-11-27): start and polkit password prompt, light and dark system theme with automatic mode, manual light/dark and back to automatic, file dialog and icons, 1280×800 and 1366×768 at 100 % and 125 % without a page scrollbar, resolution change while running. Recorded: system font Adwaita Sans 11 pt, Qt work area 1964×1063 at 1964×1103, Qt colour scheme light; the information script found no separate polkit agent process (the password prompt appeared) |
| LXQt | system default | not recorded | reported (the maintainer's test table, 2026-11-26): start and polkit password prompt, light and dark system theme with automatic mode, manual light/dark and back to automatic, file dialog and icons, 1280×800 and 1366×768 at 100 % and 125 % without a page scrollbar, resolution change while running; recorded: system font DejaVu LGC Sans 12 pt, Qt work area 1920×1048 |
| MATE 1.28 (mate-session 1.28.2), VM | light and dark (GTK theme `BlackMATE` when recorded) | X11 | reported (the maintainer's test table, 2026-11-27): start and polkit password prompt, light and dark system theme with automatic mode, manual light/dark and back to automatic, file dialog and icons, 1280×800 and 1366×768 at 100 % and 125 % without a page scrollbar, resolution change while running. Recorded: polkit agent polkit-mate, system font Sans 10 pt, Qt work area 1920×1029 at 1920×1080 (y = 26), Qt colour scheme dark |
| Openbox, no polkit agent (VM, via SDDM) | system default | X11 | reported: clear error dialogs, the cancel and close texts during the password prompt, Ctrl+C handled without a crash, exit code 130 (measured 2026-11-27; closing the window at the same moment not measured); pkexec's textual agent fails with the correct password (upstream polkit, see below) |

Reported by the maintainer on 2026-11-25, KDE Plasma, Wayland, CachyOS, `dev/0.4.0` before the T5 changes:

- 32" 2K monitor at 100 % and 130 % scale: the window resizes dynamically, no page scrollbar; at 130 % the single-column layout still fits.
- 22" 1920×1080 monitor at 100 %: works; at 120 % the layout switches to two columns; no page scrollbar at 120 % and 130 %.
- Found: the menu arrow of the sun/moon button covered the icon. Fixed (`f4f898c`); not re-checked on the desktop yet.
- Not recorded: Plasma, Qt and PySide6 versions, the logical work area, the system font.
- Not tested yet on the main computer: the manual light mode on the dark KDE desktop (with the old code it showed Fusion's dark palette, measured offscreen with the KDE platform theme; fixed in `20a7d98`), then back to automatic and dark in every direction.
- Not tested yet: a laptop screen (1280×800, 1366×768), the 880×550 minimum on KDE Plasma and XFCE, a monitor, dock or resolution/scale change while the program runs, the other desktops, a session without a polkit agent, automatic theme following and restoring the system mode, and the layout after the T5 changes (tighter compact spacing, wrapping mode buttons and check box).

Reported by the maintainer on 2026-11-25, GNOME 51.1, Wayland, CachyOS in VirtualBox, `dev/0.4.0` at `55a212d`, at 1280×800 (100 % and 125 %), 1366×768 (133 %) and 1920×1080 (125 %):

- With the GTK theme `adw-gtk3-dark` and `color-scheme` `prefer-light`, Qt reports `ColorScheme.Dark` (`QT_QPA_PLATFORMTHEME` empty, platform `wayland`), so the automatic mode is dark while GNOME's own settings and libadwaita applications are light. With the GTK theme `Adwaita` Qt reports `Light` at once, and the window switches to light while running, and back to dark with `adw-gtk3-dark`; both looked correct. Qt follows the GTK theme name here, not GNOME's `color-scheme` (open finding A).
- Switching between manual "Sötét" and "Rendszer / Automatikus" while the automatic mode is also dark mixes the colours: the text colours change, the window and panel colours do not, and the text is hard to read. Other switches (automatic light ↔ automatic dark, manual light ↔ dark) were correct (open finding B).
- At 1366×768 with 133 %, changing the scale while the program runs leaves the bottom of the window (the button row) off the screen; after a restart it fits. Changing the scale while running at 1280×800 (100 % / 125 %) and 1920×1080 (125 %) was correct (open finding C).
- To be re-tested after the fixes: both GTK themes, automatic mode with `color-scheme` default, prefer-dark and prefer-light, every manual/automatic switch pair, and the scale change while running.
- Fixes since then, not yet re-tested on GNOME (finding B stays open until the maintainer reports): the manual light mode is light under a dark Qt colour scheme (`20a7d98`), and the appearance is applied one way and completely on every switch, without Qt's colour scheme override (`a031391`). Finding A is kept as a documented limitation (READMEs). Finding C: the diagnostic log showed that every signal arrives, but Qt reports the whole 1020×576 output as the work area on Wayland; fixed by the Wayland reserve (see above), not yet re-tested on GNOME or KDE.

Reported by the maintainer on 2026-11-26, KDE Plasma, Wayland, CachyOS (main computer), `dev/0.4.0` (commit not recorded), at 1440p, 1080p, 1280×960 and 1280×720, each at 100 % and 120 % scale:

- Switching the system theme between Breeze and Breeze Dark while the program runs: in automatic mode the window follows at once.
- Manual switches inside the program: no mixed colours and no drawing errors.
- In a manual mode a system theme change recolours only the window frame (drawn by the desktop); the program stays in the manual mode. This is the expected behaviour.
- Finding: at 1280×720 with 120 % (about 1067×600 logical) the bottom of the window is slightly cut off; the buttons are visible and clickable, no page scrollbar appeared. The maintainer considers it cosmetic because the buttons are usable; at 1280×800 it is correct. Analysis open (`docs/progress.md`).
- Not reported separately: each switch direction (for example manual "Világos" on the dark desktop, then back to automatic and dark), a scale change while the program runs, the Plasma, Qt and PySide6 versions and the system font.
- Answer to a question, same day: the slightly cut-off bottom is visible right after starting at 1280×720 with 120 %; the maintainer does not mind it and expects nobody to use such a small resolution with this scale. After changing the resolution or the scale while the program runs, the window stays in the single-column layout and its whole bottom is missing.

Diagnostic logs of the maintainer, 2026-11-26, same machine (a diagnostic script outside the repository: the program's own resize calls with their callers, every resize event with its size, and `WAYLAND_DEBUG=1`):

- Change while running, 2560×1440 → 1280×720 (scale stays 100 %) and 100 % → 120 %: KWin sends `xdg_toplevel.configure(880, 900)`, the size from before the change, in the same batch as the output change (`wl_output.mode`, `scale`), without new `configure_bounds`. The program fits the window first (`adapt_to_screen`: 880×672, then 880×552); 1 ms later Qt applies the queued configure (`ack_configure`, a spontaneous resize event 672 → 900, 552 → 900). The program made no resize call in between and gets no further signal, so the window stayed 900 px high on a 720 or 600 px output with the buttons outside the screen. Our code did not cause the 900; the compositor did. Fixed by the size guard (`COMPOSITOR_RESIZE_GUARD_MS`, `COMPOSITOR_RESIZE_CORRECTIONS` in `app.py`; `CompositorRestoresSizeTests` in `tests/test_layout.py`): on Wayland, for 2 s after fitting the window to a changed work area (restarted after each correction), a resize that does not come from the program and is larger than the work area is undone, at most twice per change; a fitting resize from outside ends the watch; maximized and full-screen windows, later resizes by the user and X11 are left alone. The 2 s limit is about 2000 times the measured delay and leaves room for a slow or busy machine (a VM). Not yet re-tested on the desktop.
- Start-up at 1280×720 with 120 %: KWin sends `configure_bounds(1067, 542)` with `configure(0, 0)`, and Qt limits the window to 960×542 itself, below the 880×550 minimum. At start-up at 2560×1440 the bounds were 2560×1382. KWin therefore keeps 58 logical px of height free on this machine (the output height minus the bounds); the program's Wayland reserve (`WAYLAND_PANEL_RESERVE`) is 48 px. KWin sends the bounds only at start-up, not after a change while the program runs, so there the reserve stays an estimate.
- Remaining difference after the fix (computed from the code and the logged values, not measured on the desktop): at start-up none, Qt follows KWin's bounds. After a change while running the window was fitted to the usable area with the 48 px reserve: client height 672 at 1280×720 and 552 at 1067×600 (Qt reports no frame for the server-side decoration on KDE Wayland), 10 px more than KWin's bounds (662 and 542). With the 60 px reserve (below) it is 660 and 540, 2 px less than KWin's bounds (computed). On the desktop the maintainer reported the bottom fully visible at 1280×720 with 120 %, at start-up and after a change while running; the remaining pixel value itself was not measured on KDE, nor on GNOME at 1360×768 with 133 %.

Re-tested by the maintainer on 2026-11-26 after the size guard (`741d0d4`): on KDE Plasma (Wayland) the resolution and scale change while the program runs (2560×1440 → 1280×720, then 100 % → 120 %) and on GNOME (Wayland, 1360×768, 100 % → 133 % while running, then a restart) the window is correct; on KDE only the few pixels coming from the reserve are missing at the bottom. The maintainer approved raising the reserve to 60 px, accepting a page scrollbar on GNOME at 133 % with a window frame.

Reported by the maintainer on 2026-11-26 after raising the reserve to 60 px (`33f7bc5`): on KDE Plasma (Wayland) at 1280×720 with 120 % the bottom of the window is fully visible in every case, at start-up and after a change while the program runs.

Reported by the maintainer on 2026-11-26, GNOME in the VM, after the one-way appearance fix (`a031391`): switching the colour modes no longer mixes the colours in any case; finding B is closed. Not reported separately: which GTK themes and `color-scheme` settings were used.

Reported by the maintainer on 2026-11-26, Openbox in the VM (no polkit agent; pkexec's own textual agent asks in the terminal), program started from a terminal:

- Ctrl+C at the password prompt: no crash; the terminal line appeared. The exit code was not measured.
- Megszakítás button and the window's X during the password prompt: the status line "Megszakítás kérve; a hitelesítés után érvényesül." and the button text "Megszakítás folyamatban…" appear; the window stays open until the password step ends (the approved plan A).
- Wrong password without a pending cancel: the dialog "A hitelesítés nem sikerült" (pkexec 127, the target was not changed) appears; the program does not quit silently.
- Closing the window or Megszakítás during the password prompt: the confirmation appeared; with a pending cancel and a wrong password, and with a pending cancel and the correct password, the program showed an error dialog and the USB drive stayed unchanged (`lsblk -f`: `sdb1` still the earlier Linux Mint ISO, `iso9660`). Starting without a polkit agent gave a clear error dialog.
- Environment finding, not a program error: in this VM (Openbox via SDDM, no graphical polkit agent, active logind session) pkexec's own textual agent fails with the correct password also without the program: plain `pkexec true` and `pkexec true </dev/null` both end with "==== AUTHENTICATION FAILED ====" and exit code 127, while `sudo` accepts the same password and the faillock table is empty. The journal shows `polkit-agent-helper-1: error response to PolicyKit daemon: ... No session for cookie` and polkitd "FAILED to authenticate"; a real wrong password shows a `pam_unix` authentication failure instead. The maintainer identified it as a known upstream polkit issue with the textual agent (https://gitlab.freedesktop.org/polkit/polkit/issues/17). So the earlier "cancel and correct password" failure says nothing about the cancel path; the full check (Megszakítás during the password prompt, then the correct password: the worker stops on the cancel, exit 130) is pending under GNOME with a graphical agent. The program's close and cancel paths only write the `cancel` line to pkexec's standard input and close it (checked with the real window and a shell in place of pkexec: no terminate, kill or signal); the cancel protocol is unchanged.
- Ctrl+C: the exit code 130 was not measured.

Reported by the maintainer on 2026-11-27, Openbox in the VM (no polkit agent), started from a terminal as `bootmediakit; echo $status`:

- Ctrl+C at the textual "Password:" prompt: no crash (earlier SIGSEGV), exit code 130 (`echo $status` printed 130), and the terminal line "BootMediaKit: megszakítva (Ctrl+C). A háttérfolyamat nem indult el, a célmeghajtóhoz nem nyúltunk." appeared.
- Not measured: closing the window at the same moment as Ctrl+C.
- At start-up the output showed "qt.svg.draw: The requested buffer size is too big, ignoring" four times. A known, cosmetic warning that does not block the release; its cause is not investigated (low priority, `docs/progress.md`).

Common to the XFCE, Cinnamon and MATE rows (the information script in the maintainer's test table, 2026-11-27): CachyOS in a VM, kernel 7.3.6-1-cachyos, X11 (Qt platform `xcb`), PySide6 6.12.0, Qt 6.12.1, Python 3.14.10, device pixel ratio 1.0, `dev/0.4.0` at `b2811dc` when the script ran; the scale and display values of the individual checks are in the table rows, not recorded here.

Reported by the maintainer on 2026-11-27, XFCE 4.20 (X11) in the VM with a graphical polkit agent (polkit-gnome), commit not recorded:

- Megszakítás during the password prompt, then Mégse in the polkit dialog: pkexec returns 126 ("Request dismissed"); the program says "A jelszókérő ablakot bezártad vagy megszakítottad, ezért a művelet nem indul el. A célmeghajtóhoz nem nyúlunk.", the log and the status line show the cancel, and "A célmeghajtót nem módosítottuk." appears. No crash. This is the expected behaviour.
- Megszakítás during the password prompt, then the correct password: the disk was not changed (the maintainer's check). This is the branch that could not be measured without an agent because of the textual agent's known polkit issue (above).
- Not measured: the exit code (130) and the worker's exact closing message.
- **A single measurement, not a guarantee:** stopping before the target is changed is expected but not strictly guaranteed, because the worker reads the `cancel` line on a separate thread (deferred, `docs/progress.md`).
- Under GNOME the graphical agent's dialog blocks the program window during the password prompt (the maintainer's test table): Megszakítás and closing cannot be pressed there; the correct password starts the operation, refusing the prompt shows the authentication error dialog and nothing is written. Approved by the maintainer (2026-11-27): the cancel check is not applicable on GNOME; the correct-password branch was measured on XFCE. The program's texts and code do not change; the user guide of the documentation phase (0.9.3) describes it (`docs/progress.md`, deferred).

### Loop-device integration tests

`tests/integration/` runs the real `worker.write_raw`, `worker.write_windows_uefi` and `worker.write_windows_bios` functions against a loop device backed by a disk image file. No physical drive is touched; all test files live on a private tmpfs that is unmounted afterwards.

```bash
sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

With `BMK_QEMU=1` the Legacy BIOS tests also boot the written disk image in QEMU with SeaBIOS (this is what CI runs):

```bash
sudo -E env BMK_INTEGRATION=1 BMK_QEMU=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

Skip conditions: every integration test is skipped unless `BMK_INTEGRATION=1` is set, the process is root, and `losetup`, `sfdisk`, `wipefs`, `mkfs.ext4`, `mkfs.ntfs` and `fatlabel` are available. A normal, non-root `unittest discover -s tests` run does not enter this directory. CI sets `BMK_INTEGRATION_REQUIRED=1`, which turns a missing precondition into an error so the step cannot pass by skipping.

The Legacy BIOS tests (`test_loop_windows_bios.py`) additionally need `grub-install` and the `/usr/lib/grub/i386-pc` directory (Arch: `grub`; Debian/Ubuntu CI: `grub-pc-bin` and `grub2-common`); the writer tests also need every program in `worker.WINDOWS_BIOS_PROGRAMS`. The ntfs-3g variants of the T0 tests are skipped when `ntfs-3g` is missing. The QEMU boot tests are skipped unless `BMK_QEMU=1` is set; with `BMK_QEMU=1`, a missing `qemu-system-x86_64`/`qemu-system-i386` is a skip, or an error under `BMK_INTEGRATION_REQUIRED=1`.

The worker itself additionally needs `lsblk`, `blockdev`, `findmnt`, `udevadm`, `partprobe`, `blkid`, `7z` and a working NTFS mount (kernel `ntfs3` or `ntfs-3g`); a missing one is reported as a test error, not a skip.

What the tests do:

- **RAW (`test_loop_raw.py`):** a 128 MiB image with an old two-partition GPT (ext4 on the first partition) is attached with `losetup --partscan`; a 40 MiB pseudo-random image with an MBR is written with `write_raw` and read-back verification. The test compares the written bytes with the source (`cmp`), checks that `wipefs` finds neither the primary nor the backup GPT signature (only the source's `dos` table), and that the kernel dropped the stale second partition. A second test keeps a stale partition open exclusively during the write; `wipefs` then fails without `--force`, so the test notices if that flag is dropped.
- **Windows (`test_loop_windows.py`):** a directory with the essential Windows Setup file names is bind-mounted in place of an ISO (`worker.mount_iso` and `worker.read_iso_volume_label` are replaced), and `write_windows_uefi` runs with SHA-256 verification on a 384 MiB image. The test checks the GPT (`sfdisk --json`: two Microsoft Basic Data partitions, the second named `BMK_EFI` with `GUID:63`), the NTFS label, the FAT label and the SHA-256 of every copied file. The pinned UEFI:NTFS image is taken from `BMK_UEFI_NTFS_IMAGE`, from the installed copy, or downloaded and verified with `fetch_uefi_ntfs.py`.

- **Windows Legacy BIOS (`test_loop_windows_bios.py`):** both groups use a test `bootmgr`: a few bytes of 16-bit real-mode code that writes `BMK-BOOT-OK` to the QEMU debug port (`0xE9`) and halts. With `BMK_QEMU=1` the image boots in `qemu-system-x86_64 -machine pc` (SeaBIOS, TCG, `snapshot=on`) and the test waits up to 60 s for that text; on failure it prints the GRUB and QEMU versions, the SeaBIOS log, the VGA text screen and, at a `grub>` prompt, the output of read-only GRUB commands.
  - `LoopWindowsBiosFeasibilityTests` (the T0 gate) builds the media itself, without the production writer: MBR with one active type-7 partition, NTFS with the production geometry, the kernel `ntfs3` or `ntfs-3g` driver, `grub-install --target=i386-pc` without `--force`, and a `grub.cfg` that runs `ntldr /bootmgr`. It checks the `55 AA` signature, non-empty MBR boot code, `core.img` in the gap before the partition, the unchanged partition table, the GRUB modules, and that the host's `/boot/grub` did not change. It stays as a writer-independent reference, so a GRUB or distribution change can be told apart from a writer bug.
  - `LoopWindowsBiosWriterTests` runs `write_windows_bios` with SHA-256 verification on a 256 MiB image; a directory with mixed-case Windows Setup file names (no EFI loader) is bind-mounted in place of the ISO. It checks `sfdisk --json` (`dos`, one active type-`7` partition from sector 2048 with the size `calculate_mbr_layout` gives), the NTFS label, the same static MBR checks, `grub/grub.cfg` against `worker.BIOS_GRUB_CFG`, the SHA-256 of every copied file and that only `/grub` was added, that no mount or `/run/bootmediakit-*` directory is left, and that the host's `/boot/grub` did not change. A second test first writes the image with `write_windows_uefi`, then with `write_windows_bios`, and checks that neither `wipefs` nor a direct read finds the primary or the backup GPT header. A third boots the written image in QEMU.

The loop device is a stand-in: `tests/integration/loop_helpers.py` makes `worker.lsblk_tree` report exactly the test's loop device as a removable `disk`. `validate_target` and every other safety check run unmodified. This substitution exists only in the test helper.

Known limits and problems:

- If the kernel or udev does not create the partition nodes (`/dev/loopNp1`, …) within 20 seconds, the test **fails** with a message pointing here; it does not pass silently. This happens in containers without udev and with kernels that have no partition-table parsers. Run the tests on a normal host or VM, or make sure `udevadm settle` works and `/dev` is a devtmpfs.
- These tests are not a substitute for physical USB tests. They give no evidence about partitions actually *used* by the kernel (mounted, swap, LUKS), about USB-specific properties (`rm`, `tran=usb`), about firmware boot, or about Windows Setup. The QEMU boot only shows that SeaBIOS, GRUB and the `ntldr` chainload reach a test `bootmgr`; it says nothing about the real Windows Boot Manager or Setup.

### Manual QEMU boot check of a finished USB drive

Before rebooting a physical computer, a finished Windows Legacy BIOS drive can be booted in QEMU with SeaBIOS. The check below never writes to the drive: QEMU runs as your normal user with **read-only** access to the device, and `snapshot=on` sends the guest's writes to a temporary file. (`readonly=on` is not used because QEMU refuses read-only IDE disks: "Block node is read-only".)

1. Plug in the drive, do not mount it, and find its device name (`/dev/sdX` below) by size, model and `TRAN` = `usb`:

   ```bash
   lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS
   ```

2. Give your user read-only access to that device node. The entry disappears when the drive is unplugged. This only limits QEMU if your user is not in the `disk` group (check with `id -nG`); members of that group can already write to every disk, so do not run the check from such an account:

   ```bash
   sudo setfacl -m u:"$USER":r /dev/sdX
   ```

3. Boot it in QEMU (`-machine pc` uses SeaBIOS, i.e. Legacy BIOS):

   ```bash
   qemu-system-x86_64 -machine pc -accel kvm -cpu host -m 4096 -drive file=/dev/sdX,format=raw,if=ide,snapshot=on -boot c
   ```

   Without KVM use `-accel tcg -cpu max` instead of `-accel kvm -cpu host`; Windows Setup is then very slow. Expected result: the Windows Setup screen appears. Close the QEMU window there; do not install. Do not use the QEMU monitor's `commit` command (or `Ctrl-A s`), which would try to write the temporary changes back.

4. Remove the access entry (or unplug the drive):

   ```bash
   sudo setfacl -x u:"$USER" /dev/sdX
   ```

If `-machine pc` is replaced by `-machine q35 -bios /usr/share/edk2/x64/OVMF.4m.fd` (Arch package `edk2-ovmf`; the firmware path can differ between distributions), the drive is expected **not** to boot, because OVMF has no NTFS driver. This does not prove that the drive never starts in UEFI mode: UEFI firmware that reads NTFS can start the ISO's own `efi/boot/bootx64.efi` from the NTFS partition (seen on a Gigabyte B850 board with CSM disabled, see [docs/history/0.3.0.md](history/0.3.0.md)). Neither check replaces a test on the real computer.

## BootMediaKit 0.1.3 — Historical release test record

### Automated checks

The 0.1.3 GitHub Actions workflow ran:

- Python compilation for the GUI, worker, ISO helpers and UI helpers.
- Shell syntax checks for the installer, uninstaller and privileged worker wrapper.
- Download and hash verification of the pinned UEFI:NTFS helper image.
- A real-tool dry-run of NTFS formatting arguments.
- Unit and packaging tests for disk identity, source/target collision detection, protected volume rejection, cancellation boundaries, Polkit packaging, responsive UI, ISO label parsing and GPT partition naming.

### Physical validation reported by the user

- **Linux DD/RAW:** a Linux ISO written in DD mode booted successfully on tested hardware in both Legacy BIOS and UEFI modes.
- **Windows UEFI:** Windows 10 IoT Enterprise LTSC 2021 x64 booted from the created USB and completed installation in UEFI mode.
- **Cancellation:** the user cancelled a physical USB creation operation; the worker stopped safely and the USB remained usable for a subsequent attempt.
- **Write performance:** successful creation was reported on different USB 2.0 drives, with elapsed times varying by the individual drive.
- **Polkit and application installation:** the installed package was used on CachyOS; the GUI and privileged worker completed a Windows USB creation.

### Still requiring broader validation

- Secure Boot enabled/disabled on multiple firmware implementations.
- Physical target hot-unplug/replug race testing.
- Physical source-on-target rejection test.
- LUKS/LVM/RAID/swap rejection on disposable devices.
- Additional Windows ISO families and non-CachyOS distributions.

Do not claim physical hardware behavior based only on unit tests.
