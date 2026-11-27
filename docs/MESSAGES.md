# Worker message identifiers

Every JSON event that `worker.py` sends to the GUI through `emit()` carries a stable identifier in `msg_id`, and its dynamic values (sizes, counters, device and path names) in `msg_args`. Both fields are **additive** (INVARIANTS C2): the existing fields (`message`, `log`, `error`, `percent`, `target_modified`, `worker_started`, `cancelled`) and their Hungarian texts are unchanged, and the GUI still shows those texts. In this release the GUI ignores `msg_id` and `msg_args`; they prepare a later translation of the worker's messages.

Rules:

- One identifier means one Hungarian `message` text (or text pattern). When the same message is sent from two places with the same meaning (for example a step shared by the UEFI and the Legacy writer), it has one identifier.
- `msg_args` holds the values that are inserted into `message` or `log`. Integers are plain JSON numbers; the Hungarian text shows them with `,` thousands separators. Paths are sent as text.
- Not arguments: the `error` text of `worker.self_check_failed`, `worker.cancelled` and `worker.failed` comes from the exception that stopped the operation, and the `log` of `worker.ntfs.ntfs3g_fallback` is the kernel mount error. These diagnostic texts have no identifiers yet.
- The `log` text of `worker.cancelled` and `worker.failed` depends on `target_modified` (whether the target had already been changed); that field is in every event.
- An event without `msg_id` (from an older worker) or with an unknown one is shown by its Hungarian texts.

`tests/test_messages.py` checks that every `emit()` call in `worker.py` passes a literal `msg_id` listed here, that the `msg_args` names match the table, and that one identifier is never used for two different messages. The writer fingerprint tests (`tests/test_writer_fingerprint.py`) compare the old fields byte for byte with the golden files and check the identifiers and arguments of every event of the six writer runs.

## Worker process

| `msg_id` | Message (Hungarian) | `msg_args` | Where |
|---|---|---|---|
| `worker.usage_error` | Hibás paraméterezés. | none | `main`: wrong number of arguments |
| `worker.not_root` | A háttérfolyamat nem kapott rendszergazdai jogosultságot. | none | `main`: not running as root |
| `worker.self_check_failed` | A privilegizált worker biztonsági ellenőrzése sikertelen. | none | `main`: installed paths, wrapper or polkit action check failed |
| `worker.started` | A BootMediaKit biztonságos háttérfolyamata elindult. | none | `main`: arguments accepted (`worker_started`) |
| `worker.cancelled` | A művelet biztonságosan megszakítva. | none | `main`: cooperative cancel, exit code 130 (`cancelled`) |
| `worker.failed` | A művelet megszakadt. | none | `main`: an error stopped the operation |

## Shared steps

| `msg_id` | Message (Hungarian) | `msg_args` | Where |
|---|---|---|---|
| `worker.disk.unmounting` | Meghajtó leválasztása: {mountpoint} | `mountpoint` (str): mount point being unmounted | `unmount_disk`, all writers |
| `worker.copy.progress` | Windows fájlok másolása… {done_bytes} / {total_bytes} bájt | `done_bytes` (int): bytes copied so far; `total_bytes` (int): bytes to copy | `copy_tree_progress`, both Windows writers |
| `worker.copy.fallback_sendfile` | A fájlrendszerek közötti gyorsmásolás nem érhető el; alternatív kernelmásolásra váltok. | none | `copy_tree_progress`: `copy_file_range` unsupported, `sendfile` used |
| `worker.copy.fallback_buffered` | A gyors kernelmásolás nem támogatott ezen a fájlrendszer-kombináción; kompatibilis adatmásolásra váltok. | none | `copy_tree_progress`: kernel copy unsupported, normal reads and writes used |
| `worker.copy.done` | Windows telepítőfájlok átmásolva. | none | `copy_tree_progress`, both Windows writers |
| `worker.ntfs.mounting_ntfs3` | NTFS kötet csatolása a Linux kernel NTFS3 driverével… | none | `mount_ntfs_volume`, both Windows writers |
| `worker.ntfs.ntfs3g_fallback` | A kernel NTFS3 driver nem érhető el; kompatibilitási tartalék: ntfs-3g… | none | `mount_ntfs_volume`: ntfs3 mount failed, ntfs-3g used |

## Windows writers (`write_windows_uefi`, `write_windows_bios`)

