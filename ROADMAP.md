# Roadmap

A feladat akkor tekinthető késznek, ha az automatizált ellenőrzések és a hozzájuk tartozó valós eszközös tesztek eredménye is rögzítve van.

## 0.3.0 — Fejlesztés alatt: Windows Legacy BIOS/MBR telepítő-pendrive

> **Ez a szakasz egyben végrehajtható munkaleírás.** Aki (ember vagy asszisztens) ezt kapja feladatként, a fizikai, éles USB-teszteken és a root jogot igénylő futtatásokon kívül mindent el tud végezni belőle. A fizikai teszteket kizárólag a projekt gazdája végzi, lásd a „Fizikai tesztek" szakaszt. Az asszisztens ezeket nem állíthatja késznek.

### Állapot

- [x] T0. Megvalósíthatósági kapu: GRUB i386-pc láncbetöltés loop-eszközön, QEMU/SeaBIOS-ban `BMK-BOOT-OK` (CI és a gazda gépe).
- [x] T1. Windows ISO vizsgálata Legacy módhoz (`scan_windows_iso(boot_mode="bios")`).
- [x] T2. MBR-elrendezés és `verify_mbr_layout`.
- [x] T3. GRUB láncbetöltő telepítése (`install_bios_chainloader`, `grub_install_args`).
- [x] T4. Az új író: `write_windows_bios`.
- [x] T5. Worker belépési pont: `windows-bios` mód.
- [x] T6. Grafikus felület: „Indítási mód” választó.
- [x] T7. Integrációs teszt a termelési íróval, QEMU-s indítási próbával (CI és a gazda gépe: 10/10).
- [x] T8. Telepítő és függőségek (`grub`), README-k.
- [x] T9. Dokumentáció.
- [ ] T10. Kiadási commit (a gazda visszajelzése után).

### Jóváhagyott és dokumentált eltérések a munkaleírástól

- **T0/T3 `grub.cfg`:** a négy soros minta helyett `insmod ntldr` és `insmod boot` is szerepel. A CI GRUB 2.14-2ubuntu2.1 nem tölti be automatikusan a parancsmodulokat (`can't find command`); a GRUB 2.16-on (Arch) a két sor ártalmatlan. A gazda jóváhagyta.
- **CI környezeti változók:** a `sudo -E` helyett `sudo env BMK_…`, mert az ubuntu-26.04 runner `sudo`-ja elhagyta a lépés `env:` változóit. Egy külön CI-lépés ellenőrzi, hogy a root folyamat megkapja őket.
- **T2 határ:** a pontosan 2 TiB-os (2**32 szektoros) meghajtót is elutasítjuk, mert az `sfdisk` ott csak figyelmeztet, és csendben levágná a partíciót.
- **T3 tiltott könyvtárak:** a „`/`, `/boot` vagy `/efi` alatt” szabály így valósult meg: maga a `/`, valamint a `/boot`, az `/efi` és minden alattuk lévő könyvtár tiltott; ezen felül `findmnt` ellenőrzi, hogy az indítókönyvtár a cél NTFS partíciójának saját csatolási pontja.
- **T6:** a Windows mód gombjának felirata „Windows telepítő (NTFS)” lett, mert mindkét indítási módot lefedi. A Windows-módleírások két sorra rövidültek és felülre igazodnak, mert 560 px szélességben (a 0.2.2-ben is) túlcsordultak.
- **T7:** a T0 teszteket nem alakítottuk át, hanem megtartottuk írótól független referenciaként (meglévő tesztet nem törlünk); a termelési írót az új `LoopWindowsBiosWriterTests` hívja, a QEMU-kód közös. `BMK_INTEGRATION_REQUIRED=1` és `BMK_QEMU=1` mellett a hiányzó QEMU hiba, nem kihagyás (a T0 QEMU-tesztekre is). A CI munkafolyamata nem változott, mert a csomagok és a `BMK_QEMU=1` a T0 óta benne vannak.
- **CI-stabilitás (külön `ci:` commit):** a csomagtelepítés háromszor próbálkozik, utána hibával áll le; a job 30, a telepítési lépés 20 perces időkorlátot kapott. Ok: a runner átmenetileg nem érte el a `security.ubuntu.com`-ot.
- **`install.sh`:** a repóban futtathatóként (100755) tárolva; a README `chmod +x` lépése ártalmatlan maradt.

### Cél

A BootMediaKit Windows-módja ma csak UEFI-ről indítható pendrive-ot készít (GPT, NTFS + `BMK_EFI`). A 0.3.0 új, választható módot ad: **Windows telepítő Legacy BIOS/MBR indításhoz**, hogy a pendrive UEFI nélküli vagy CSM-módban használt gépen is elinduljon.

**Nem cél:** kombinált BIOS+UEFI pendrive egyetlen MBR-rel, Windows XP/2003 ISO, 32 bites UEFI, Linux persistence, ISO-letöltés, több pendrive egyidejű írása, új disztribúció támogatása. A meglévő RAW és Windows UEFI mód viselkedése nem változik.

### Választott megoldás és az oka

**MBR + egyetlen aktív NTFS partíció + GNU GRUB (i386-pc) láncbetöltő, amely a Windows `bootmgr`-t indítja.**

- A BIOS az MBR-ből a GRUB `boot.img`-et indítja, az a partíció előtti résbe ágyazott `core.img`-et, ez beolvassa az NTFS-ről a `/grub` könyvtárat és a `grub.cfg`-t, amely az `ntldr /bootmgr` paranccsal átadja a vezérlést a Windows indítókezelőjének. Ugyanezt az utat használja a WoeUSB.
- **Licenc:** a boot-kódot a felhasználó gépére telepített GRUB csomag `grub-install` programja írja ki. A BootMediaKit nem tartalmaz és nem terjeszt Microsoft boot-kódot (MBR, NTFS PBR), és nem másol ilyet más projektből (ms-sys, Rufus). Ezzel a korábbi „boot-kód licencének tisztázása" kérdés lezárható.
- **Ár:** új futási függőség (`grub` csomag az i386-pc modulokkal), és a pendrive-ra a Windows fájljai mellé egy `/grub` könyvtár kerül.

Ha a T0 kísérlet szerint ez az út nem működik, **a munka megáll, és a gazda dönt**. Az asszisztens önállóan nem válthat más megoldásra (ms-sys, syslinux, beágyazott bináris boot-szektor).

### Szabályok (invariánsok): ezeket nem szabad megsérteni

A 0.2.2 szabályai változatlanul érvényesek:

