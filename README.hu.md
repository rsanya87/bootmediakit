# BootMediaKit

**BootMediaKit** egy grafikus, nyílt forráskódú Linuxos USB-készítő. A grafikus felület Python és PySide6 alapú; a lemezre írást külön, root tulajdonú wrapperen és saját Polkit-szabályon át indított, izolált Python worker végzi.

**Fejlesztői verzió:** `0.1.3-safety-alpha`  
**Elsődleges platform:** Arch Linux család (elsőként CachyOS)  
**Az alkalmazás licence:** GNU GPL-3.0-only

> A 0.1.2-es verziót valódi USB 2.0 pendrive-okon is teszteltük. A Samsung RV511 gépen a Windows Telepítő eljutott az első újraindításig, majd a belső SSD-ről folytatta a telepítést. A Linux RAW/DD írás Legacy/MBR módban szintén tesztelve van. További UEFI firmware-, Secure Boot-, Windows ISO- és eszköztesztek még szükségesek; a program nem teljes Rufus-funkciópótlás.

## Jelenlegi funkciók

- Külön, root tulajdonú worker-wrapper és saját Polkit akció; a GUI nem kap rendszergazdai jogosultságot.
- Biztonságos megszakítási kérés a GUI-ból; a worker írási egységek között áll le, nem kényszerített folyamatkilövéssel.
- A forrás és a cél fizikai meghajtójának ütközésvizsgálata; a cél meghajtóazonosságának ismételt ellenőrzése közvetlenül a törlés előtt.
- A rendszer- és swap-meghajtók védelme, valamint LUKS/LVM/RAID/swap kötetek elutasítása.
- Partíciók és címkék részletes megjelenítése a megerősítés előtt; dupla megerősítés nagy vagy nem-removable USB-meghajtóknál.


- Kompakt, átméretezhető PySide6 felület kisebb alapablakkal, a betűméret csökkentése nélkül; hosszú ISO-nevek tördelése vízszintes görgetés nélkül.
- Élő elteltidő-kijelzés a pendrive készítésének tényleges futási idejéről.
- Saját BootMediaKit alkalmazásikon az ablakhoz, a tálcához és az alkalmazásmenühöz.
- Jól olvasható meghajtó- és partícióadatok sötét KDE témán; a fejlesztői verziószám közvetlenül a név alatt jelenik meg.

- ISO, IMG, BIN és RAW lemezképek közvetlen kiírása.
- Nyers lemezkép írása után opcionális teljes visszaolvasás.
- Windows telepítő ISO-k felismerése, hogy ne kerüljenek véletlenül nyers kiírásra.
- Windows x64 UEFI telepítő készítése GPT lemezen, két partícióval:
  - egy nagy NTFS Microsoft Basic Data partíció az eredeti Windows ISO fájljainak;
  - egy 1 MiB-os FAT `BMK_EFI` UEFI:NTFS segédpartíció a pendrive végén. A GPT-típusa Microsoft Basic Data (nem EFI System), be van állítva a NoDriveLetter (GUID-specifikus 63-as) attribútum, és a GPT partíciónév, valamint a FAT kötetcímke is `BMK_EFI`.
- Az eredeti `install.esd`, `install.wim` és a többi Windows telepítőfájl változatlanul kerül át. Nincs ESD→WIM konvertálás és SWM-darabolás.
- A hivatalos UEFI:NTFS segédkép méretének és Git-blob SHA-1 azonosítójának ellenőrzése telepítéskor és használat előtt.
- A segédkép visszaolvasásos ellenőrzése a pendrive-ra írás után.
- A kernel NTFS3 driverét részesíti előnyben, az ntfs-3g tartalék lehetőséggel.
- Kikapcsolt SHA-256 visszaellenőrzésnél megpróbálja a kernel `copy_file_range`, majd `sendfile` fájlmásolását használni; ha az ISO9660 és NTFS3 közötti mindkét gyors másolási mód nem támogatott, automatikusan visszaáll a streamelt másolásra.
- Ritkítja a grafikus folyamatfrissítéseket, és csak az USB fájlrendszerét üríti ki, nem a gép összes meghajtóját.
- A fájlok kiírását kötegelt lemezre ürítéssel végzi, nem minden fájl után külön fsync művelettel.
- Opcionális SHA-256 visszaellenőrzés minden átmásolt Windows fájlra. A Windows mód gyorsabb induló beállítása miatt ez alapértelmezésben ki van kapcsolva, de a grafikus felületen bármikor bekapcsolható.
- Grafikus folyamatjelző és napló.
- Rendszergazdai engedélykérés csak a tényleges, romboló lemezművelethez.