| `msg_id` | Message (Hungarian) | `msg_args` | Where |
|---|---|---|---|
| `worker.windows.uefi.scanning` | Windows ISO és UEFI:NTFS segédkép ellenőrzése… | none | UEFI writer: ISO and UEFI:NTFS image checks start |
| `worker.windows.bios.scanning` | Windows ISO ellenőrzése a Legacy BIOS módhoz… | none | Legacy writer: ISO checks start |
| `worker.windows.precheck_done` | ISO előellenőrzés kész; a pendrive-ot még nem módosítottam. | `boot_wim` (str): Windows PE image, relative to the ISO root; `install_image` (str): install image, relative to the ISO root; `iso_label` (str): ISO volume label; `copy_bytes` (int): bytes to copy | both writers, before the target is changed |
| `worker.windows.uefi.partitioning` | USB lemez leválasztása és GPT partíciók létrehozása… | none | UEFI writer |
| `worker.windows.uefi.layout_verified` | GPT ellenőrzése sikeres: két Microsoft Basic Data partíció; az UEFI:NTFS segédpartíció automatikus meghajtóbetűjel nélkül. | none | UEFI writer |
| `worker.windows.bios.partitioning` | USB lemez leválasztása és MBR partíció létrehozása… | none | Legacy writer |
| `worker.windows.bios.layout_verified` | MBR ellenőrzése sikeres: egy aktív NTFS partíció. | none | Legacy writer |
| `worker.windows.formatting_ntfs` | NTFS fájlrendszer létrehozása… | none | both writers |
| `worker.windows.uefi.writing_efi_partition` | BMK_EFI FAT indítópartíció telepítése… | none | UEFI writer, `write_uefi_ntfs_image` |
| `worker.windows.uefi.efi_partition_verified` | BMK_EFI FAT segédpartíció SHA-256 és kötetcímke visszaellenőrzése sikeres. | none | UEFI writer, `write_uefi_ntfs_image` |
| `worker.windows.copying` | Windows ISO fájlok másolása az NTFS partícióra… | none | both writers |
| `worker.windows.flushing` | A másolt adatok kiírása a pendrive-ra… | none | `copy_windows_files`, both writers |
| `worker.windows.verify.started` | USB-re másolt Windows fájlok SHA-256 visszaellenőrzése… | none | `copy_windows_files`, with verification |
| `worker.windows.verify.progress` | SHA-256 visszaellenőrzés… {done_bytes} / {total_bytes} bájt | `done_bytes` (int): bytes checked so far; `total_bytes` (int): bytes to check | `verify_copied_files` |
| `worker.windows.verify.done` | Minden telepítőfájl SHA-256 ellenőrzése sikeres. | none | `verify_copied_files` |
| `worker.windows.verify.skipped` | A teljes SHA-256 ellenőrzés kihagyva; az indítófájlok meglétét ellenőriztem. | none | `copy_windows_files`, without verification |
| `worker.windows.bios.installing_bootloader` | GRUB indító telepítése a pendrive-ra… | none | Legacy writer, `install_bios_chainloader` |
| `worker.windows.bios.bootloader_installed` | A GRUB indító települt; a partíciós tábla változatlan. | none | Legacy writer, `install_bios_chainloader` |
| `worker.windows.finishing` | Fájlrendszer kiürítése és leválasztása… | none | both writers |
| `worker.windows.uefi.done` | A Windows UEFI:NTFS telepítő USB elkészült. | none | UEFI writer, success |
| `worker.windows.bios.done` | A Windows Legacy BIOS telepítő USB elkészült. | none | Legacy writer, success |

## Linux RAW writer (`write_raw`)

| `msg_id` | Message (Hungarian) | `msg_args` | Where |
|---|---|---|---|
| `worker.raw.checking_target` | Célmeghajtó ellenőrzése… | `image` (str): source image path; `image_bytes` (int): image size; `device` (str): target device path; `target_bytes` (int): target size | before the target is changed |
| `worker.raw.wiping` | Régi partíciós és fájlrendszer-aláírások eltávolítása… | none | `wipefs` step |
| `worker.raw.write_started` | Lemezkép kiírása… | none | writing starts |
| `worker.raw.write_progress` | Lemezkép kiírása… {done_bytes} / {total_bytes} bájt | `done_bytes` (int): bytes written so far; `total_bytes` (int): image size | writing |
| `worker.raw.verify_started` | Visszaolvasás és adategyezőség ellenőrzése… | none | with verification |
| `worker.raw.verify_progress` | Ellenőrzés… {done_bytes} / {total_bytes} bájt | `done_bytes` (int): bytes compared so far; `total_bytes` (int): image size | with verification |
| `worker.raw.done_verified` | A lemezkép sikeresen kiírva és ellenőrizve. | none | success with verification |
| `worker.raw.done` | A lemezkép sikeresen kiírva. | none | success without verification |