1. **A RAW-írás sorrendje és a `wipefs --all --force` kötelező volta nem változik.**
2. **Megszakításkor nincs `fsync`**, a megszakítás kooperatív (`cancel` sor a worker `stdin`-jén), 130-as kilépési kóddal.
3. **A Windows UEFI mód elrendezése nem változik:** GPT, 1. partíció NTFS az ISO kötetcímkéjével, 2. partíció 1 MiB-os FAT `BMK_EFI`, Microsoft Basic Data típus, `GUID:63`. A `write_windows_uefi` viselkedése bájtra ugyanaz marad; a meglévő egység- és integrációs tesztjei változtatás nélkül zöldek.
4. **A GUI sosem fut rootként.** A polkit-akciót és a `bootmediakit-worker` wrappert nem módosítjuk.
5. **Minden felhasználónak szánt szöveg magyar**, konkrét hibaüzenettel: mi történt és mit tegyen a felhasználó.
6. **Fail-closed:** ha egy biztonsági ellenőrzés nem tud dönteni, a művelet megáll.
7. **Verziószámot csak a kiadási commit emelhet** (T10). Fejlesztés közben a `version.py` `0.2.2` marad.

Új szabályok a 0.3.0-hoz:

8. **A `grub-install` csak a validált céleszközre futhat.** Közvetlenül előtte újra le kell futnia a céleszköz azonosság-ellenőrzésének. A hívás mindig tartalmazza: `--target=i386-pc`, explicit `--boot-directory=<a cél NTFS csatolási pontja>`, és utolsó argumentumként pontosan a validált eszközútvonalat. Ha bármelyik hiányzik vagy üres, a hívás nem történhet meg. EFI-célú `grub-install` hívás, `efibootmgr`, és a gazdagép saját `/boot` vagy ESP könyvtárára mutató `--boot-directory` tilos.
9. **A BootMediaKit nem tartalmaz bináris boot-kódot** a Legacy módhoz, és futás közben sem tölt le ilyet.
10. **A `worker.py` marad `-I` módú**, új Python-függőség nélkül (csak a szabványos könyvtár).
11. **A loop-eszközt USB-nek mutató helyettesítés csak a `tests/integration/loop_helpers.py`-ban élhet**, a termelési kódban nem.

### Munkamenet

- Ág: `dev/0.3.0` a `main`-ből. A `main` védett: közvetlenül nem írható, csak pull requesten át, zöld CI-vel. A merge és a tag a gazda dolga.
- Feladatonként egy kis commit, `feat:`, `fix:`, `test:`, `ci:`, `docs:` előtaggal. Az új viselkedéshez regressziós teszt tartozik ugyanabban a commitban.
- Minden commit előtt:
  ```bash
  python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py version.py
  bash -n install.sh uninstall.sh bootmediakit-worker
  shellcheck -S warning install.sh uninstall.sh bootmediakit-worker
  QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
  ```
  Induláskor 129 egységteszt van. Egyetlen meglévő tesztet sem lehet törölni vagy gyengíteni; ha egy teszt a változtatás miatt elavul, az indoklás a commit üzenetbe kerül.
- **Root jogot igénylő futtatás** (integrációs tesztek, `./install.sh`): az asszisztens nem futtat `sudo`-t. Ezeket a gazda futtatja külön terminálban, vagy a CI futtatja a feltöltött ágon. Az asszisztens kiírja a pontos parancsot, és megvárja az eredményt.
- A `CHANGELOG.md` tetején fejlesztés közben `## Unreleased` szakasz áll, minden feladat hozzáad egy sort.
- Az asszisztens fizikai lemezre (`/dev/sd*`, `/dev/nvme*`, `/dev/mmcblk*`) semmilyen parancsot nem ad ki.

---

### T0. Megvalósíthatósági kapu: GRUB láncbetöltés loop-eszközön és QEMU-ban

Ez a feladat dönti el, hogy a választott megoldás működik-e. **Amíg ez nem zöld, a T2–T6 nem kezdhető el.**

**Hol:** új `tests/integration/test_loop_windows_bios.py`, a `tests/integration/loop_helpers.py` bővítése.

**Elvárás:** egy önálló integrációs teszt (még a termelési író nélkül, a lépéseket a teszt maga hajtja végre), ugyanazokkal a skip-feltételekkel, mint a meglévők (`BMK_INTEGRATION=1`, root, szükséges programok; ezekhez jön a `grub-install` és az i386-pc modulkönyvtár megléte):

1. 256 MiB-os lemezkép, `losetup --partscan`.
2. `sfdisk`: `label: dos`, egy partíció 1 MiB-tól a lemez végéig, típus `7`, aktív.
3. `mkfs.ntfs` ugyanazokkal a geometria-argumentumokkal, amelyeket a meglévő Windows-író használ (nézd meg a kódban; a rejtett szektorok száma a partíció kezdete legyen).
4. Csatolás (kernel `ntfs3`, tartalék `ntfs-3g`), a gyökérbe egy **teszt `bootmgr`** fájl kerül: néhány bájtnyi valós módú gépi kód, amely a QEMU hibakereső portjára (`0xE9`) kiírja a `BMK-BOOT-OK` szöveget, majd megáll (`hlt` ciklus). A bájtsort a teszt állítja elő, kommentben az assembly megfelelőjével.
5. `grub-install --target=i386-pc --boot-directory=<csatolási pont> <loop eszköz>`, majd a `<csatolási pont>/grub/grub.cfg` megírása:
   ```
   insmod part_msdos
   insmod ntfs
   ntldr /bootmgr
   boot
   ```
6. Leválasztás, `sync`.
7. **Indítási próba QEMU-ban**, ha `BMK_QEMU=1` és van `qemu-system-x86_64` vagy `qemu-system-i386`: a lemezképfájl indítása SeaBIOS-szal, `-display none -no-reboot -debugcon file:<kimenet>`, KVM nélkül is (`-accel tcg`), legfeljebb 60 másodperc időkorláttal. A teszt akkor sikeres, ha a kimeneti fájlban megjelenik a `BMK-BOOT-OK`. QEMU nélkül ez a rész `SkipTest`, a többi ellenőrzés lefut.
8. Statikus ellenőrzések QEMU nélkül is: az MBR végén `55 AA`; a partíciós tábla a `grub-install` előtt és után azonos (`sfdisk --dump` összehasonlítás); az MBR első 440 bájtja nem csupa nulla; az 1. szektortól a partíció kezdetéig tartó résben van nem nulla adat (`core.img`); létezik a `grub/grub.cfg` és a `grub/i386-pc/` könyvtár az `ntfs.mod` és `ntldr.mod` fájlokkal.

