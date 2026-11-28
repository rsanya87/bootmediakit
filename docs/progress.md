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

A VM-es és a fizikai eredményt csak a gazda jelentheti; a jegyzőkönyvben külön oszlopba kerülnek. Az ISO-k (I1–I5): [TESTING.md](TESTING.md), „ISO test set (0.5.0)”.

**Szintek:**

1. A betöltő elindul.
2. A Setup felülete teljesen betölt, és a „Telepítés most” után eljut az első képernyőig (kiadáslista, termékkulcs vagy lemezválasztó); a jegyzőkönyvbe az kerül, melyik képernyőig jutott. Fizikai gépen itt megállunk; ha a Setup eljut a lemezválasztóig, ott is megállunk, belső lemezen nem lépünk tovább.
3. A fájlmásolás elindul.
4. Teljes telepítés és első indítás.

**Szabályok:**

- Fizikai gépen csak az 1–2. szint; belső lemezen soha nem lépünk tovább a lemezválasztónál.
- VM: QEMU, a boot-média `snapshot=on` módban, minden futásnál friss célmeghajtó; Legacy = SeaBIOS, UEFI = OVMF Secure Boot nélkül. Minden UEFI-teszt rekordja megmondja a Secure Boot állapotát (0.5.0-ban: ki).
- Pendrive: 8 GB elég az I1–I4-hez (az I3 adata ≈ 4,3 GB, 4 GB-os nem elég), 16 GB kell az I5-höz.
- Várakozás a 2. szint első képernyőjére (az ISO-szerkezet és a Setup ismert viselkedése alapján, nem mérés): az I1 és az I2 `sources/ei.cfg` fájlja `EditionID=Professional`, `Channel=Retail`, ezért a Setup valószínűleg nem mutat kiadáslistát, hanem a Professional kiadást telepíti; az I3-nál és az I4-nél nincs `ei.cfg`, így a Setup termékkulcsot kérhet. Az I2-nél ez mérés alapján bejött (fizikai gép, 2026-11-28: kulcskérés és kiadáslista nélkül, Professional, a lemezválasztóig); az I1, az I3 és az I4 továbbra is várakozás. Az ISO-kat nem módosítjuk (nincs `ei.cfg`/`PID.txt` beillesztés).
- A Windows 7 hivatalos médiája nem tartalmaz USB 3-meghajtót: modern, csak xHCI-portos gépen a Setup nem biztos, hogy látja a pendrive-ot. Ez ismert Windows 7-korlát, nem BootMediaKit-hiba (a support-szövegbe később kerül).

**I1 – Windows 7 SP1 x64 (hivatalos)**

- [ ] Legacy, VM: 2. szint
- [ ] Legacy, VM: 4. szint
- [ ] Legacy, fizikai (valódi BIOS-os gép): 2. szint
- [ ] UEFI: elutasítás ellenőrzése (T1/T2)

**I2 – Windows 7 SP1 x86 (hivatalos)**

- [ ] Legacy, VM: 2. szint
- [x] Legacy, fizikai (opcionális): 2. szint. *(A gazda jelentése, 2026-11-28; Lenovo G565 laptop; a pendrive a BootMediaKit 0.4.0 kiadással készült: „A gép elindul, a telepítő a lemezválasztóig eljut, kulcsot nem kér, fixen professional verzió (nincs verzióválasztó).”)*
- [ ] UEFI: elutasítás ellenőrzése (T1/T2)

**I3 – Windows 8.1 with Update x64 (hivatalos)**

- [ ] Legacy, VM: 2. szint
- [ ] Legacy, fizikai: 2. szint
- [ ] UEFI (Secure Boot ki), VM: 2. szint
- [ ] UEFI (Secure Boot ki), VM: 4. szint
- [ ] UEFI (Secure Boot ki), fizikai: 2. szint

**I4 – Windows 8.1 with Update x86 (hivatalos)**

- [ ] Legacy, VM: 2. szint
- [ ] Legacy, fizikai (opcionális): 2. szint
- [ ] UEFI: elutasítás ellenőrzése (T1/T2)

**I5 – harmadik féltől származó, integrált Windows 7 SP1 x64 kép (nem hivatalos)**

- [ ] Legacy, VM: 2. szint
- [ ] Legacy, VM: 3. szint (a 4 GiB-nál nagyobb `install.wim` NTFS-ről olvasása hiba nélkül halad-e)
- [ ] Legacy, fizikai (opcionális, modern gépen, USB 3): 2. szint
- [ ] UEFI (Secure Boot ki): extra, támogatási ígéret nélkül

**Minden kiadás előtt**

- [ ] A [REGRESSION_CHECKLIST.md](REGRESSION_CHECKLIST.md) kötelező pontjai.