## GUI texts (`app.py`)

Texts the GUI writes itself, with an identifier, through `gui_text()` in `app.py`; the text is translated by `tr()`, the identifier names it in the documentation and the tests. `tests/test_target_state.py` checks that this table and `gui_text()` list the same identifiers with the same texts.

| `msg_id` | Text (Hungarian) | Where |
|---|---|---|
| `gui.result.target_unknown` | A háttérfolyamat záró jelzés nélkül állt le, ezért nem tudjuk, módosult-e a célmeghajtó. A célmeghajtó részleges állapotban maradhat; újrahasználat előtt készítsd el újra. | log and failure dialog: the worker started, then ended without a closing event or abnormally (killed, crashed); fail-closed, INVARIANTS B3 |
| `gui.interrupt.untouched` | BootMediaKit: megszakítva (Ctrl+C). A háttérfolyamat nem indult el, a célmeghajtóhoz nem nyúltunk. | terminal (stderr) after Ctrl+C during an operation; the worker never started (for example at the pkexec password prompt) |
| `gui.interrupt.not_modified` | BootMediaKit: megszakítva (Ctrl+C). A worker jelezte, hogy a célmeghajtót nem módosította. | terminal after Ctrl+C; the worker's closing event reported the target unchanged and it exited normally |
| `gui.interrupt.complete` | BootMediaKit: megszakítva (Ctrl+C). A művelet előtte sikeresen befejeződött. | terminal after Ctrl+C; the operation had already succeeded |
| `gui.interrupt.partial` | BootMediaKit: megszakítva (Ctrl+C). A célmeghajtó részleges állapotban maradhat. | terminal after Ctrl+C in every other case (target changed or state unknown); nothing is printed when no operation ran |
| `gui.cancel.pending_authentication` | Megszakítás kérve; a hitelesítés után érvényesül. | status line: Megszakítás (or Ctrl+C) while pkexec still authenticates, before the worker started |
| `gui.cancel.before_authentication` | A megszakítás a hitelesítés után érvényesül, várhatóan a lemez módosítása előtt (ez nem szigorúan garantált). A hitelesítő ablak Mégse gombjával a művelet nem indul el, és a lemezhez nem nyúlunk. | log, same moment; the cancel line waits in the pipe and the worker reads it on a separate thread, so stopping before the first change of the target is expected but not strictly guaranteed (`docs/history/0.4.0.md`, deferred) |
| `gui.button.erase_and_write` | Törlés és írás | accept button of the final confirmation before writing (was Qt's Yes) |
| `gui.button.erase_this_drive` | Igen, ezt a meghajtót törlöm | accept button of the second confirmation for a large or non-removable drive |
| `gui.button.cancel` | Mégse | reject (default, Escape) button of both write confirmations (was Qt's Cancel) |
| `gui.button.stop` | Megszakítás | accept button of the Megszakítás confirmation |
| `gui.button.stop_and_close` | Megszakítás és bezárás | accept button of the close confirmation while an operation runs |
| `gui.button.continue` | Folytatás | reject (default, Escape) button of the Megszakítás and close confirmations |
| `gui.close.before_start` | A jelszókérés még folyamatban van, a pendrive írása még nem kezdődött el. A hitelesítő ablak Mégse gombjával a művelet nem indul el, és a lemezhez nem nyúlunk. Ha itt szakítod meg, a megszakítás a hitelesítés után érvényesül, várhatóan a lemez módosítása előtt; ezt nem garantáljuk szigorúan, a célmeghajtó részleges állapotban maradhat. Megszakítod és bezárod? | close confirmation while the worker has not started (two line breaks before the question); after it started the earlier text stays |
| `gui.cancel.confirm_before_start` | A jelszókérés még folyamatban van, a pendrive írása még nem kezdődött el. A hitelesítő ablak Mégse gombjával a művelet nem indul el, és a lemezhez nem nyúlunk. Ha itt szakítod meg, a megszakítás a hitelesítés után érvényesül, várhatóan a lemez módosítása előtt; ezt nem garantáljuk szigorúan, a célmeghajtó részleges állapotban maradhat. Biztosan megszakítod? | Megszakítás confirmation while the worker has not started (two line breaks before the question); after it started the earlier text stays |