**Ellenőrizendő feltevések (a kódírás előtt nézz utána a telepített GRUB dokumentációjában, ne emlékezetből dolgozz):** a `--boot-directory=<X>` Archon `<X>/grub` könyvtárat hoz létre; az `ntldr` parancs a fájlt valós módban indítja; a `grub-install` loop-eszközön `--force` nélkül is beágyazza a `core.img`-et az 1 MiB-os résbe; `ntfs-3g` (fuseblk) csatolásnál is felismeri a fájlrendszert.

**Elfogadás:** a teszt a gazda gépén (`sudo`-val) és a CI-ben zöld, a QEMU-s rész legalább az egyik helyen ténylegesen lefut és zöld. **Ha a `BMK-BOOT-OK` nem jelenik meg, vagy a `grub-install` csak `--force`-szal vagy blocklistával működik: állj meg, írd le pontosan a tapasztalatot, és kérd a gazda döntését.**

### T1. Windows ISO vizsgálata Legacy módhoz

**Hol:** `worker.py` (`scan_windows_iso` és környéke), `iso_utils.py`, `tests/test_worker.py`.

**Most:** a vizsgálat az UEFI-módhoz szükséges fájlokat várja el.

**Elvárás:**
1. A vizsgálat kapjon indítási módot (például `boot_mode="uefi" | "bios"`); az alapérték `uefi`, így a meglévő hívások és tesztek változatlanok.
2. `bios` módban kötelező: `bootmgr` a gyökérben, `boot/bcd`, `sources/boot.wim`, és `sources/install.wim` vagy `.esd` vagy `.swm`. Az EFI-fájlok hiánya ebben a módban nem hiba (32 bites és régebbi ISO-k).
3. A kis- és nagybetű-érzéketlen keresés ugyanúgy működjön, mint most.
4. Ha van `i386/` könyvtár, de nincs `bootmgr` (Windows XP/2003 jellegű ISO), külön, érthető üzenet: ez a típus nem támogatott.
5. A szimbolikus linkek és nem szabályos fájlok elutasítása változatlan.
6. Ha az ISO gyökerében már létezik `grub` nevű fájl vagy könyvtár, a Legacy mód álljon meg érthető üzenettel (nem írunk felül ISO-tartalmat).

**Elfogadás:** új tesztek mindegyik esetre; a meglévő `WindowsIsoScanTests` változtatás nélkül zöld.

### T2. MBR-elrendezés

**Hol:** `worker.py`, `tests/test_worker.py`.

**Elvárás:**
1. Új függvény az MBR-elrendezés kiszámítására és az `sfdisk` szkript előállítására: `label: dos`, egy partíció, kezdete 2048. szektor (1 MiB, 512 bájtos logikai szektornál), típus `7` (NTFS/HPFS), `bootable`, mérete a lemez végéig, 1 MiB-ra igazítva.
2. **2 TiB-nál nagyobb céleszköz elutasítása** érthető üzenettel (az MBR korlátja). Nem 512 bájtos logikai szektorméretű eszköz elutasítása, ha a meglévő kód ezt a Windows-módban is így kezeli; kövesd a meglévő viselkedést.
3. A minimális méret ellenőrzése ugyanazzal a tartalékkal, mint az UEFI-módban.
4. Új `verify_mbr_layout()`: `sfdisk --json` alapján ellenőrzi a címkét (`dos`), az egyetlen partíciót, a típust, az aktív jelzőt, a kezdetet és a méretet. Eltérésnél a művelet megáll.

**Elfogadás:** egységtesztek a számításra, a 2 TiB-os határra, a túl kicsi lemezre; teszt valódi `sfdisk`-kel ritka (sparse) képfájlon, a meglévő `test_sfdisk_accepts_generated_gpt_script_on_sparse_image` mintájára.

### T3. GRUB láncbetöltő telepítése

**Hol:** `worker.py`, `tests/test_worker.py`.

**Elvárás:**
1. Új függvény (például `install_bios_chainloader(device, ntfs_mount, expected_identity)`), amely:
   - újra ellenőrzi a céleszköz azonosságát (8. szabály);
   - ellenőrzi, hogy létezik a `grub-install` és az i386-pc modulkönyvtár (`/usr/lib/grub/i386-pc`), különben érthető hiba a telepítendő csomag nevével;
   - lefuttatja a `grub-install`-t a T0-ban igazolt argumentumokkal, időkorláttal, a meglévő `command()` segédfüggvényen át;
   - megírja a `grub/grub.cfg`-t a T0 szerinti tartalommal, `fsync`-kel;
   - ellenőrzi az eredményt: a partíciós tábla változatlan (`verify_mbr_layout`), az MBR aláírása megvan, az első 440 bájt nem nulla, a `grub/i386-pc/ntfs.mod` és `ntldr.mod` létezik.
2. A `grub-install` hívás előtt és után `check_cancelled()`. A hívás közben nem szakítható meg; ezt a naplóüzenet jelezze.
3. A `grub-install` argumentumlistáját egy külön, tisztán tesztelhető függvény állítsa össze, amely hibát dob, ha a céleszköz vagy a csatolási pont üres, nem abszolút, vagy a csatolási pont `/`, `/boot` vagy `/efi` alatt van.

**Elfogadás:** egységtesztek mockolt `command`-dal: a pontos argumentumlista; elutasítás üres/hibás bemenetre és a gazdagép könyvtáraira; hiányzó GRUB esetén érthető üzenet és **nincs** romboló lépés; megváltozott partíciós tábla esetén hiba.

### T4. Az új író: `write_windows_bios`

**Hol:** `worker.py`, `tests/test_worker.py`.

**Sorrend (a `write_windows_uefi` mintájára; a közös lépéseket szervezd közös segédfüggvénybe úgy, hogy az UEFI-út viselkedése ne változzon):**

`require_programs` (a Legacy módhoz kellő programokkal) → `ensure_source_not_on_target` → `validate_target` → GRUB elérhetőségének ellenőrzése (**még a romboló lépés előtt**) → ISO csatolása → `scan_windows_iso(boot_mode="bios")` → kötetcímke kiolvasása → méretellenőrzés → `unmount_disk` → újabb `ensure_source_not_on_target` és `validate_target` → `assert_disk_unmounted` → `wipefs --all --force` → `sfdisk` (MBR) → `blockdev --rereadpt` / `partprobe`, várakozás a partíció-eszközre → `verify_mbr_layout` → `mkfs.ntfs` az ISO címkéjével és a meglévő geometria-argumentumokkal → NTFS boot-szektor ellenőrzése (`validate_ntfs_boot_sector`) → NTFS csatolása → fájlmásolás a meglévő másolóval → opcionális SHA-256 visszaellenőrzés → `install_bios_chainloader` → `sync` → leválasztás → záró `verify_mbr_layout` → kész.

