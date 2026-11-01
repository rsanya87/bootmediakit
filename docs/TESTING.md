# Testing

## Baseline 0.1.1-alpha import

Automated command:

```bash
python3 -m unittest discover -s tests -v
```

Recorded development result: 9 tests passed.

Additional static checks:

```bash
python3 -m py_compile app.py worker.py iso_utils.py
bash -n install.sh uninstall.sh
```

These checks validate Python syntax and shell syntax, not runtime behavior on every supported distribution.

## Known manual test result

One Windows Setup attempt using the BootMediaKit 0.1.1-alpha Windows UEFI/FAT32 path reached Setup but showed the “required media driver is missing” dialog. The same ISO reportedly works when prepared with Rufus on the same target PC. This is a confirmed reproducible report from one user setup, not yet a root-caused defect.

## Test levels

- Unit tests: automated with mocked system calls where appropriate.
- Integration tests: require a Linux host with the listed system tools.
- Hardware tests: require a disposable USB drive.
- Firmware tests: require booting the created USB on physical or virtual UEFI firmware.
- Windows Setup tests: require booting the USB and confirming that Setup can read the installation image.

Never describe a mocked unit test as proof that the USB-writing workflow works on real hardware.
