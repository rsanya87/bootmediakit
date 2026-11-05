# Roadmap

A feladat csak akkor tekinthető késznek, ha az automatizált ellenőrzések és a hozzá tartozó valós eszközös tesztek eredménye is rögzítve van.

## 0.2.1 — Stabilizálás és kiadásra jelölt változat

- [x] Aszinkron USB-meghajtó-felderítés Qt-folyamattal, időkorláttal és párhuzamos frissítés elleni védelemmel.
- [x] Forrás/cél fizikai meghajtó-ütközésvizsgálatának megerősítése Btrfs al-köteteknél és egymásra épülő autofs/CIFS csatolásoknál.
- [x] Biztonságos leállás, ha a forrásfájlt tartalmazó fájlrendszer fizikai meghajtója nem állapítható meg egyértelműen.
- [x] Worker-eseményküldés kezelése bezáródó GUI vagy megszakadt csővezeték esetén; a duplikált hibajelzés elkerülése.
- [x] Qt objektumok és gyermekfolyamatok rendezett leállítása az alkalmazás bezárásakor.
- [x] Qt SVG-megjelenítővel nem kompatibilis szűrőelem eltávolítása.
- [x] RAW írás előtti aláírástörlés és a műveleti sorrendet ellenőrző regressziós teszt.
- [x] Automatizált Python-, shell-, csomagolási és offscreen GUI-ellenőrzések.
- [x] Első fizikai RC smoke teszt: Linux Mint 22.3 Cinnamon DD/RAW indítása sikeres a legutóbbi RAW-író frissítéssel.
- [ ] Végső RC elfogadási teszt: Linux DD/RAW UEFI és Legacy BIOS módban, valamint Windows x64 UEFI telepítő az RC builddel. A Windows RC újratesztelése még függőben van.

## 0.2.2+ — Következő fejlesztési és tesztelési célok

- [ ] ISO kötetcímke-megőrzés tesztelése további Windows ISO-kon, szóközökkel és vegyes kis-/nagybetűkkel.
- [ ] További Windows-verziók és UEFI firmware-ek tesztelése.
- [ ] Secure Boot be- és kikapcsolt állapotának célzott vizsgálata több firmware-en.
- [ ] Célmeghajtó kihúzásának/visszacsatlakoztatásának, valamint a forrás céllemezen található esetének fizikai tesztje.
- [ ] Loop-device integrációs tesztek GPT, NTFS, FAT, hibakezelés és megszakítás utáni takarítás vizsgálatára.
- [ ] Arch PKGBUILD és reprodukálható csomagellenőrzések.
- [ ] Eszközkompatibilitási és hibadiagnosztikai információk bővítése az USB 2.0 írási sebesség romlása nélkül.
- [ ] Debian/Ubuntu támogatás felmérése; a disztribúciófüggő csomagtelepítés és Polkit-beállítás különválasztása az író logikától.
- [ ] Fedora támogatás felmérése a Debian/Ubuntu csomagolás megtervezése után.

## 0.1.3 — Korábbi stabil Arch/CachyOS kiadás

- [x] Linux ISOHybrid/DD írás ellenőrzése Legacy BIOS és UEFI módban.
- [x] Windows 10 IoT Enterprise LTSC 2021 x64 UEFI telepítés sikeres befejezése fizikai hardveren.
- [x] Eredeti Windows ISO kötetcímkéjének megőrzése az NTFS partíción; a `BMK_EFI` kizárólag az 1 MiB-os segédpartíció címkéje.
- [x] GPT Microsoft Basic Data + NoDriveLetter GUID:63 attribútum az UEFI:NTFS segédpartíción.
- [x] Rögzített upstream UEFI:NTFS segédkép ellenőrzése; csak az ideiglenes másolat címkézése.
- [x] Biztonsági ellenőrzések, saját Polkit akció, root tulajdonú worker-wrapper, célmeghajtó-azonosítás és együttműködő megszakítás.
- [x] Kompakt, képernyőmérethez igazodó GUI, saját ikon, látható verziószám, elteltidő-kijelzés és partíció-információs buborék.
- [x] Automatizált unit-, csomagolási és CI-ellenőrzések.
- [x] Az eredeti Windows Setup hiányzó médiaillesztő-problémájának lezárása (#2) a sikeres UEFI telepítés után.

## Későbbi platform- és funkciótámogatás

A projekt egyszerre egy disztribúciócsaládot céloz, és csak a jelenlegi Arch/CachyOS folyamat stabilizálása után bővíti a támogatott rendszereket.

1. Arch Linux család (elsőként CachyOS) — jelenlegi célplatform.
2. Debian és Ubuntu — tervezett támogatás.
3. Fedora — tervezett támogatás.

A grafikus felület és a lemezírási logika maradjon disztribúciófüggetlen. A csomagtelepítés, függőségfelismerés, asztali integráció és Polkit-konfiguráció külön disztribúciós adapterekbe kerüljön.

## Hosszabb távú ötletek

- Windows Legacy BIOS/CSM telepítő.
- Windows To Go és FreeDOS.
- Linux persistence.
- USB-meghajtó állapot- és kapacitástesztek.
- Lemezkép-ellenőrzőösszegek és kiadói aláírás ellenőrzése.
- Opcionális ISO-letöltés/katalógus.
- Rugalmasabb formázási lehetőségek.