**Elvárás:**
1. A `TARGET_MODIFIED` jelző, a megszakítási pontok, a takarítás (`finally`: ISO és NTFS leválasztása, ideiglenes könyvtár törlése) ugyanúgy működjön, mint az UEFI-írónál.
2. A záró naplóösszefoglaló írja le az elrendezést: MBR, egy aktív NTFS partíció, GRUB láncbetöltő a `/grub` könyvtárban, és hogy a pendrive **csak Legacy BIOS/CSM módban** indul.
3. A SHA-256 manifest csak az ISO fájljaira vonatkozik; a `/grub` könyvtár nem része.

**Elfogadás:** egységtesztek mockolt parancsokkal: a lépések sorrendje (a `wipefs --all --force` megléte, a `grub-install` a másolás után és a leválasztás előtt); megszakítás a `wipefs` után → takarítás lefut; megszakadt GUI-cső (a 0.2.2 `GuiPipeBrokenTests` mintájára); hiányzó GRUB → a céleszköz érintetlen.

### T5. Worker belépési pont

**Hol:** `worker.py` (`main()`), `tests/test_worker.py`.

**Elvárás:** új mód a meglévő `raw` és `windows` mellé (javasolt név: `windows-bios`), ugyanazzal az argumentumsorrenddel. Ismeretlen módnév továbbra is hiba. A wrapper és a polkit-szabály nem változik (az argumentumokat változatlanul adják tovább; ezt ellenőrizd).

**Elfogadás:** tesztek a `WindowsVerifyArgumentTests` mintájára: az új mód a `write_windows_bios`-t hívja a helyes ellenőrzési kapcsolóval és azonossággal; a régi módok változatlanok.

### T6. Grafikus felület

**Hol:** `app.py`, `ui_helpers.py` (ha kell), `tests/test_app.py`, `tests/test_packaging.py`.

**Elvárás:**
1. Windows ISO kiválasztásakor új választó: **„Indítási mód"**, két értékkel: „UEFI (GPT)" (alapértelmezett) és „Legacy BIOS (MBR)". Nem Windows ISO-nál a választó rejtett vagy tiltott.
2. Ha a GRUB i386-pc nem érhető el a gépen, a Legacy érték tiltott, és súgószöveg mondja meg a teendőt (`sudo pacman -S grub`).
3. A megerősítő párbeszédablak nevezze meg a választott módot, és Legacy módnál figyelmeztessen: a pendrive UEFI módban nem indul.
4. Rövid, állandó megjegyzés a választó mellett: a Legacy módot régebbi gépekhez szánjuk; az újabb Windows telepítők hardverkövetelményei miatt a telepítő a régi gépen megtagadhatja a telepítést. (Ne állíts konkrét verziókövetelményt, amit nem ellenőriztél.)
5. A GUI a workernek az új módnevet adja át; a kompakt ablakméret és a meglévő elrendezési tesztek nem sérülhetnek.

**Elfogadás:** offscreen GUI-tesztek: a választó csak Windows ISO-nál aktív; hiányzó GRUB → Legacy tiltva; a worker-argumentumok helyesek mindkét módban; a meglévő `tests/test_app.py` tesztek zöldek.

### T7. Integrációs teszt a termelési íróval

**Hol:** `tests/integration/test_loop_windows_bios.py` (a T0 teszt átalakítása), `.github/workflows/tests.yml`.

**Elvárás:**
1. A T0 kézi lépései helyett a teszt a `worker.write_windows_bios`-t hívja a loop-eszközre, a meglévő `loop_as_usb_disk()` helyettesítéssel, bind mountolt mappával az ISO helyett (a `test_loop_windows.py` mintájára), a teszt `bootmgr` fájllal.
2. Ellenőrzések: `sfdisk --json` (dos, egy aktív 7-es típusú partíció), NTFS-címke, minden másolt fájl SHA-256-ja, a `/grub/grub.cfg` tartalma, a T0 statikus ellenőrzései, nem maradt csatolás és ideiglenes könyvtár.
3. QEMU-s indítási próba `BMK_QEMU=1` mellett, a `BMK-BOOT-OK` megjelenésével.
4. Külön teszt: a régi, kétpartíciós GPT-s (Windows UEFI módú) lemezre írt Legacy mód után nem marad GPT-aláírás (sem elöl, sem hátul).
5. CI: a csomaglistába `grub-pc-bin`, `grub2-common`, `qemu-system-x86`; az integrációs lépésben `BMK_QEMU=1`. A `BMK_INTEGRATION_REQUIRED=1` mellett a QEMU hiánya is hiba legyen, ne skip.

**Elfogadás:** zöld a CI-ben és a gazda gépén. A meglévő három integrációs teszt változatlanul zöld.

### T8. Telepítő és függőségek

**Hol:** `install.sh`, `README.md`, `README.hu.md`, `tests/test_packaging.py`.

**Elvárás:**
1. Az `install.sh` csomaglistájába bekerül a `grub`. A README mindkét nyelven mondja ki: a csomag csak a `grub-install` eszközt és az i386-pc modulokat adja; a telepítése **nem** módosítja a gép saját rendszerbetöltőjét, és a BootMediaKit a `grub-install`-t kizárólag a kiválasztott pendrive-ra futtatja.
2. A README „Mit tud" és korlátok része frissül: a Legacy mód mit készít, mivel indul, mivel nem.
3. Csomagolási teszt: az `install.sh` tartalmazza a `grub` csomagot; a README-k említik a Legacy módot és a fenti megjegyzést.

**Elfogadás:** a tesztek zöldek; a `shellcheck` tiszta.

### T9. Dokumentáció

**Hol:** `README.md`, `README.hu.md`, `docs/TESTING.md`, `CONTRIBUTING.md`, `ROADMAP.md`, `CHANGELOG.md`.

**Elvárás:**
1. A `ROADMAP.md`-be ez a szakasz kerül a 0.2.2 fölé, állapotlistával; a régi „0.2.2+" lista megfelelő pontja lezárva.
2. `docs/TESTING.md`: az új integrációs teszt, a `BMK_QEMU` kapcsoló, és egy **kézi QEMU-próba** leírása kész pendrive-ra, írásvédetten (`-snapshot` vagy `readonly=on`), hogy a fizikai újraindítás előtt ellenőrizhető legyen az indulás.
3. A dokumentált parancsok egyezzenek a CI-vel; a `TestCommandDocumentationTests` ezt őrzi, szükség szerint bővítsd.

