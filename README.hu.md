# BootMediaKit

**BootMediaKit** egy grafikus, nyílt forráskódú Linuxos USB-készítő. A grafikus felület Python és PySide6 alapú; a lemezre írást külön, root tulajdonú wrapperen és saját Polkit-szabályon át indított, izolált Python worker végzi.

**Verzió:** `0.2.2` (stabil kiadás, 2026-11-10)  
**Elsődleges platform:** Arch Linux család (elsőként CachyOS)  
**Az alkalmazás licence:** GNU GPL-3.0-only

> A 0.2.2 karbantartó kiadás: új funkciót nem ad, és nem változtat sem az írási sorrenden, sem a Windows-mód GPT-elrendezésén. Az automatizált GitHub Actions ellenőrzései sikeresek, beleértve a valódi RAW és Windows írót futtató loop-eszközös integrációs teszteket. A 0.2.2-vel fizikailag újra ellenőrizve: a visszaolvasással kiírt Linux Mint 22.3 DD/RAW pendrive UEFI és Legacy BIOS/MBR módban is elindult, olyan pendrive-on is, amelyen előtte a Windows-mód kétpartíciós GPT-je volt; a Windows 10/11 IoT Enterprise LTSC pendrive a várt partíciónevekkel elkészült és elindult. A teljes Windows 10/11 IoT Enterprise LTSC telepítés, valamint a normál Windows 11 26H2 Telepítő indulása Secure Boot be- és kikapcsolt állapotában (csak a partícióválasztó képernyőig) a 0.2.1-gyel lett ellenőrizve, ezek teljes körűen nem lettek megismételve. Ezek a teszteredmények a kipróbált konfigurációkra vonatkoznak, nem jelentenek minden firmware-re érvényes kompatibilitási garanciát. A BootMediaKit nem teljes Rufus-funkciópótlás.

## Jelenlegi funkciók

- Külön, root tulajdonú worker-wrapper és saját Polkit akció; a GUI nem kap rendszergazdai jogosultságot.
- Biztonságos megszakítási kérés a GUI-ból; a worker írási egységek között áll le, nem kényszerített folyamatkilövéssel.
- A forrás és a cél fizikai meghajtójának ütközésvizsgálata; a cél meghajtóazonosságának ismételt ellenőrzése közvetlenül a törlés előtt.
- A rendszer- és swap-meghajtók védelme, valamint LUKS/LVM/RAID/swap kötetek elutasítása.
- Partíciók és címkék részletes megjelenítése a megerősítés előtt; dupla megerősítés nagy vagy nem-removable USB-meghajtóknál.


- Képernyőmérethez igazodó PySide6 felület: legfeljebb 740×900-as ablak, 1366×768-as laptopon kompakt elrendezés és görgetés nélküli használatra optimalizált méret; a 10 pontos betűméret megmarad.
- Élő elteltidő-kijelzés a pendrive készítésének tényleges futási idejéről.
- Saját BootMediaKit alkalmazásikon az ablakhoz, a tálcához és az alkalmazásmenühöz.
- Jól olvasható meghajtóadatok sötét KDE témán; a partíciók teljes listája a kis `i` információs ikon fölé húzott egérmutatóval jelenik meg.

- ISO, IMG, BIN és RAW lemezképek közvetlen kiírása.
- Nyers lemezkép írása után opcionális teljes visszaolvasás.
- Windows telepítő ISO-k felismerése, hogy ne kerüljenek véletlenül nyers kiírásra.
- Windows x64 UEFI telepítő készítése GPT lemezen, két partícióval:
  - egy nagy NTFS Microsoft Basic Data partíció az eredeti Windows ISO fájljainak;
  - egy 1 MiB-os FAT `BMK_EFI` UEFI:NTFS segédpartíció a pendrive végén. A GPT-típusa Microsoft Basic Data (nem EFI System), be van állítva a NoDriveLetter (GUID-specifikus 63-as) attribútum, és a GPT partíciónév, valamint a FAT kötetcímke is `BMK_EFI`.