## Windows UEFI:NTFS – hogyan működik?

A megoldás az UEFI:NTFS projekt és a Rufus által használt elrendezést követi: a pendrive első, nagy partíciója NTFS, és az eredeti Windows telepítőfájlokat tartalmazza. A második, kisméretű FAT segédpartíció a lemez legvégére kerül. GPT esetén ezt a Rufus Microsoft Basic Data típusúnak jelöli és beállítja a NoDriveLetter attribútumot ahelyett, hogy második EFI System Partitionként deklarálná. Ez fontos: a Windows Setup hibázhat, ha ugyanazon a gépen két ESP-t talál.

A gép UEFI firmware-e a FAT partícióról elindítja az UEFI:NTFS betöltőt. Az betölti az NTFS UEFI illesztőprogramot, megkeresi ugyanazon az USB-eszközön az NTFS partíciót, majd elindítja rajta a Windows x64 EFI bootloadert.

A tiszta UEFI:NTFS segédképet a telepítő a Rufus hivatalos GitHub-forrásából, rögzített commitból tölti le, majd ellenőrzi a pontos méretét, Git-blob SHA-1 és SHA-256 azonosítóját. USB-készítéskor a program egy ideiglenes másolat FAT kötetcímkéjét `RUFUS_BOOT` értékről `BMK_EFI` értékre állítja a `fatlabel` eszközzel. A hitelesített upstream képfájl változatlan marad, az aláírt EFI binárisokhoz nem nyúlunk. Az elkészült ideiglenes képet SHA-256 alapján visszaellenőrzi a pendrive-ról, és külön ellenőrzi a `BMK_EFI` kötetcímkét is.

A Windows ISO fájljai eredeti formában kerülnek az NTFS partícióra. Így a FAT32 4 GiB-os fájlkorlátja nem érvényesül, és az ESD/WIM képfájlt sem kell módosítani. CachyOS-on a program először a Linux kernel NTFS3 driverét használja; ha az nem érhető el vagy nem tudja csatolni a kötetet, az ntfs-3g a kompatibilitási tartalék. A fájlok kiírása után csak a cél USB fájlrendszerét szinkronizálja. Kikapcsolt SHA-256 módban először kernel-assisted `copy_file_range`, majd szükség esetén `sendfile` másolást próbál használni. Csak akkor vált a biztonságos streamelt másolásra, ha egyik gyors útvonal sem támogatott. A teljes SHA-256 visszaolvasás a teljes adatmennyiséget újra elolvassa, ezért lassabb USB 2.0 pendrive-oknál jelentős időt adhat hozzá; emiatt alapértelmezésben kikapcsolt, de opcionálisan kérhető.

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
- `dosfstools` — `fatlabel` a BMK_EFI FAT kötetcímkéjének beállításához és ellenőrzéséhez
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

## Windows Telepítő több belső meghajtó esetén

Ha a `setupact.log` naplóban `GetMachineInfo: Couldn't find info for boot disk`, `CanBeSystemVolume` vagy „The selected disk is not the computer's boot disk” jelenik meg, előfordulhat, hogy a Windows PE több belső HDD/SSD mellett rosszul azonosítja a boot-/rendszerlemezt. Ez nem feltétlenül a telepítő pendrive hibája. A `Shift+F10` után futtasd a `diskpart`, majd `list disk` parancsot, és a kapacitás alapján azonosítsd a céllemezt. Diagnosztikai próbához ideiglenesen válaszd le a nem célként használt belső meghajtókat, és csak a cél SSD maradjon csatlakoztatva a telepítő USB mellett. **Ne futtass `clean` parancsot a másodlagos lemezen.** UEFI-s Windows telepítéshez a céllemeznek GPT partíciós táblát kell használnia. [Microsoft UEFI/GPT útmutató](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/configure-uefigpt-based-hard-drive-partitions?view=windows-11).

## Biztonság

Az USB teljes tartalma törlődik. Mindig ellenőrizd a meghajtó eszköznevét, típusát és kapacitását. Csak olyan pendrive-ot használj, amelyen nincs megőrzendő adat. A program írás előtt újraellenőrzi a céleszközt és tiltja a rendszerlemezt, de a téves eszközválasztás kockázatát semmilyen program nem tudja teljesen megszüntetni.

## Külső összetevők

A BootMediaKit nem tartalmaz átmásolt Rufus alkalmazás-forráskódot. Telepítéskor a hivatalos Rufus tárolóból külön licencű UEFI:NTFS segédképet tölt le; ez harmadik féltől származó UEFI bootloader- és fájlrendszer-driver binárisokat tartalmaz. A forrásokra, szerzői jogokra és licencekre vonatkozó részletek: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