**Elfogadás:** a dokumentumokban szereplő parancsok szó szerint lefuttathatók tiszta klónon.

### T10. Kiadási commit (csak akkor, ha T0–T9 kész, a CI zöld, és a gazda visszajelzett)

1. `version.py`: `0.3.0`; README-k verziósora és állapotbekezdése; `CHANGELOG.md` (`Unreleased` → `0.3.0 — <dátum>`); `docs/TESTING.md` új legfelső szakasz a tesztjegyzőkönyvvel; `ROADMAP.md` ez a szakasz „Stabil kiadás".
2. A fizikai tesztek pipái **csak a gazda visszajelzése alapján** kerülnek be; ami nincs visszajelezve, az a jegyzőkönyvben „nem tesztelt"-ként szerepel.
3. `grep -rnIw "Unreleased\|TODO" . --exclude-dir=.git` találatai csak a munkaleírás szövegében és az azt őrző tesztben maradhatnak.
4. Pull request a `main`-re. A merge, a `v0.3.0` tag és a release a gazda dolga.

---

### Fizikai tesztek (a projekt gazdája végzi)

Az asszisztens ezeket nem végezheti el, és nem jelölheti késznek. Csak eldobható pendrive-on.

- [ ] Kézi QEMU-próba a kész Legacy pendrive-ról (írásvédetten): megjelenik a Windows Telepítő.
- [ ] Windows 10 x64 ISO, Legacy mód: indulás valódi gépen Legacy BIOS/CSM módban, a telepítő a partícióválasztóig. *(Visszajelzés 2026-11-11: két külön ISO, Windows 10 IoT Enterprise LTSC és Windows 11 IoT Enterprise LTSC, nagyon régi Core 2 Duo laptopon, Legacy módban: a pendrive elindult, a Windows Telepítő a particionálásig jutott, tovább nem lett próbálva. Az ISO-k architektúrája nem lett külön visszajelezve; a program naplója egy `CES_X64FREV_HU-HU_DV9` címkéjű ISO-t mutatott.)*
- [ ] Windows 7 SP1 ISO (ha van kéznél), Legacy mód: indulás és a telepítő első képernyője. (USB 3.0 portról a Windows 7 telepítő illesztőprogram hiányában elakadhat; ez nem a pendrive hibája, USB 2.0 porton próbáld.)
- [x] `sudo sfdisk -d /dev/sdX` a Legacy pendrive-on: `label: dos`, egy partíció, `type=7`, `bootable`. *(Visszajelzés 2026-11-11: `label: dos`, `sector-size: 512`, egyetlen partíció `start=2048, size=15562752, type=7, bootable`.)*
- [ ] Legacy mód olyan pendrive-on, amelyen előtte Windows UEFI mód (GPT) volt: `sudo wipefs /dev/sdX` nem mutat `gpt` sort.
- [ ] Ugyanaz a pendrive UEFI-only módban **nem** indul (elvárt viselkedés, a GUI figyelmeztetésével egyezik).
- [ ] Regresszió: Windows UEFI mód és Linux RAW mód továbbra is működik (egy-egy kiírás és indítás).
- [ ] A saját gép rendszerbetöltője érintetlen a `grub` csomag telepítése és egy Legacy kiírás után (a gép újraindul a megszokott módon).
- [ ] GRUB nélküli állapot: a `grub` csomag eltávolítása után a Legacy érték tiltott a felületen, a súgószöveg helyes.

---

### Későbbre halasztva (0.3.x és később)

- Kombinált „MBR, BIOS vagy UEFI" pendrive (NTFS + UEFI:NTFS segédpartíció egy MBR-en).
- Több pendrive egyidejű írása különböző ISO-kkal (feladatkezelő a GUI-ban, feladatok közötti forrás/cél ellenőrzés).
- A 0.2.2-ből nyitva maradt fizikai pontok: Windows 11 26H2 Secure Boot ki/be, a forrás-fájlrendszer hibaüzenete FUSE/overlay helyről, `fuseblk` forrás, eszközfrissítés kihúzás/visszadugás közben.
- A GitHub Actions lépések frissítése (Node.js 20 kivezetés) és az `ubuntu-latest` váltás hatásának ellenőrzése.
- Arch PKGBUILD, Debian/Ubuntu és Fedora támogatás (ott a `grub-install` neve és a modulkönyvtár eltérhet).
- Ismert ISO SHA-256 ellenőrzés kiírás előtt, Linux persistence.

## 0.2.2 — Stabil kiadás (2026-11-10): alaprendezés és automatizált tesztháló

> **Ez a szakasz egyben végrehajtható munkaleírás.** Aki (ember vagy asszisztens) ezt kapja feladatként, a fizikai, éles USB-teszteken kívül mindent el tud végezni belőle. A fizikai teszteket kizárólag a projekt gazdája végzi, lásd a „Fizikai tesztek" szakaszt. Az asszisztens ezeket nem állíthatja késznek.

### Állapot

- [x] T1. Forrás-fájlrendszer elutasítás: érthetőbb üzenet és pontosabb kör.
- [x] T2. Többeszközös btrfs: minden tag részt vesz az ütközésvizsgálatban.
- [x] T3. `lsblk` időtúllépés naplózása ismétlődés nélkül.
- [x] T4. A GUI-cső megszakadásának tesztjei és README-megjegyzés.
- [x] T5. Egyetlen verziószám-forrás (`version.py`).
- [x] T6. CI: shellcheck.
- [x] T7. CI: loop-eszközös integrációs tesztek.
- [x] T8. Dokumentáció-tisztítás.
- [x] T9. Kiadási commit a zöld CI és a gazda visszajelzése után. A merge és a `v0.2.2` tag a gazda dolga.

### Cél

A 0.2.1 kódját nem bővítjük új funkcióval. A cél a megmaradt közepes és alacsony prioritású hibák lezárása, valamint egy automatikus tesztháló, amely a lemezíró logika regresszióit éles USB nélkül is elkapja (például a `wipefs --force` kiesését). Utána indulhat a 0.3.0 fejlesztési ág.

**Nem cél:** új funkció (Windows Legacy BIOS, persistence, új disztribúció, ISO-letöltés), az írási folyamat sorrendjének átalakítása, a GPT-elrendezés megváltoztatása.

### Szabályok (invariánsok): ezeket nem szabad megsérteni

