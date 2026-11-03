# Testing

## BootMediaKit 0.1.3 release test record

### Automated checks

The GitHub Actions workflow runs:

- Python compilation for the GUI, worker, ISO helpers and UI helpers.
- Shell syntax checks for the installer, uninstaller and privileged worker wrapper.
- Download and hash verification of the pinned UEFI:NTFS helper image.
- A real-tool dry-run of NTFS formatting arguments.
- A test that labels a temporary copy of the UEFI:NTFS helper image `BMK_EFI` while leaving the pristine source unchanged.
- Unit and packaging tests for disk identity, source/target collision detection, protected volume rejection, cancellation boundaries, Polkit packaging, responsive UI, ISO label parsing and GPT partition naming.

Run locally:

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py
bash -n install.sh uninstall.sh bootmediakit-worker
python3 -m unittest discover -s tests -v
```

### Physical validation reported by the user

- **Linux DD/RAW:** a Linux ISO written in DD mode booted successfully on tested hardware in both Legacy BIOS and UEFI modes.
- **Windows UEFI:** Windows 10 IoT Enterprise LTSC 2021 x64 booted from the created USB and completed installation in UEFI mode.
- **Cancellation:** the user cancelled a physical USB creation operation; the worker stopped safely and the USB remained usable for a subsequent attempt.
- **Write performance:** the user reported successful creation on different USB 2.0 drives, with elapsed times varying by the individual drive. No performance-tuning change was made during the final UI refinements.
- **Polkit and application installation:** the safety-alpha package was installed and used on CachyOS; the GUI and privileged worker completed a Windows USB creation.

### Still requiring broader validation

- Secure Boot enabled/disabled on multiple firmware implementations.
- Physical target hot-unplug/replug race testing.
- Physical source-on-target rejection test.
- LUKS/LVM/RAID/swap rejection on disposable devices.
- Additional Windows ISO families and non-CachyOS distributions.
- The original ISO volume-label preservation change in this release: automated label parsing and `sfdisk` GPT write/read-back tests are included; confirm the actual NTFS and GPT labels on a newly created USB.

Do not treat mocked unit tests as proof of physical hardware behavior. Destructive tests must use disposable media only. Never use a drive containing the source ISO or user data as a test target.
