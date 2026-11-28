[English](ROADMAP.md) | Magyar

# Roadmap

A BootMediaKit grafikus, nyílt forráskódú USB-készítő Linuxra: lemezképeket ír ki nyersen (DD/RAW), és Windows telepítő pendrive-ot készít UEFI (GPT) vagy Legacy BIOS (MBR) indításhoz. Jelenleg az Arch Linux családot támogatja (elsőként a CachyOS-t).

Ez az áttekintés az irányt mutatja, nem ígéret: a terv a tesztek eredményei szerint változhat, és dátumot nem vállal. A megjelent változásokat a [CHANGELOG.md](CHANGELOG.md) rögzíti.

## Honnan indultunk

- **0.1.3 (2026-11-03):** az első stabil Arch/CachyOS kiadás. Linux lemezképek nyers (DD/RAW) írása; Windows x64 UEFI telepítő GPT-n, egy nagy NTFS partícióval és egy UEFI:NTFS segédpartícióval; saját polkit-akció és root tulajdonú worker, a grafikus felület jogosultság nélkül fut.
- **0.2.1 (2026-11-05):** a 0.2.x sor első stabil kiadása: biztonságosabb lemezírás, megbízhatóbb hiba- és megszakításkezelés, stabilabb felület, bővebb regressziós tesztek.
- **0.2.2 (2026-11-10):** karbantartó kiadás új funkció nélkül: pontosabb forrás-fájlrendszer-ellenőrzés, egyetlen verziószám-forrás, shell-ellenőrzés a CI-ben, és loop-eszközös integrációs tesztek a valódi írókkal.
- **0.3.0 (2026-11-24):** új Windows Legacy BIOS/MBR mód: egyetlen aktív NTFS partíció a gépre telepített GNU GRUB (i386-pc) láncbetöltőjével. A Linux RAW és a Windows UEFI mód nem változott.
- **0.4.0 (2026-11-27):** asztali környezettől független, reszponzív felület: a rendszer világos/sötét beállításának követése sötét tartalékkal és kézi váltóval, dokumentált 880×550-es minimális ablakméret, érthető hiba hitelesítési ügynök nélkül. A három lemezíró viselkedését ujjlenyomat-tesztek rögzítik; nem változott. Fizikailag KDE Plasma, GNOME, XFCE, Cinnamon, MATE és LXQt alatt ellenőrizve.

A lezárt verziók részletes fejlesztési naplója: [docs/history/](docs/history/).

## Hol tartunk

**0.5.0 – fejlesztés alatt.** Cél: a Windows 7 (csak Legacy) és a Windows 8/8.1 (Legacy és UEFI) ellenőrzése; a támogatás csak a ténylegesen kipróbált változatokra fog vonatkozni. Az előző kiadás, a 0.4.0, 2026-11-27-én készült el.

A fejlesztés részletes állapota: [docs/progress.md](docs/progress.md).

## Verziók

| Verzió | Cél | Állapot |
|---|---|---|
| 0.4.0 | Asztali környezettől független, reszponzív felület világos/sötét témával; a lemezírók viselkedésének tesztes rögzítése; azonosítók a worker üzenetein | kész |
| 0.5.0 | Windows 7 (csak Legacy) és Windows 8/8.1 (Legacy és UEFI) ellenőrzése | fejlesztés alatt |
| 0.6.0 | Megbízhatósági regressziózárás a csomagolás előtt: nyitott fizikai tesztek, telepítés, frissítés, eltávolítás | tervezett |
| 0.7.0 | Közös telepítési szerződés: fájllista, függőségleltár, a csomagban csak a futáshoz szükséges fájlok | tervezett |
| 0.8.0 | Magyar nyelvi katalógus és fordítási infrastruktúra | tervezett |
| 0.8.1 | Angol nyelv és nyelvválasztó („HU / EN”) | tervezett |
| 0.8.2 | További nyelvek befogadása kódmódosítás nélkül | tervezett |
| 0.9.0 | Disztribúciófüggetlen futásidejű képességréteg | tervezett |
| 0.9.1 | Arch/CachyOS natív csomag (PKGBUILD) | tervezett |
| 0.9.2 | Debian/Ubuntu DEB csomag | tervezett |
| 0.9.3 | Dokumentáció és közzétételi csomag, magyarul és angolul | tervezett |
| 1.0.0 | Végleges, terjeszthető kiadás | tervezett |

Köztes javítóverzió (például 0.5.1) csak valós, külön javítandó hiba esetén készül.

## Meghozott döntések

- **Windows 7:** csak Legacy BIOS (MBR) módban. A hivatalos Windows 7 SP1 ISO-n nincs UEFI-s rendszertöltő (`efi/boot/bootx64.efi`), a telepítőkép módosítása pedig nem cél.
- **Windows 8 és 8.1:** Legacy és UEFI módban is. A támogatás csak a ténylegesen kipróbált változatokra fog vonatkozni.
- **32 bites UEFI:** a 32 bites (IA32) UEFI nem támogatott; az x86 Windows adathordozó csak Legacy BIOS módban támogatott.
- **Disztribúciók az 1.0.0-ban:** Arch/CachyOS és Debian/Ubuntu, natív csomaggal. A projekt egyszerre egy disztribúciócsaládot vesz fel, és csak az előző stabilizálása után bővít.
- **Fedora (RPM):** nem része az 1.0.0-nak; egy hibamentes 1.0.0 után újra mérlegeljük.
- **AppImage:** nincs tervben.
- **Flatpak:** nem cél, mert a program közvetlenül a blokkeszközökkel dolgozik.
- A grafikus felület és a lemezírási logika disztribúciófüggetlen marad; a csomagtelepítés, a függőségek felismerése, az asztali integráció és a polkit-beállítás külön, disztribúciónkénti rétegbe kerül.

## Tudatosan nem része az 1.0.0-nak

- Linux persistence
- Windows To Go
- ISO-letöltés és ISO-katalógus
- Több pendrive párhuzamos írása
- Kombinált BIOS+UEFI Windows-pendrive
- A Windows telepítő testreszabása vagy a WIM/ESD átalakítása
- 32 bites UEFI
- Windows 7 UEFI módban
- Fedora RPM, AppImage, Flatpak
- Minden asztali környezet és disztribúció általános támogatásának ígérete

## Hosszabb távú ötletek

Az 1.0.0 után kerülhetnek sorra; egyik sem vállalás.

- Kombinált BIOS+UEFI Windows-pendrive egyetlen MBR-rel
- Windows To Go és FreeDOS
- Linux persistence
- USB-meghajtók állapot- és kapacitástesztje
- Lemezkép-ellenőrzőösszegek és kiadói aláírás ellenőrzése
- Opcionális ISO-letöltés és ISO-katalógus
- Rugalmasabb formázási lehetőségek

## További dokumentumok

- [CHANGELOG.md](CHANGELOG.md): a kiadások változásai
- [docs/progress.md](docs/progress.md): az aktuális verzió részletes fejlesztési állapota
- [docs/history/](docs/history/): a lezárt verziók fejlesztési naplója
- [CONTRIBUTING.hu.md](CONTRIBUTING.hu.md): közreműködés