1. **A RAW-írás sorrendje marad:** `validate_target` → `ensure_source_not_on_target` → `unmount_disk` → újabb `ensure_source_not_on_target` és `validate_target` → `assert_disk_unmounted` → `wipefs --all --force` → írás → `sync` → opcionális visszaolvasás (`blockdev --flushbufs` után) → `blockdev --rereadpt`. A `--force` kötelező a Windows-módban is (a 0.2.1 fejlesztése közben egy köztes beta ezt kihagyta, és a Linux DD pendrive nem indult).
2. **Megszakításkor nincs `fsync`**, csak a fájlleíró lezárása. A megszakítás kooperatív marad (a worker `stdin`-en kapja a „cancel" sort), 130-as kilépési kóddal.
3. **A Windows-mód elrendezése nem változik:** GPT, 1. partíció NTFS (az ISO kötetcímkéjével), 2. partíció 1 MiB-os FAT `BMK_EFI`, Microsoft Basic Data típus, `GUID:63` attribútummal. A rögzített Rufus UEFI:NTFS képet csak a `fatlabel` módosíthatja.
4. **A GUI sosem fut rootként.** A polkit-akciót (`org.bootmediakit.policy`) és a wrappert (`bootmediakit-worker`) nem módosítjuk, hacsak az adott feladat kifejezetten nem kéri.
5. **Minden felhasználónak szánt szöveg magyar**, a mostani stílusban. Az új hibaüzenet legyen konkrét: mi történt és mit tegyen a felhasználó.
6. **Fail-closed:** ha a biztonsági ellenőrzés nem tud dönteni (forrás ismeretlen, mount nem azonosítható), a művelet megáll. Ezt nem lehet „átengedésre" lazítani. A feladatok csak az üzeneteket és az igazoltan biztonságos esetek körét módosíthatják.
7. **Verziószámot csak a kiadási commit emelhet** (T9). A fejlesztés közbeni commitok `0.2.1`-et hagyják az `APP_VERSION`-ben.

### Munkamenet

- Ág: `dev/0.2.2` az `origin/main`-ből. Feladatonként egy kis commit, `fix:`, `test:`, `ci:`, `docs:` előtaggal.
- Minden commit előtt: `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v` (kell hozzá a `PySide6`; jelenleg 98 teszt). Egyetlen meglévő tesztet sem lehet törölni vagy gyengíteni. Ha egy teszt a változtatás miatt elavul, az indoklás kerüljön a commit üzenetbe.
- Az új viselkedéshez regressziós teszt tartozik, ugyanabban a commitban.
- Nem kerülhet be új futási függőség a README és az `install.sh` frissítése nélkül.

---

### T1. Forrás-fájlrendszer elutasítás: érthetőbb üzenet és pontosabb kör

**Hol:** `worker.py`, `source_backing_majmins()` (a `non_block_backed_types` halmaz és a „fizikai háttértára nem igazolható" hiba).

**Most:** minden, a listán nem szereplő, nem `/dev/` forrású fájlrendszer (`fuse*`, `overlay`, `zfs`, `virtiofs`, `vboxsf`) általános biztonsági hibával elutasítja az ISO-t.

**Elvárás:**
1. A hibaüzenet nevezze meg a fájlrendszer típusát és a forrást, és mondja ki a teendőt: *„Másold az ISO-t helyi, blokkeszközön lévő lemezre (például a saját mappádba), majd válaszd ki újra."*
2. Vegyük fel a halmazba a **hálózati/virtuális, biztosan nem fizikai** típusokat: `virtiofs`, `vboxsf`, `fuse.sshfs`, `fuse.rclone`, `fuse.gvfsd-fuse`, `fuse.portal`. Ezekről nem kell blokkeszközt feloldani, mert nem lehetnek a céllemezen.
3. A **`fuseblk`** (ntfs-3g) és minden `/dev/…` forrású fájlrendszer továbbra is blokkeszközre oldódik fel, és ott megy az ütközésvizsgálat.
4. Az `overlay`, `zfs` és minden ismeretlen típus **marad elutasított**, de az új, érthető üzenettel. (Nem igazolható, hogy nem a céllemezen van.)

**Elfogadás:** az új típusokra külön teszt (engedett és elutasított), a `fuseblk`-ra és `overlay`-re is. A meglévő `test_source_backing_resolution_*` tesztek továbbra is zöldek.

### T2. Többeszközös btrfs: ne lehessen észrevétlenül a céllemezen a forrás

**Hol:** `worker.py`, `source_backing_majmins()`.

**Most:** a mountinfo csak egyetlen tagot ad vissza egy többeszközös btrfs-ből, a többi tag nem kerül az ütközésvizsgálatba.

**Elvárás:** `btrfs` típusú forrásnál olvasd ki a fájlrendszer összes tagját a `/sys/fs/btrfs/<UUID>/devices/` alól (az UUID-t a `/sys/fs/btrfs/` és a `blkid`/`findmnt` adja), és mindegyik tag fizikai őseit add a `backing` halmazhoz. Ha a listát nem lehet kiolvasni, **utasíts el** (fail-closed, érthető üzenettel).

**Elfogadás:** unit teszt mockolt sysfs-sel (két tag, ebből az egyik a cél; elutasítás), egytagú btrfs továbbra is működik, kiolvashatatlan lista → elutasítás.

### T3. `lsblk` időtúllépés naplózása: ne spameljen

**Hol:** `app.py`, `_finish_lsblk_error()` és `_lsblk_timed_out()`.

**Most:** csendes (automatikus) frissítésnél a hiba 5 másodpercenként új naplósor.

**Elvárás:** ugyanaz az üzenet egymás után csak egyszer kerüljön a naplóba. Az első sikeres frissítés után az üzenet újra megjelenhet (állapotváltozás). A kézi frissítés (gomb) továbbra is mutassa a párbeszédablakot.

**Elfogadás:** teszt a `tests/test_app.py`-ban: három egymás utáni csendes időtúllépés → egy naplósor; siker után újabb időtúllépés → új sor.

### T4. Windows-mód: a GUI-cső megszakadásának tesztelése és dokumentálása

**Hol:** `worker.py` (`OUTPUT_BROKEN`, `check_cancelled()`, `write_windows_uefi()`), `tests/test_worker.py`, `README.md`, `README.hu.md`.

**Elvárás:**
1. Teszt: mockolt `emit` / lezárt stdout mellett a `write_windows_uefi` a következő `check_cancelled()` ponton `OperationCancelled`-ot dob, a `TARGET_MODIFIED` állapotnak megfelelően, és a takarítás (leválasztás, ideiglenes könyvtár törlése) lefut.
2. Ugyanez a teszt a `write_raw`-ra is, ha még nincs.
3. README (angol és magyar), „Safety/Biztonság" szakasz: *ha a grafikus felület írás közben bezárul vagy megszakad, a worker biztonságosan leáll, de a pendrive részlegesen írt állapotban maradhat; ilyenkor az eszközt újra kell írni.*

**Elfogadás:** a tesztek zöldek, és mindkét README tartalmazza a megjegyzést.

### T5. Egyetlen verziószám-forrás

**Hol:** új `version.py`, `app.py`, `fetch_uefi_ntfs.py`, `install.sh`, `uninstall.sh` (ha listáz fájlt), `tests/test_packaging.py`.

**Elvárás:**
1. Új fájl: `version.py`, tartalma egyetlen sor: `__version__ = "0.2.1"`.
2. Az `app.py` `APP_VERSION`-je és a `fetch_uefi_ntfs.py` User-Agentje ebből olvasson (`from version import __version__`).
3. **Az `install.sh`-nak telepítenie kell a `version.py`-t** az `$APP_DIR`-be (`install -m 0644 "$SCRIPT_DIR/version.py" "$APP_DIR/version.py"`), különben a telepített alkalmazás induláskor összeomlik. A `fetch_uefi_ntfs.py` az `install.sh` elején fut a forráskönyvtárból, ott az import működik.
4. A `tests/test_packaging.py` ellenőrizze:
   - az `install.sh` telepíti a `version.py`-t;
   - a `README.md` és a `README.hu.md` „Version/Verzió" sora, a `CHANGELOG.md` legfelső szakaszcíme és a `docs/TESTING.md` aktuális szakaszcíme tartalmazza a `version.__version__` értéket;
   - nincs más helyen kódolt verziószöveg a `.py` fájlokban (kivéve a `version.py`-t).
5. A `worker.py` marad `-I` módú, és **nem** importálja a `version.py`-t (a privilegizált worker függőségeit nem bővítjük).

**Elfogadás:** a régi, szöveget kereső verziótesztek helyén az új tesztek állnak, és az `install.sh` fájllistája a `version.py`-val együtt konzisztens.

### T6. CI: shellcheck

**Hol:** `.github/workflows/tests.yml`.

**Elvárás:** `sudo apt-get install -y shellcheck`, majd `shellcheck -S warning install.sh uninstall.sh bootmediakit-worker`. A jelenlegi figyelmeztetéseket javítsd, vagy egy rövid, indokolt `# shellcheck disable=SCxxxx` sorral zárd le. Ne gyengítsd az ellenőrzés szintjét.

**Elfogadás:** a lépés zöld a CI-ben.

### T7. CI: loop-eszközös integrációs teszt (a legfontosabb a 0.2.2-ben)

**Hol:** új `tests/integration/` mappa (például `test_loop_raw.py`, `test_loop_windows.py`), `.github/workflows/tests.yml`, `docs/TESTING.md`.

**Elvárás:**
1. A tesztek **csak akkor futnak**, ha `BMK_INTEGRATION=1` és a folyamat root (`os.geteuid() == 0`) és elérhetők a `losetup`, `sfdisk`, `wipefs`, `mkfs.ext4`, `mkfs.ntfs`, `fatlabel`. Egyébként `unittest.SkipTest`. Így a helyi, nem root futtatás nem törik el.
2. **Raw teszt:** hozz létre egy 128 MiB-os `disk.img`-et régi GPT-vel (két partíció, az elsőn ext4), csatold `losetup -P`-vel, készíts egy 40 MiB-os, MBR-es „ISO" fájlt véletlen tartalommal, és hívd a `worker.write_raw`-t a loop eszközre. Ellenőrizd: a kiírt bájtok megegyeznek a forrással (`cmp`), a `wipefs` a régi GPT aláírásokat (az elsőt és a hátsót is) nem találja, csak a forrás táblája maradt.
3. **Windows-teszt:** egy ISO helyett egy mappa fájlokkal és bind mount (`worker.mount_iso` mockolva), `write_windows_uefi` a loop eszközre. Ellenőrizd a GPT-t (`sfdisk --json`: két Microsoft Basic Data partíció, a 2. `BMK_EFI`, `GUID:63`), az NTFS-címkét, a FAT-címkét és a másolt fájlok SHA-256-ját.
4. A loop eszközt stand-inként kezeld: a `worker.lsblk_tree` és a `validate_target` mockolva úgy, hogy a `loop` típust `disk`-nek veszi (ez a rész nem lehet a termelési kódban). A mockolást egy közös segédfüggvény végezze a `tests/integration/` alatt.
5. CI: új, külön lépés `sudo` alatt: `sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v`. A GitHub-runneren van udev és `ntfs-3g`, a kernel NTFS3-driver nem biztos, hogy van; a worker `ntfs-3g` tartalékot használ.
6. Takarítás minden esetben (`addCleanup`): `umount`, `losetup -d`, ideiglenes fájlok törlése.

**Elfogadás:** a két teszt zöld a CI-ben és helyben (`sudo`-val). Ha a runneren a loop partíció-eszköz nem jön létre, a teszt jelezze ezt érthetően (ne hibásan zöld legyen), és a probléma kerüljön a `docs/TESTING.md`-be.

**Megjegyzés:** ez a teszt nem helyettesíti a fizikai USB-t. A kernel által *használt* partíciókra és az USB-specifikus viselkedésre (`rm`, `tran=usb`) nem ad bizonyítékot.

### T8. Dokumentáció-tisztítás

**Hol:** `README.md`, `README.hu.md`, `docs/TESTING.md`, `CONTRIBUTING.md`, `ROADMAP.md`.

**Elvárás:**
1. A „Run the automated tests / Futtatás" parancsok egyezzenek a CI-vel: `py_compile` az `app.py worker.py iso_utils.py ui_helpers.py fetch_uefi_ntfs.py version.py` fájlokra, `bash -n install.sh uninstall.sh bootmediakit-worker`, `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v`, és említsd, hogy a GUI-tesztekhez `PySide6` kell.
2. A `docs/TESTING.md`-ben az integrációs teszt futtatása (T7) és a skip-feltételek.
3. A `CHANGELOG.md`-ben új, legfelső szakasz a 0.2.2-nek **csak a T9-ben** (a kiadási commitnál) jelenik meg, fejlesztés közben a `## Unreleased` címet használd, és minden feladat adjon hozzá egy sort.

**Elfogadás:** a dokumentumokban szereplő parancsok szó szerint lefuttathatók egy tiszta klónon.

### T9. Kiadási commit (csak akkor, ha T1–T8 kész és a CI zöld)

1. `version.py`: `0.2.2`; README-k, `CHANGELOG.md` (`Unreleased` → `0.2.2 — <dátum>`), `docs/TESTING.md` fejléc, `ROADMAP.md` ez a szakasz „Stabil kiadás".
2. A `ROADMAP.md`-ben a fizikai tesztek pipái **csak a gazda visszajelzése alapján** kerülnek be.
3. `grep -rniI "Unreleased\|TODO\|RC" .` ne adjon találatot a forrásban (a `CHANGELOG.md` korábbi szakaszai kivételével).
4. A merge és a tag (`v0.2.2`) a gazda dolga.

---

### Fizikai tesztek (a projekt gazdája végzi)

Az asszisztens ezeket nem végezheti el, és nem jelölheti késznek. A pipák a gazda 2026-11-10-i visszajelzését rögzítik; a kiadást a gazda a nyitva maradt pontok ismeretében hagyta jóvá.

- [x] Linux DD/RAW, UEFI és Legacy BIOS (Linux Mint ISO), RAW visszaolvasás **bekapcsolva** egyszer.
- [x] A RAW teszt **olyan pendrive-on is**, amelyen előtte Windows-mód (GPT, két partíció) volt.
- [ ] Windows 10/11 IoT LTSC, UEFI: az USB elkészítése, `sfdisk -d` ellenőrzés (1. partíció az ISO címkéjével, 2. `BMK_EFI`, `GUID:63`), a telepítő első újraindításig. *(Visszajelzés a 0.2.2-höz: az USB elkészült, a partíciónevek jók, a pendrive bootol; az `sfdisk -d` szerinti `GUID:63` és a telepítés az első újraindításig nem lett külön visszajelezve.)*
- [ ] Windows 11 26H2, Secure Boot ki és be, a partícióválasztóig.
- [ ] A T1 hibaüzenet kipróbálása: ISO egy FUSE/hálózati/overlay helyről.
- [ ] A program normál indítása, eszközfrissítés (kihúzás/visszadugás közben is), tiszta kilépés CachyOS-en. *(Visszajelzés: az indítás és a tiszta kilépés rendben; a kihúzás/visszadugás közbeni frissítés nem lett visszajelezve.)*
- [ ] Egy `fuseblk` (ntfs-3g) lemezen lévő ISO továbbra is használható.

---

### Későbbre halasztva (0.3.0 és később)

- Windows Legacy BIOS/MBR mód. *(A 0.3.0-ban megvalósítva: MBR + aktív NTFS + a gépre telepített GNU GRUB i386-pc láncbetöltő; a BootMediaKit nem tartalmaz Microsoft boot-kódot, így a licenckérdés lezárult. A kombinált BIOS+UEFI változat későbbre maradt.)*
- Arch PKGBUILD és reprodukálható csomagellenőrzések.
- Debian/Ubuntu, majd Fedora támogatás, a Polkit-beállítás és a csomagtelepítés szétválasztásával az író logikától.
- Ismert ISO SHA-256 ellenőrzés kiírás előtt, Linux persistence.

## 0.2.1 — Stabil kiadás

### Elkészült fejlesztések

- [x] Aszinkron USB-meghajtó-felderítés Qt-folyamattal, időkorláttal és párhuzamos frissítés elleni védelemmel.
- [x] Forrás/cél fizikai meghajtó-ütközésvizsgálatának megerősítése Btrfs al-köteteknél és egymásra épülő autofs/CIFS csatolásoknál.
- [x] Biztonságos leállás, ha a forrásfájlt tartalmazó fájlrendszer fizikai meghajtója nem állapítható meg egyértelműen.
- [x] Worker-eseményküldés kezelése bezáródó GUI vagy megszakadt csővezeték esetén; a duplikált hibajelzés elkerülése.
- [x] Qt objektumok és gyermekfolyamatok rendezett leállítása az alkalmazás bezárásakor.
- [x] Qt SVG-megjelenítővel nem kompatibilis szűrőelem eltávolítása.
- [x] RAW írás előtti aláírástörlés, a teljes lemez leválasztásának ellenőrzése és a műveleti sorrendet ellenőrző regressziós tesztek.
- [x] Automatizált Python-, shell-, csomagolási és offscreen GUI-ellenőrzések.

### Fizikai validáció

- [x] Linux Mint 22.3 Cinnamon DD/RAW pendrive sikeres indítása UEFI módban.
- [x] Linux DD/RAW pendrive sikeres indítása Legacy BIOS/MBR módban.
- [x] Windows 10 és Windows 11 IoT Enterprise LTSC x64 UEFI telepítés sikeres befejezése a tesztelt rendszeren.
- [x] A normál Windows 11 26H2 x64 telepítő eljutott a Windows Setup partícióválasztó képernyőjéig Secure Boot kikapcsolt állapotában.
- [x] Ugyanez a Windows 11 26H2 x64 teszt Secure Boot bekapcsolt állapotában is eljutott a partícióválasztó képernyőig.
- [ ] A Windows 11 26H2 telepítés folytatása és befejezése – ez a lépés nem része az igazolt 0.2.1 teszteredménynek.
- [ ] További alaplapokon és UEFI firmware-eken végzett Secure Boot kompatibilitási tesztek.

### Automatizált ellenőrzések

- [x] GitHub Actions: Python fordítási, shell szintaktikai, UEFI:NTFS segédkép-ellenőrzési, NTFS formázási dry-run, FAT címkézési, unit-, csomagolási és offscreen GUI-tesztek. Sikeres futás: [41980736701](https://github.com/rsanya87/bootmediakit/actions/runs/41980736701).

## 0.2.2+ — Következő fejlesztési és tesztelési célok

- [ ] ISO kötetcímke-megőrzés tesztelése további Windows ISO-kon, szóközökkel és vegyes kis-/nagybetűkkel.
- [ ] További Windows-verziók és UEFI firmware-ek tesztelése.
- [ ] Secure Boot be- és kikapcsolt állapotának célzott vizsgálata több firmware-en.
- [ ] Célmeghajtó kihúzásának/visszacsatlakoztatásának, valamint a forrás céllemezen található esetének fizikai tesztje.
- [x] Loop-device integrációs tesztek GPT, NTFS és FAT vizsgálatára (0.2.2, T7). A hibakezelés és a megszakítás utáni takarítás loop-eszközös vizsgálata még nyitott.
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

- ~~Windows Legacy BIOS/CSM telepítő~~ (0.3.0). Kombinált BIOS+UEFI Windows pendrive egyetlen MBR-rel.
- Windows To Go és FreeDOS.
- Linux persistence.
- USB-meghajtó állapot- és kapacitástesztek.
- Lemezkép-ellenőrzőösszegek és kiadói aláírás ellenőrzése.
- Opcionális ISO-letöltés/katalógus.
- Rugalmasabb formázási lehetőségek.
