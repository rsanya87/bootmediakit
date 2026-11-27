English | [Magyar](CONTRIBUTING.hu.md)

# Contributing

BootMediaKit is an early-stage project. Reliability and data safety take priority over feature count.

## Before changing code

Read these first (Hungarian): [`docs/INVARIANTS.md`](docs/INVARIANTS.md) lists the rules no change may break (the three writers are frozen), [`docs/LESSONS.md`](docs/LESSONS.md) the mistakes that already happened, and [`docs/REGRESSION_CHECKLIST.md`](docs/REGRESSION_CHECKLIST.md) the physical checks the maintainer runs before every release. A new worker message needs a `msg_id` listed in [`docs/MESSAGES.md`](docs/MESSAGES.md).

1. Check `ROADMAP.md`, `docs/progress.md` and existing issues for an already-known problem.
2. Keep the graphical frontend unprivileged. Privileged operations must remain in the narrowly scoped worker and be invoked only after explicit confirmation.
3. Revalidate the target block device immediately before any destructive operation. Never weaken the system-disk protection checks for convenience.
4. Add or update automated tests for every bug fix.
5. Document whether a test is mocked, unit-level, hardware-level, firmware-level, or a real Windows Setup test.

## Maintainer documents

The maintainer documents exist in one language only, so that each change is made once:

- In Hungarian: [docs/INVARIANTS.md](docs/INVARIANTS.md), [docs/LESSONS.md](docs/LESSONS.md), [docs/REGRESSION_CHECKLIST.md](docs/REGRESSION_CHECKLIST.md), [docs/progress.md](docs/progress.md) and the closed release records in [docs/history/](docs/history/).
- [docs/MESSAGES.md](docs/MESSAGES.md) describes the message identifiers in English; the interface texts in it are the program's Hungarian source texts.
- [CHANGELOG.md](CHANGELOG.md), the release notes and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) are in English only.

The user and contributor documents exist in English (the original file name) and in Hungarian (the same name with `.hu.md`): README, CONTRIBUTING, ROADMAP and `docs/TESTING`. A change to one of them updates both languages.

## Development environment

The current baseline targets Arch-based Linux. The runtime dependencies are the Arch packages `install.sh` installs and both READMEs list: `pyside6`, `util-linux`, `parted`, `ntfs-3g`, `ntfsprogs`, `dosfstools`, `polkit`, `7zip` and `grub` (only `grub-install` and the i386-pc modules, for the Windows Legacy BIOS mode). `wimlib` is not used since 0.1.2 (no WIM splitting). The tests additionally need the fonts DejaVu Sans and Noto Sans (Arch: `ttf-dejavu`, `noto-fonts`), `shellcheck`, `desktop-file-utils`, and for the QEMU boot checks of the integration tests `qemu-system-x86_64` (Arch: `qemu-system-x86`).

## Tests

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py theme.py fetch_uefi_ntfs.py version.py
bash -n install.sh uninstall.sh bootmediakit-worker
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

The GUI tests need `PySide6`. CI also runs `shellcheck -S warning install.sh uninstall.sh bootmediakit-worker` and, as root, the loop-device integration tests:

```bash
sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

To include the QEMU/SeaBIOS boot check of the Windows Legacy BIOS media, as CI does:

```bash
sudo -E env BMK_INTEGRATION=1 BMK_QEMU=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

See `docs/TESTING.md` for their requirements and skip conditions, and for a read-only manual QEMU check of a finished USB drive. The application version lives only in `version.py`; only a release commit may change it.

Do not claim that a physical-device or Windows Setup issue is fixed based only on unit tests. Real USB-writing tests must use disposable media.

## Pull requests

- Explain the problem and expected behavior.
- Include test results and the test level.
- Include relevant logs with personal paths, serial numbers, and unrelated identifiers removed.
- Update `CHANGELOG.md` and `docs/progress.md` when appropriate.