- Windows telepítő pendrive **Legacy BIOS/CSM** indításhoz, az „Indítási mód” választóval: MBR lemez egyetlen aktív NTFS partícióval az eredeti Windows ISO fájljainak, és GNU GRUB i386-pc indító, amely az ISO saját Windows `bootmgr`-ét indítja. Lásd: [Windows Legacy BIOS/MBR – hogyan működik?](#windows-legacy-biosmbr--hogyan-működik).
- Az eredeti `install.esd`, `install.wim` és a többi Windows telepítőfájl változatlanul kerül át. Nincs ESD→WIM konvertálás és SWM-darabolás.
- A hivatalos UEFI:NTFS segédkép méretének és Git-blob SHA-1 azonosítójának ellenőrzése telepítéskor és használat előtt.
- A Windows telepítő nagy NTFS partíciója megőrzi az ISO eredeti kötetcímkéjét; a `BMK_EFI` név kizárólag a kis segédpartícióhoz tartozik.
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

A kiadás fizikai tesztje során a normál Windows 11 26H2 x64 telepítő Secure Boot kikapcsolt és bekapcsolt állapotában is eljutott a Windows Telepítő partícióválasztó képernyőjéig. A telepítés ezen túl nem folytatódott. Ez kizárólag a tesztelt firmware-en megfigyelt eredmény; más alaplapok és UEFI firmware-ek eltérően viselkedhetnek.

## Windows Legacy BIOS/MBR – hogyan működik?

UEFI nélküli, vagy CSM (legacy) módban használt UEFI-s géphez válaszd a Windows módot, és az **Indítási mód** legyen **Legacy BIOS (MBR)**. A választó csak felismert Windows telepítő ISO-nál aktív; az alapérték továbbra is az UEFI (GPT).

A BootMediaKit ekkor MBR partíciós táblát készít egyetlen aktív NTFS partícióval (típus: `7`), amely 1 MiB-tól a pendrive végéig tart. Erre másolja az eredeti Windows ISO fájljait, majd lefuttatja a gépre telepített `grub` csomag `grub-install` programját. A BIOS az MBR-ből a GRUB indítókódját tölti be, a partíció előtti résből a GRUB magját, az NTFS partíció `/grub` könyvtárából pedig a modulokat és a `grub.cfg`-t. A `grub.cfg` az `ntldr /bootmgr` paranccsal elindítja a Windows rendszerindító-kezelőjét, onnan a Windows Telepítő a megszokott módon folytatódik. Az SHA-256 ellenőrzés csak az ISO fájljaira vonatkozik; a `/grub` könyvtár utána kerül fel.

- **Nincs beépített indítókód.** A BootMediaKit ehhez a módhoz nem tartalmaz és nem tölt le indítókódot, és más projektből sem másol Microsoft MBR- vagy boot-szektor-kódot. Az indítókódot a gép saját `grub-install` programja írja ki.
- **A gép rendszere érintetlen marad.** A `grub-install` csak `--target=i386-pc` kapcsolóval fut, a `--boot-directory` a pendrive saját NTFS csatolási pontjára mutat, utolsó argumentuma pedig az újraellenőrzött USB-eszköz. A BootMediaKit soha nem futtat EFI-s `grub-install`-t, `grub-mkconfig`-ot vagy `efibootmgr`-t, és indítókönyvtárként elutasítja a gép gyökérkönyvtárát, valamint a `/boot`, az `/efi` és az alattuk lévő könyvtárakat; indítókönyvtár csak a pendrive NTFS partíciójának csatolási pontja lehet.
- **Csak Legacy módban indul.** A pendrive csak Legacy BIOS/CSM módban indul, UEFI módban **nem**. UEFI-s géphez az UEFI (GPT) indítási módot használd. A megerősítő ablak is figyelmeztet erre.
- **Régebbi gépekhez.** A mód régebbi gépekhez készült. Az újabb Windows telepítők ellenőrzik a hardverkövetelményeket, és régi gépen megtagadhatják a telepítést; ez a Windows Telepítő döntése, nem a pendrive hibája.
- Feltételek és elutasítások: 2 TiB-os vagy nagyobb meghajtót nem fogad el (az MBR korlátja); 512 bájtos logikai szektor kell, mint az UEFI módban; Windows XP / Server 2003 jellegű ISO (`i386` könyvtár `bootmgr` nélkül) nem támogatott; ha az ISO gyökerében már van `grub` nevű elem, a program megáll, nem írja felül. `grub-install` és `/usr/lib/grub/i386-pc` nélkül a Legacy érték a felületen tiltott.
- Tesztelés: az automatikus tesztek a termelési íróval loop-eszközre írják a pendrive-ot, és QEMU/SeaBIOS alatt egy teszt-`bootmgr`-ig indítják. A valódi Windows ISO-kkal és gépeken végzett fizikai teszteket a [ROADMAP.md](ROADMAP.md) követi.

### Jelenlegi korlátozások

- Windows telepítő: **UEFI x64 (GPT)** vagy **Legacy BIOS/CSM (MBR)**, pendrive-onként egy mód; kombinált BIOS+UEFI Windows pendrive még nincs. A Linux ISOHybrid/DD mód az ISO saját bootképessége szerint Legacy BIOS és UEFI rendszeren is használható.
- Windows To Go, FreeDOS, Linux persistence és Windows 11 telepítő testreszabása még nincs.
- A jelenlegi elrendezés 512 bájtos logikai szektorú USB-meghajtót igényel.
- A telepítőszkript egyelőre Arch-alapú rendszereket támogat; Debian/Ubuntu és Fedora későbbi fejlesztési cél.
- A Windows 10 és Windows 11 IoT Enterprise LTSC x64 UEFI telepítése a tesztelt rendszeren sikeresen befejeződött. A normál Windows 11 26H2 x64 ISO Secure Boot be- és kikapcsolt állapotában is eljutott a partícióválasztó képernyőig; a telepítés további része nem lett igazolva.
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
- `grub` — a `grub-install` és az i386-pc modulok a Windows Legacy BIOS módhoz. A BootMediaKit csak ezeket használja, és a `grub-install`-t kizárólag a kiválasztott pendrive-ra futtatja. A csomag telepítése **nem** módosítja a gép saját rendszerbetöltőjét. A csomag telepítés utáni üzenete a `grub-install` és a `grub-mkconfig` futtatását javasolja; ez a gép saját rendszerbetöltőjére vonatkozik, a BootMediaKit-hez nem kell.

KDE alatt aktív polkit hitelesítő ügynök szükséges.

## Automatikus tesztek

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py version.py
bash -n install.sh uninstall.sh bootmediakit-worker
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

A GUI-tesztekhez (`tests/test_app.py`) `PySide6` kell; a CI ezen felül a `shellcheck -S warning install.sh uninstall.sh bootmediakit-worker` parancsot is futtatja.

Az egységtesztek ellenőrzik a célmeghajtó-védelmet, a forrás/cél ütközésvizsgálatot, a GPT partícióelrendezést, a partícióneveket, az sfdisk típusokat, az ISO szerkezetét, a fájlmásolási manifestet, az SHA-256 visszaellenőrzést, a megszakítást és a csomagolást. Az opcionális loop-eszközös integrációs tesztek a valódi RAW, Windows UEFI és Windows Legacy BIOS írót futtatják rootként egy lemezképfájlon; `BMK_QEMU=1` mellett a Legacy BIOS pendrive-képet QEMU/SeaBIOS alatt el is indítják:

```bash
sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

`BMK_INTEGRATION=1`, root jog és a szükséges programok nélkül ezek kimaradnak; részletek: [docs/TESTING.md](docs/TESTING.md). Egyik szint sem helyettesíti a valódi USB-s, firmware-es és Windows Telepítő tesztet.

## Fejlesztési irány

Elsőként az Arch/CachyOS változatot stabilizáljuk. Debian/Ubuntu és Fedora csak ezután következik. Részletek: [ROADMAP.md](ROADMAP.md), [CHANGELOG.md](CHANGELOG.md), [CONTRIBUTING.md](CONTRIBUTING.md).

## Windows Telepítő több belső meghajtó esetén

Ha a `setupact.log` naplóban `GetMachineInfo: Couldn't find info for boot disk`, `CanBeSystemVolume` vagy „The selected disk is not the computer's boot disk” jelenik meg, előfordulhat, hogy a Windows PE több belső HDD/SSD mellett rosszul azonosítja a boot-/rendszerlemezt. Ez nem feltétlenül a telepítő pendrive hibája. A `Shift+F10` után futtasd a `diskpart`, majd `list disk` parancsot, és a kapacitás alapján azonosítsd a céllemezt. Diagnosztikai próbához ideiglenesen válaszd le a nem célként használt belső meghajtókat, és csak a cél SSD maradjon csatlakoztatva a telepítő USB mellett. **Ne futtass `clean` parancsot a másodlagos lemezen.** UEFI-s Windows telepítéshez a céllemeznek GPT partíciós táblát kell használnia. [Microsoft UEFI/GPT útmutató](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/configure-uefigpt-based-hard-drive-partitions?view=windows-11).

## Biztonság

Az USB teljes tartalma törlődik. Mindig ellenőrizd a meghajtó eszköznevét, típusát és kapacitását. Csak olyan pendrive-ot használj, amelyen nincs megőrzendő adat. A program írás előtt újraellenőrzi a céleszközt és tiltja a rendszerlemezt, de a téves eszközválasztás kockázatát semmilyen program nem tudja teljesen megszüntetni.

Ha a grafikus felület írás közben bezárul vagy megszakad a kapcsolata a workerrel, a worker a következő írási határon biztonságosan leáll, de a pendrive részlegesen írt állapotban maradhat. Ilyenkor az eszközt használat előtt újra kell írni.

## Külső összetevők

A BootMediaKit nem tartalmaz átmásolt Rufus alkalmazás-forráskódot. Telepítéskor a hivatalos Rufus tárolóból külön licencű UEFI:NTFS segédképet tölt le; ez harmadik féltől származó UEFI bootloader- és fájlrendszer-driver binárisokat tartalmaz. A forrásokra, szerzői jogokra és licencekre vonatkozó részletek: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
