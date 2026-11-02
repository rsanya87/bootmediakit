# BootMediaKit

**BootMediaKit** egy grafikus, nyílt forráskódú Linuxos USB-készítő. A grafikus felület Python és PySide6 alapú; a lemezre írást külön, rendszergazdai jogosultsággal futó háttérfolyamat végzi.

**Fejlesztői verzió:** `0.1.2-alpha`  
**Elsődleges platform:** Arch Linux család (elsőként CachyOS)  
**Az alkalmazás licence:** GNU GPL-3.0-only

> Ez alfa verzió, tesztelésre készült. Nem állítjuk, hogy már teljes Rufus-helyettesítő. Az új Windows UEFI:NTFS eljárás automatikus tesztekkel ellenőrzött, de valódi pendrive-on, UEFI firmware-rel és Windows Telepítővel még tesztelni kell.

## Jelenlegi funkciók

- ISO, IMG, BIN és RAW lemezképek közvetlen kiírása.
- Nyers lemezkép írása után opcionális teljes visszaolvasás.
- Windows telepítő ISO-k felismerése, hogy ne kerüljenek véletlenül nyers kiírásra.
- Windows x64 UEFI telepítő készítése GPT lemezen, két partícióval:
  - egy nagy NTFS Microsoft Basic Data partíció az eredeti Windows ISO fájljainak;
  - egy 1 MiB-os FAT EFI System Partition a pendrive végén, az UEFI:NTFS segédképpel.
- Az eredeti `install.esd`, `install.wim` és a többi Windows telepítőfájl változatlanul kerül át. Nincs ESD→WIM konvertálás és SWM-darabolás.
- A hivatalos UEFI:NTFS segédkép méretének és Git-blob SHA-1 azonosítójának ellenőrzése telepítéskor és használat előtt.
- A segédkép visszaolvasásos ellenőrzése a pendrive-ra írás után.
- A kernel NTFS3 driverét részesíti előnyben, az ntfs-3g tartalék lehetőséggel.
- A fájlok kiírását kötegelt lemezre ürítéssel végzi, nem minden fájl után külön fsync művelettel.
- Opcionális SHA-256 visszaellenőrzés minden átmásolt Windows fájlra. A Windows mód gyorsabb induló beállítása miatt ez alapértelmezésben ki van kapcsolva, de a grafikus felületen bármikor bekapcsolható.
- Grafikus folyamatjelző és napló.
- Rendszergazdai engedélykérés csak a tényleges, romboló lemezművelethez.

## Windows UEFI:NTFS – hogyan működik?

A megoldás az UEFI:NTFS projekt és a Rufus által használt elrendezést követi: a pendrive első, nagy partíciója NTFS, és az eredeti Windows telepítőfájlokat tartalmazza. A második, kisméretű FAT partíció a lemez legvégére kerül.

A gép UEFI firmware-e a FAT partícióról elindítja az UEFI:NTFS betöltőt. Az betölti az NTFS UEFI illesztőprogramot, megkeresi ugyanazon az USB-eszközön az NTFS partíciót, majd elindítja rajta a Windows x64 EFI bootloadert.

Az UEFI:NTFS segédképet telepítéskor az alkalmazás a Rufus hivatalos GitHub-forrásából, rögzített commitból tölti le. A letöltő ellenőrzi a fájl pontos méretét, Git-blob SHA-1 és SHA-256 azonosítóját. Az írás közben ugyanezeket a feltételeket ellenőrzi, majd a segédpartíciót vissza is olvassa.

A Windows ISO fájljai eredeti formában kerülnek az NTFS partícióra. Így a FAT32 4 GiB-os fájlkorlátja nem érvényesül, és az ESD/WIM képfájlt sem kell módosítani. CachyOS-on a program először a Linux kernel NTFS3 driverét használja; ha az nem érhető el vagy nem tudja csatolni a kötetet, az ntfs-3g a kompatibilitási tartalék. A fájlok kiírását egyetlen kötegelt sync követi, nem minden egyes fájl után fsync. A teljes SHA-256 visszaolvasás a teljes adatmennyiséget újra elolvassa, ezért lassabb USB 2.0 pendrive-oknál jelentős időt adhat hozzá; emiatt alapértelmezésben kikapcsolt, de opcionálisan kérhető.

### Secure Boot

