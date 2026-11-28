# Fejlesztési állapot (belső)

Ez a fájl a fejlesztés belső állapotkövetője: az aktuális verzió feladatai, a jóváhagyott eltérések a munkaleírástól, a halasztott tételek és a fizikai tesztek. A nyilvános áttekintés: [ROADMAP.hu.md](../ROADMAP.hu.md); a lezárt kiadások szakaszai: [history/](history/).

A feladat akkor tekinthető késznek, ha az automatizált ellenőrzések és a hozzájuk tartozó valós eszközös tesztek eredménye is rögzítve van.

## 0.5.0 — Fejlesztés alatt: Windows 7 (Legacy) és Windows 8/8.1 (Legacy és UEFI) minősítése

A kötelező szabályok: [docs/INVARIANTS.md](INVARIANTS.md), a korábbi hibák: [docs/LESSONS.md](LESSONS.md), a kiadás előtti fizikai ellenőrzőlista: [docs/REGRESSION_CHECKLIST.md](REGRESSION_CHECKLIST.md).

**Cél:** a Windows 7, 8 és 8.1 telepítő ISO-k működését külön-külön igazolni; a Windows 10/11 sikere nem bizonyítja a régebbi telepítőkét. A támogatási ígéret csak a ténylegesen kipróbált ISO-kra és módokra terjed ki. Windows 7: csak Legacy BIOS (MBR); Windows 8/8.1: Legacy és UEFI.

### Állapot

- [ ] T0. Ág, ISO-tesztkészlet jegyzőkönyve (a gazda adatai alapján)
- [ ] T1. ISO-felismerés ellenőrzése az összes tesztelt változaton (csak `scan_windows_iso`/GUI-módválasztás)
- [ ] T2. Windows 7 UEFI elutasítása érthető hibával (fail-closed)
- [ ] T3. Loop/QEMU ellenőrzés a termelési íróval (SeaBIOS, OVMF) a minősített változatokra, ahol lehetséges
- [ ] T4. Dokumentáció: csak bizonyított kompatibilitás
- [ ] T5. Kiadási commit

### Meghozott döntések

- **32 bites UEFI (a gazda döntése, 2026-11-28):** a 32 bites (IA32) UEFI nem támogatott; az x86 Windows adathordozó csak Legacy BIOS módban támogatott. Kódváltoztatás nem kell: a worker UEFI-előellenőrzése (`scan_windows_iso`) az `efi/boot/bootx64.efi` nélküli ISO-t már ma elutasítja, a pendrive első írása előtt. A GUI előzetes jelzése (ilyen ISO-nál ne ajánlja fel a UEFI módot, érthető üzenettel) a T1/T2 feladata. Nyilvánosan: `ROADMAP.md`/`ROADMAP.hu.md`, „Decisions made” / „Meghozott döntések”.
- **Secure Boot (a gazda döntése, 2026-11-28):** a Windows 7 / 8.1 adathordozók Secure Boot-viselkedését a 0.5.0-ban nem teszteljük; „nem tesztelt” marad, és a 0.6.0 Secure Boot-ellenőrzései közé kerül. Nyilvánosan: `docs/TESTING.md`/`docs/TESTING.hu.md`, az ISO-tesztkészlet szakasz vége.

### Jóváhagyott és dokumentált eltérések a munkaleírástól

- **A T0 előtt: a dokumentumok kétnyelvűsítése (a gazda kérése, 2026-11-27).** A felhasználóknak és közreműködőknek szóló dokumentumok angolul (eredeti fájlnév) és magyarul (`.hu.md`) is elérhetők: README, CONTRIBUTING, ROADMAP, docs/TESTING. A CHANGELOG, a kiadási jegyzetek, a THIRD_PARTY_NOTICES és a LICENSE csak az eredeti nyelvükön maradnak; a karbantartói dokumentumok (INVARIANTS, LESSONS, REGRESSION_CHECKLIST, progress, history/, MESSAGES) egynyelvűek. Csak dokumentáció és doksi-tesztek; a kód, a worker, a writerek és a golden fájlok nem változnak.

### Későbbre halasztva

- A 0.4.0-ból nyitva maradt halasztott tételek: [docs/history/0.4.0.md](history/0.4.0.md), „Későbbre halasztva”.

### Fizikai és kézi tesztek (a gazda végzi; csak az ő visszajelzése alapján pipálva)

- A lista a T0-ban, a gazda ISO-tesztkészlete alapján készül.
