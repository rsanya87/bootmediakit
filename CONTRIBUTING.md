# Contributing

BootMediaKit is an early-stage project. Reliability and data safety take priority over feature count.

## Before changing code

1. Check `ROADMAP.md` and existing issues for an already-known problem.
2. Keep the graphical frontend unprivileged. Privileged operations must remain in the narrowly scoped worker and be invoked only after explicit confirmation.
3. Revalidate the target block device immediately before any destructive operation. Never weaken the system-disk protection checks for convenience.
4. Add or update automated tests for every bug fix.
5. Document whether a test is mocked, unit-level, hardware-level, firmware-level, or a real Windows Setup test.

## Development environment

The current baseline targets Arch-based Linux and uses Python 3, PySide6, `parted`, `dosfstools`, `wimlib`, `7zip`, and polkit.

## Tests

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py version.py
bash -n install.sh uninstall.sh bootmediakit-worker
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

The GUI tests need `PySide6`. CI also runs `shellcheck -S warning install.sh uninstall.sh bootmediakit-worker` and, as root, the loop-device integration tests:

```bash
sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

See `docs/TESTING.md` for their requirements and skip conditions. The application version lives only in `version.py`; only a release commit may change it.

Do not claim that a physical-device or Windows Setup issue is fixed based only on unit tests. Real USB-writing tests must use disposable media.

## Pull requests

- Explain the problem and expected behavior.
- Include test results and the test level.
- Include relevant logs with personal paths, serial numbers, and unrelated identifiers removed.
- Update `CHANGELOG.md` and `ROADMAP.md` when appropriate.
