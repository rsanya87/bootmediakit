# Testing

## BootMediaKit 0.2.1 — Release Candidate 1

### Automated checks

The GitHub Actions workflow on the RC branch is the required automated release gate. RC1 run 41980555416 passed: https://github.com/rsanya87/bootmediakit/actions/runs/41980555416. It runs:

- Python compilation for the GUI, worker, ISO helpers and UI helpers.
- Shell syntax checks for the installer, uninstaller and privileged worker wrapper.
- Download and hash verification of the pinned UEFI:NTFS helper image.
- A real-tool dry-run of NTFS formatting arguments.
- A test that brands a temporary copy of the UEFI:NTFS helper image `BMK_EFI` while leaving the pristine source unchanged.
- Unit, packaging and offscreen GUI tests for device safety, source/target collision detection, cancellation boundaries, Polkit packaging, GUI lifecycle, ISO metadata and GPT partition handling.

Run locally:

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py
bash -n install.sh uninstall.sh bootmediakit-worker
python3 -m unittest discover -s tests -v
```

### Physical validation status

- **Linux DD/RAW:** Linux Mint 22.3 Cinnamon ISO was successfully booted from physical USB media after the latest RC RAW-writer update. This is an initial smoke test, not yet the complete release matrix.
- **Windows UEFI:** Windows x64 UEFI media must be recreated and retested using the 0.2.1 RC build before final release. The earlier 0.1.3 Windows 10 IoT Enterprise LTSC 2021 test is historical validation only.
- **Legacy BIOS:** confirm Linux DD/RAW boot again on the RC build with an ISO that supports Legacy BIOS.
- **Read-back:** run at least one RAW write with full read-back verification enabled.
- **GUI lifecycle:** confirm normal launch, device refresh and clean application exit.

### RC acceptance checklist

- Linux Mint 22.3 Cinnamon DD/RAW boot (UEFI; Legacy BIOS where supported by the test machine).
- RAW full read-back verification.
- Windows 10 IoT Enterprise LTSC 2021 x64 UEFI media creation and setup continuation through the first reboot.
- Verify the Windows USB GPT layout, preserved source ISO volume label, and `BMK_EFI` helper partition metadata.
- Confirm that the GUI starts and exits cleanly on the target CachyOS environment.

Do not treat mocked unit tests as proof of physical hardware behavior. Destructive tests must use disposable media only. Never use a drive containing the source ISO or user data as a test target.

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
