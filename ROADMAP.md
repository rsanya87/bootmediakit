# Roadmap

A feladat akkor tekinthető késznek, ha az automatizált ellenőrzések és a hozzájuk tartozó valós eszközös tesztek eredménye is rögzítve van.

## 0.2.2 — Alaprendezés és automatizált tesztháló (hibajavító kiadás)

> **Ez a szakasz egyben végrehajtható munkaleírás.** Aki (ember vagy asszisztens) ezt kapja feladatként, a fizikai, éles USB-teszteken kívül mindent el tud végezni belőle. A fizikai teszteket kizárólag a projekt gazdája végzi, lásd a „Fizikai tesztek" szakaszt. Az asszisztens ezeket nem állíthatja késznek.

### Állapot (`dev/0.2.2` ág)

- [x] T1. Forrás-fájlrendszer elutasítás: érthetőbb üzenet és pontosabb kör.
- [x] T2. Többeszközös btrfs: minden tag részt vesz az ütközésvizsgálatban.
- [x] T3. `lsblk` időtúllépés naplózása ismétlődés nélkül.
- [x] T4. A GUI-cső megszakadásának tesztjei és README-megjegyzés.
- [x] T5. Egyetlen verziószám-forrás (`version.py`).
- [x] T6. CI: shellcheck.
- [x] T7. CI: loop-eszközös integrációs tesztek.
- [x] T8. Dokumentáció-tisztítás.
- [ ] T9. Kiadási commit: csak zöld CI és a gazda fizikai tesztjei után.

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

Az asszisztens ezeket nem végezheti el, és nem jelölheti késznek.

- [ ] Linux DD/RAW, UEFI és Legacy BIOS (Linux Mint ISO), RAW visszaolvasás **bekapcsolva** egyszer.
- [ ] A RAW teszt **olyan pendrive-on is**, amelyen előtte Windows-mód (GPT, két partíció) volt.
- [ ] Windows 10/11 IoT LTSC, UEFI: az USB elkészítése, `sfdisk -d` ellenőrzés (1. partíció az ISO címkéjével, 2. `BMK_EFI`, `GUID:63`), a telepítő első újraindításig.
- [ ] Windows 11 26H2, Secure Boot ki és be, a partícióválasztóig.
- [ ] A T1 hibaüzenet kipróbálása: ISO egy FUSE/hálózati/overlay helyről.
- [ ] A program normál indítása, eszközfrissítés (kihúzás/visszadugás közben is), tiszta kilépés CachyOS-en.
- [ ] Egy `fuseblk` (ntfs-3g) lemezen lévő ISO továbbra is használható.

---

### Későbbre halasztva (0.3.0 és később)

- Windows Legacy BIOS/MBR mód (MBR + aktív NTFS + UEFI:NTFS), előbb a boot-kód licencének tisztázásával.
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

- Windows Legacy BIOS/CSM telepítő.
- Windows To Go és FreeDOS.
- Linux persistence.
- USB-meghajtó állapot- és kapacitástesztek.
- Lemezkép-ellenőrzőösszegek és kiadói aláírás ellenőrzése.
- Opcionális ISO-letöltés/katalógus.
- Rugalmasabb formázási lehetőségek.
