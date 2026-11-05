# Testing

## BootMediaKit 0.2.1 — Stable release (2026-11-05)

### Automated checks

The GitHub Actions suite passed on the final release-candidate source commit: [run 41980736701](https://github.com/rsanya87/bootmediakit/actions/runs/41980736701). The workflow covers:

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