A Rufus által közzétett UEFI:NTFS segédkép tartalmaz Secure Boot aláírású x64 UEFI:NTFS összetevőket. Ez **nem jelent minden gépen garantált Secure Boot kompatibilitást**: a firmware tanúsítványtárolója, a Microsoft harmadik féltől származó UEFI CA beállítása és a visszavonási lista eltérhet. Egyes gépeken engedélyezni kell a harmadik féltől származó UEFI tanúsítványokat, más esetben a firmware visszautasíthat egy visszavont aláírást. A BootMediaKit nem kapcsolja ki a Secure Bootot és nem módosít firmware-beállításokat.

### Jelenlegi korlátozások

- Windows telepítő: **UEFI x64**.
- Legacy BIOS/CSM, Windows To Go, FreeDOS, Linux persistence és Windows 11 telepítő testreszabása még nincs.
- A jelenlegi elrendezés 512 bájtos logikai szektorú USB-meghajtót igényel.
- A telepítőszkript egyelőre Arch-alapú rendszereket támogat; Debian/Ubuntu és Fedora későbbi fejlesztési cél.
- A valódi Windows Telepítő teszt még hátravan. A 0.1.1-alpha korábbi FAT32/SWM eljárásával a felhasználó gépén „Hiányzik egy adathordozóhoz szükséges illesztőprogram” hiba jelent meg, miközben ugyanaz az ISO Rufusszal működött. A 0.1.2 UEFI:NTFS eljárása ezt a fájlrendszer- és indítási korlátot célozza, de a hibajegyet csak a felhasználó gépén sikeres telepítőindítás után zárjuk le.
- A fájl-ellenőrzés a másolt fájlok méretét és SHA-256 hashét ellenőrzi. Az ISO eredetiségét vagy kiadói aláírását nem vizsgálja.

## Telepítés Arch-alapú Linuxon

A telepítőnek internetkapcsolat kell, mert a hivatalos Rufus GitHub-forrásból letölti a rögzített UEFI:NTFS segédképet, majd ellenőrzi.

```bash
chmod +x install.sh
./install.sh
```

Indítás az alkalmazásmenüből vagy terminálból:

```bash
bootmediakit
```

Szükséges Arch csomagok:

- `pyside6` — grafikus felület
- `util-linux` — `lsblk`, `blockdev`, `sfdisk`, `wipefs`, `mount` és `umount`
- `parted` — `partprobe`, hogy a kernel újraolvassa a partíciós táblát
- `ntfs-3g` — NTFS csatolás
- `ntfsprogs` — `mkfs.ntfs` formázó (Arch külön csomag)
- `polkit` — jogosultságemelés
- `7zip` — Windows ISO felismerése

KDE alatt aktív polkit hitelesítő ügynök szükséges.

## Automatikus tesztek

```bash
python3 -m py_compile app.py worker.py iso_utils.py fetch_uefi_ntfs.py
bash -n install.sh uninstall.sh
python3 -m unittest discover -s tests -v
```

Az egységtesztek ellenőrzik a célmeghajtó-védelmet, a GPT partícióelrendezést, a partícióneveket, az sfdisk típusokat, az ISO szerkezetét, a fájlmásolási manifestet és az SHA-256 visszaellenőrzést. Ezek nem helyettesítik a valódi USB-s, firmware-es és Windows Telepítő tesztet.

## Fejlesztési irány

Elsőként az Arch/CachyOS változatot stabilizáljuk. Debian/Ubuntu és Fedora csak ezután következik. Részletek: [ROADMAP.md](ROADMAP.md), [CHANGELOG.md](CHANGELOG.md), [CONTRIBUTING.md](CONTRIBUTING.md).

## Biztonság

Az USB teljes tartalma törlődik. Mindig ellenőrizd a meghajtó eszköznevét, típusát és kapacitását. Csak olyan pendrive-ot használj, amelyen nincs megőrzendő adat. A program írás előtt újraellenőrzi a céleszközt és tiltja a rendszerlemezt, de a téves eszközválasztás kockázatát semmilyen program nem tudja teljesen megszüntetni.

## Külső összetevők

Az UEFI:NTFS segédképet a program a Rufus rögzített upstream forrásából tölti le. A segédkép és az abban található külső kódok licence nem változik. Lásd: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
