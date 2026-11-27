[English](TESTING.md) | Magyar

# Tesztelés

## BootMediaKit 0.4.0 — Stabil kiadás (2026-11-27)

A 0.4.0 a grafikus felületet függetleníti az asztali környezettől (megjelenés, elrendezés, DPI, a polkit-ügynök hibái), és azonosítókat ad a worker eseményeihez. A három writer nem változott: a writer-ujjlenyomat tesztek, amelyek a 0.3.0-s kóddal, minden más változtatás előtt készültek, a kiadáson változtatás nélkül sikeresek.

### Automatizált ellenőrzések

A GitHub Actions tesztkészlet sikeres volt a kiadási commit előtti utolsó olyan commiton, amelynek programfájljai azonosak a kiadáséval: [run 46055903239](https://github.com/rsanya87/bootmediakit/actions/runs/46055903239) (`0054196`). Az utána következő commitok csak a dokumentációt és a verziószámot változtatják. A munkafolyamat futtatja:

- a 384 egység-, csomagolási, offscreen GUI-, téma-, elrendezés-, pseudo-locale-, üzenetazonosító-, célállapot-, terminálmegszakítás- és writer-ujjlenyomat tesztet (a 0.3.0-ban 213 volt); az elrendezési teszteket DejaVu Sans és Noto Sans betűtípussal is; egy kihagyott teszt a lépést elbuktatja;
- a tíz rootként futó loop-eszközös integrációs tesztet `BMK_INTEGRATION_REQUIRED=1` és `BMK_QEMU=1` mellett, a 0.3.0-hoz képest változatlanul.

Ugyanezek az egység-/GUI-tesztek (384) és a rootként futó integrációs tesztek (10, egy sem kihagyva) a karbantartó CachyOS gépén is sikeresek voltak 2026-11-27-én, a kiadással azonos programfájlokkal.

### A 0.4.0 igazolt fizikai ellenőrzései

A karbantartó jelentései 2026-11-25-ről, 2026-11-26-ról és 2026-11-27-ről; a részletek, a környezetek és a mért értékek lent, az [Asztali tesztmátrix (0.4.0)](#asztali-tesztmátrix-040) részben vannak.

- **Asztali környezetek:** KDE Plasma 6.8 (Wayland, fő gép, két monitor), valamint virtuális gépben GNOME 51.1 (Wayland; GTK-témák: `adw-gtk3-dark` és `Adwaita`), XFCE 4.20, Cinnamon 6.8 és MATE 1.28 (X11) és LXQt (a munkamenet típusa nincs rögzítve): indítás és polkit-jelszókérés; világos, sötét és automatikus megjelenés, a kézi váltó színkeveredés nélkül; fájlválasztó és ikonok; 1280×800 és 1366×768 100% és 125% skálázással görgetősáv nélkül; felbontásváltás futás közben. KDE Plasma alatt ezen felül: 150% és 200% nagyobb betűmérettel, skálaváltás futás közben, az ablak átvitele a kisebb monitorra, és annak a monitornak a kihúzása, amelyen az ablak volt.
- **880×550-es minimális ablak:** XFCE alatt 1024×640 logikai képponton (1280×800 125%-on): kerettel együtt elfér, 29 px tartalék, görgetősáv nincs. KDE Plasma: a monitor 1280×800-at nem kínál, ezért a szigorúbb 1280×720-on 125%-on ellenőrizve: elfér, görgetősáv nincs.
- **Polkit-ügynök nélkül** (Openbox): érthető hibaablak; a megszakítás és a bezárás szövegei a jelszókérés alatt; Ctrl+C a jelszókérésnél: nincs összeomlás, a kilépési kód 130, a terminálon megjelenik a sor az érintetlen célmeghajtóról.
- **Megszakítás a hitelesítés alatt grafikus ügynökkel** (XFCE, polkit-gnome): a Mégse után a pkexec 126-tal tér vissza, és megjelenik a „semmi nem indult el, a célmeghajtóhoz nem nyúltunk” üzenet; Megszakítás, majd a jó jelszó után a lemez nem változott (egyetlen mérés, nem garancia). GNOME alatt a polkit-ablak modális, ezért ott ez a próba nem alkalmazható (jóváhagyva).
- **Írási regresszió a fő gépen** (`docs/REGRESSION_CHECKLIST.md`, a kiadás telepített programfájljai): Linux Mint 22.3 XFCE DD/RAW visszaolvasással (UEFI és Legacy BIOS módban is elindul); Windows 11 26H2 UEFI és Legacy pendrive ellenőrzéssel (az UEFI-s pendrive elindul; a Legacy pendrive Legacy/CSM módban elindul, és a fő gép NTFS-t olvasó firmware-én UEFI módban is); egy hibás pendrive RAW módban: az írás sikeres, a visszaolvasás hibát jelez; a fő gép utána rendesen elindul; a `grub` csomag nélkül a Legacy lehetőség a súgójával tiltva van.

### Kiadási elfogadási jegyzőkönyv

- A writer-ujjlenyomatok változatlanok; nincs fix `Noto Sans`, nincs dupla skálázás; a `msg_id`/`msg_args` dokumentált és tesztelt: sikeres (CI).
- Világos/sötét mód olvasható minden mátrix-DE-ben, a kézi váltó és az automatikus mód visszaállítása: sikeres (fizikai). A sötét tartalék nem besorolható palettánál: csak offscreen tesztek, fizikailag nem fordult elő.
- A minimális ablakméret az 1280×800 és 1366×768 kijelzők munkaterületén görgetősáv nélkül: sikeres (XFCE alatt 1024×640-en mérve, KDE Plasma alatt a szigorúbb 1024×576-on).
- A hiányzó polkit-ügynök érthető hibát ad; a wrapper és a polkit-akció változatlan: sikeres.
- Egység-, GUI-, csomagolási, loop- és QEMU-tesztek a CI-ben és a karbantartó gépén: sikeres.
- Írási regresszió (RAW, Windows UEFI, Windows Legacy, a gép saját rendszerbetöltője érintetlen; GRUB nélkül): sikeres.
- A munkaleírástól való jóváhagyott eltérések és a halasztott tételek: lásd [docs/history/0.4.0.md](history/0.4.0.md).
- Nem tesztelt vagy nem rögzített: az ablak bezárása a Ctrl+C-vel egy időben; a kilépési kód és a worker záró üzenete a jó jelszavas megszakítás után (XFCE); a Qt munkaterület és a keret a minimumon KDE Plasma alatt; a Wayland-ráhagyás után pontosan megmaradó pixelek KDE Plasma és GNOME alatt; KDE Plasma X11-munkamenet (nincs telepítve) és GNOME X11 alatt (a VM-ben nem érhető el); nagy kontrasztú rendszertéma valódi asztalon; két, eltérő skálázású monitor; valódi laptopkijelző; a kiadás írásainak `sfdisk -d`, `wipefs` és `lsblk` kimenete, és hogy meddig jutott a Windows Setup; a 0.2.2-ből és a 0.3.0-ból nyitva maradt fizikai tételek ([docs/history/](history/)).

A mockolt egységteszteket és a loop-eszközös teszteket ne tekintsd a fizikai hardver viselkedésének bizonyítékának. Romboló tesztet csak eldobható adathordozón végezz. Soha ne használj tesztcélnak olyan meghajtót, amelyen a forrás-ISO vagy felhasználói adat van.

## BootMediaKit 0.3.0 — Stabil kiadás (2026-11-24)

A 0.3.0 a Windows Legacy BIOS/MBR módot adja hozzá. A Linux DD/RAW írási sorrend és a Windows UEFI GPT-elrendezés a 0.2.2-höz képest nem változott; a meglévő egység- és integrációs tesztjeik változtatás nélkül sikeresek.

### Automatizált ellenőrzések

A GitHub Actions tesztkészlet sikeres volt az utolsó, kiadás előtti forrás-commiton: [run 45436385317](https://github.com/rsanya87/bootmediakit/actions/runs/45436385317). Az utána következő kiadási commit csak a verziószámot és a dokumentációt változtatja. A 0.2.2 ellenőrzései mellett a munkafolyamat most futtatja:

- a 213 egység-, csomagolási és offscreen GUI-tesztet (a 0.2.2-ben 129 volt);
- tíz rootként futó loop-eszközös integrációs tesztet (a 0.2.2-ben három volt): a T0 GRUB-láncbetöltési kaput ntfs3-mal és ntfs-3g-vel, a termelési `write_windows_bios` writert, egy Legacy írást Windows UEFI pendrive-ra (nem marad sem elsődleges, sem tartalék GPT-fejléc), valamint a meglévő RAW és Windows UEFI writer-teszteket;
- `BMK_QEMU=1` mellett a Legacy pendrive három QEMU/SeaBIOS-indítását (T0 ntfs3, T0 ntfs-3g, termelési writer), amelyek mindegyikében a teszt-`bootmgr` kiírja a `BMK-BOOT-OK` szöveget.

A loop-eszközös integrációs tesztek (10/10) a fejlesztés közben a karbantartó CachyOS gépén is sikeresek voltak (T7).

### A 0.3.0 igazolt fizikai ellenőrzései

A karbantartó jelentései 2026-11-11-ről és 2026-11-24-ről:

- **Windows Legacy BIOS valódi hardveren:** a Windows 10 IoT Enterprise LTSC x64 és a Windows 11 IoT Enterprise LTSC (x64; a Windows 11 csak x64-ként létezik) Legacy pendrive egy nagyon régi Core 2 Duo laptopon elindult; a Windows Setup a particionálási képernyőig jutott. A telepítés nem folytatódott.
- **Windows 7 SP1:** `hu_windows_7_professional_with_sp1_vl_build_x64_dvd_u_677833` Legacy (MBR) módban kiírva; a Setup elindult.
- **Legacy elrendezés:** az `sfdisk -d` kimenete `label: dos`, `sector-size: 512` és egyetlen partíció `start=2048, type=7, bootable`.
- **Legacy a korábban GPT-s pendrive-on:** egy Windows UEFI elrendezésű pendrive-ra írt Legacy után a `wipefs` csak `dos` bejegyzést mutatott, `gpt`-t nem.
- **Kézi QEMU-próba:** a kész Legacy pendrive QEMU/SeaBIOS alatt a Windows Setupot mutatta. OVMF-fel nem indult el.
- **Csak UEFI-s firmware:** egy Gigabyte B850 D3HP alaplapon kikapcsolt CSM mellett a Legacy pendrive `UEFI:` előtaggal jelent meg, és UEFI módban elindította a Windows Setupot (`PEFirmwareType` 0x2), valószínűleg azért, mert a firmware NTFS-drivere olvassa az ISO saját `efi\boot\bootx64.efi` fájlját. Ezt nem tekintjük hibának; a grafikus felület, a worker naplója és a README-k azt írják, hogy a pendrive Legacy BIOS/CSM indításhoz készül, és UEFI-ben csak NTFS-t olvasó firmware-en indulhat.
- **Regresszió:** Windows UEFI mód (az `sfdisk` kimenet a várt, a Setup UEFI-ből elindult a karbantartó fő gépén) és Linux Mint DD/RAW (elindult UEFI-ből és egy Legacy gépen).
- **A gép saját rendszerbetöltője:** a Windows UEFI próba után a karbantartó CachyOS rendszere rendesen elindult; a `grub` csomag ekkor telepítve volt, és korábban Legacy írások is készültek.
- **GRUB nélkül:** a `grub` csomag eltávolítása után a Legacy lehetőség a helyes megjegyzéssel és súgóval szürke volt; a visszatelepítés után újra választható lett.
- **Ellenőrzés:** a SHA-256 ellenőrzés (Windows) és a teljes visszaolvasás (Linux RAW) működött; egy részben hibás pendrive-on mindkettő ellenőrzési hibát jelzett.

### Kiadási elfogadási jegyzőkönyv

- Windows 10/11 IoT Enterprise LTSC x64 Legacy BIOS indítás a Setup particionálási képernyőjéig: sikeres.
- Windows 7 SP1 x64 Legacy BIOS, a Setup indulása: sikeres.
- `sfdisk -d` MBR-elrendezés és `wipefs` korábbi GPT után: sikeres.
- A kész pendrive kézi QEMU/SeaBIOS-indítása: sikeres.
- Csak UEFI-s viselkedés: NTFS-driver nélkül (OVMF) nem indul; NTFS-t olvasó firmware-ű Gigabyte B850-en elindult. A dokumentáció ennek megfelelően átfogalmazva.
- A Windows UEFI és a Linux DD/RAW mód regressziója: sikeres.
- A gép saját rendszerbetöltője érintetlen; GRUB nélkül a Legacy lehetőség tiltva: sikeres.
- Fizikailag nem tesztelt: teljes Windows-telepítés Legacy pendrive-ról (a Setup a particionálásnál vagy az első képernyőn megállt); a 0.2.2-ből nyitva maradt tételek (Windows 11 26H2 Secure Boot ki/be, a forrás-fájlrendszer elutasító üzenete FUSE/hálózati/overlay forrásnál, `fuseblk` forrás, eszközfrissítés kihúzás/visszadugás közben).

A mockolt egységteszteket és a loop-eszközös teszteket ne tekintsd a fizikai hardver viselkedésének bizonyítékának. Romboló tesztet csak eldobható adathordozón végezz. Soha ne használj tesztcélnak olyan meghajtót, amelyen a forrás-ISO vagy felhasználói adat van.

## BootMediaKit 0.2.2 — Korábbi kiadás tesztjegyzőkönyve (2026-11-10)

A 0.2.2 karbantartó kiadás. Az írási sorrend és a Windows mód GPT-elrendezése a 0.2.1-hez képest nem változott.

### Automatizált ellenőrzések

A GitHub Actions tesztkészlet sikeres volt az utolsó, kiadás előtti forrás-commiton: [run 42714445280](https://github.com/rsanya87/bootmediakit/actions/runs/42714445280). Az utána következő kiadási commit csak a verziószámot és a dokumentációt változtatja. A 0.2.1 ellenőrzései mellett a munkafolyamat most futtatja:

- a `shellcheck -S warning` ellenőrzést a telepítőn, az eltávolítón és a privilegizált worker-wrapperen;
- a 129 egység-, csomagolási és offscreen GUI-tesztet;
- három rootként futó loop-eszközös integrációs tesztet, amelyek a valódi RAW és Windows writert lemezképekre futtatják (lásd [Loop-eszközös integrációs tesztek](#loop-eszközös-integrációs-tesztek)).

Ugyanezek az egység- és integrációs tesztek a karbantartó CachyOS gépén is sikeresek voltak (Python 3.14, util-linux 2.42).

### A 0.2.2 igazolt fizikai ellenőrzései

- **Linux DD/RAW visszaolvasásos ellenőrzéssel:** a Linux Mint 22.3 pendrive fizikai USB-ről elindult Legacy BIOS/MBR és UEFI módban.
- **RAW egy korábban Windows módú pendrive-ra:** ugyanaz a RAW írás olyan pendrive-ra is elkészült, amelyen közvetlenül előtte a Windows mód kétpartíciós GPT-je volt; az eredmény mindkét módban elindult. Az első indításkor a Linux Mint saját `writable` partíciót hozott létre a kép utáni szabad helyen; ezt az élő rendszer teszi, nem a BootMediaKit.
- **Windows 10/11 IoT Enterprise LTSC, UEFI:** a pendrive elkészült, az első partíció az ISO kötetcímkéjét viseli, a második neve `BMK_EFI`; a pendrive ugyanúgy elindul, mint a 0.2.1-gyel.
- **Telepített alkalmazás:** az `install.sh` telepíti a `version.py`-t; az alkalmazás CachyOS-en elindul és rendben kilép.

### Kiadási elfogadási jegyzőkönyv

- Linux DD/RAW indítás UEFI és Legacy BIOS/MBR módban, bekapcsolt visszaolvasással: sikeres.
- RAW írás korábbi Windows módú GPT-re: sikeres.
- Windows IoT LTSC pendrive készítése, partíciónevek és indítás: sikeres.
- A `GUID:63` attribútum `sfdisk -d`-vel és a Windows Setup az első újraindításig: a 0.2.2-hez nem lett jelentve (a 0.2.1-en ellenőrizve; az attribútumot az integrációs teszt lefedi).
- Windows 11 26H2 szabványos ISO kikapcsolt és bekapcsolt Secure Boottal: a 0.2.2-hez nem lett megismételve (a 0.2.1-en a lemezválasztó képernyőig ellenőrizve).
- Az új forrás-fájlrendszer elutasító üzenet FUSE/hálózati/overlay forrásnál, ISO `fuseblk` (ntfs-3g) lemezen, és az eszközfrissítés kihúzás/visszadugás közben: fizikailag nem tesztelt; csak egységtesztek fedik.

A mockolt egységteszteket és a loop-eszközös teszteket ne tekintsd a fizikai hardver viselkedésének bizonyítékának. Romboló tesztet csak eldobható adathordozón végezz. Soha ne használj tesztcélnak olyan meghajtót, amelyen a forrás-ISO vagy felhasználói adat van.

## BootMediaKit 0.2.1 — Korábbi kiadás tesztjegyzőkönyve (2026-11-05)

### Automatizált ellenőrzések

A GitHub Actions tesztkészlet sikeres volt az utolsó kiadásjelölt forrás-commiton: [run 41980736701](https://github.com/rsanya87/bootmediakit/actions/runs/41980736701). A munkafolyamat lefedi:

- a grafikus felület, a worker, az ISO-segédek és a UI-segédek Python-fordítását;
- a telepítő, az eltávolító és a privilegizált worker-wrapper shell-szintaxis-ellenőrzését;
- a rögzített UEFI:NTFS segédkép letöltését és hash-ellenőrzését;
- az NTFS-formázás argumentumainak valódi programmal végzett próbafuttatását (dry-run);
- egy tesztet, amely a UEFI:NTFS segédkép egy ideiglenes másolatát `BMK_EFI` címkével látja el, az eredeti forrást változatlanul hagyva;
- egység-, csomagolási és offscreen GUI-teszteket az eszközbiztonságra, a forrás/cél ütközésvizsgálatra, a megszakítási határokra, a polkit-csomagolásra, a grafikus felület életciklusára, az ISO-metaadatokra és a GPT-partíciók kezelésére.

A helyi futtatáshoz lásd lent: [Az automatizált tesztek futtatása](#az-automatizált-tesztek-futtatása).

### A 0.2.1 igazolt fizikai ellenőrzései

- **Linux DD/RAW:** a Linux Mint 22.3 Cinnamon pendrive fizikai USB-ről sikeresen elindult UEFI és Legacy BIOS/MBR módban.
- **Windows IoT LTSC:** a Windows 10 és Windows 11 IoT Enterprise LTSC x64 telepítő pendrive a tesztelt rendszer(ek)en sikeresen befejezte az UEFI-s telepítést.
- **Windows 11 26H2 szabványos ISO:** a Windows Setup kikapcsolt és bekapcsolt Secure Boottal is a lemezválasztó/particionálási képernyőig jutott. A partícióválasztó képernyőn túl a telepítés nem fejeződött be, és nem állítjuk teljes telepítési tesztként sikeresnek.
- **A Secure Boot hatóköre:** a 26H2 Setup sikeres indulása csak a tesztfirmware-en megfigyelt indítási utat igazolja. Nem igazol kompatibilitást minden UEFI-megvalósítással, tanúsítvány-adatbázissal vagy visszavonási állapottal.

### Kiadási elfogadási jegyzőkönyv

- Linux DD/RAW indítás UEFI és Legacy BIOS/MBR módban: sikeres.
- Windows 10 és Windows 11 IoT Enterprise LTSC UEFI-s telepítés: sikeres.
- Windows 11 26H2 szabványos ISO, Secure Boot ki és be, a Setup lemezválasztásáig: eddig a lépésig sikeres.
- Windows 11 26H2 telepítés a lemezválasztáson túl: nem tesztelt.
- További firmware-ek, nem Arch-alapú disztribúciók, fizikai kihúzás/visszadugás közbeni versenyhelyzetek és a célmeghajtón lévő forrás elutasítása a kiadás igazolt tesztmátrixán kívül maradnak.

A mockolt egységteszteket ne tekintsd a fizikai hardver viselkedésének bizonyítékának. Romboló tesztet csak eldobható adathordozón végezz. Soha ne használj tesztcélnak olyan meghajtót, amelyen a forrás-ISO vagy felhasználói adat van.

## Az automatizált tesztek futtatása

### Statikus ellenőrzések, egységtesztek és offscreen GUI-tesztek

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py theme.py fetch_uefi_ntfs.py version.py
bash -n install.sh uninstall.sh bootmediakit-worker
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

Futási függőségek (az `install.sh` által telepített Arch-csomagok, amelyeket mindkét README és a `CONTRIBUTING.md` is felsorol): `pyside6`, `util-linux`, `parted`, `ntfs-3g`, `ntfsprogs`, `dosfstools`, `polkit`, `7zip`, `grub`. Csak a tesztekhez: a DejaVu Sans és Noto Sans betűtípus (Arch: `ttf-dejavu`, `noto-fonts`; Ubuntu CI: `fonts-dejavu-core`, `fonts-noto-core`, `fontconfig`), `shellcheck`, `desktop-file-utils`, valamint QEMU az integrációs indítási próbákhoz.

A GUI-tesztekhez (`tests/test_app.py`) `PySide6` kell. A `tests/` moduljai, amelyeket ez a parancs mind root nélkül futtat:

- `test_worker.py`: a privilegizált worker egységtesztjei mockolt parancsokkal (a cél és a forrás biztonsági ellenőrzései, többeszközös Btrfs tagjai, ISO-címkék, az UEFI GPT és a Legacy MBR elrendezés, a GRUB-láncbetöltő argumentumai és ellenőrzései, RAW írás és visszaolvasás, másolás és SHA-256 ellenőrzés, NTFS-csatolás, megszakítás és megszakadt GUI-cső, a worker módjai). Bizonyító erő: egység/mock.
- `test_app.py`: offscreen GUI-tesztek (indítási és leállítási stabilitás, a GRUB elérhetőségének vizsgálata, az indítási mód választója és az általa adott worker-argumentumok, az ellenőrzés jelölőnégyzete és a módgombok).
- `test_ui_helpers.py`: a tiszta GUI-segédfüggvények (eltelt idő, ablakprofilok).
- `test_desktop_polkit.py`: a pkexec 126/127-es kilépési kódjainak kezelése a grafikus felületen anélkül, hogy a `pkexec`-en (a rögzített wrapperrel) és az `lsblk`-n kívül bármi más folyamat indulna; a polkit-akció és a wrapper változatlansága (rögzített hash-ek); a `.desktop` fájl (szabványos kulcsok, `desktop-file-validate`).
- `test_packaging.py`: a telepítő, a polkit-akció hatóköre és a root wrapper, az egyetlen verziószám-forrás, a dokumentált tesztparancsok a CI-hez képest, hogy a CI ne lehessen sikeres az integrációs vagy az egységteszt-lépés kihagyásával, hogy a lenti GUI-minőségi tesztkészletek felderítésre kerülnek, hogy minden tesztmodul le van írva itt, és hogy a telepítő minden helyi modult telepít, amely a grafikus felülethez kell, de tesztsegédet nem. Ellenőrzi a projektdokumentumokat is: a nyilvános `ROADMAP.md`, a belső `docs/progress.md` és a `docs/history/` alatti lezárt kiadási szakaszok léteznek, a `ROADMAP.md` és a `docs/progress.md` nem hivatkozik a repón kívüli fájlra (`roadmap/`), és a gyökér és a `docs/` Markdown-fájljaiban minden relatív hivatkozás és horgony érvényes (a külső `http`/`https` hivatkozásokat nem ellenőrzi, hálózat nem kell; a kódblokkokat kihagyja). A kétnyelvű dokumentumok (`BilingualDocumentTests`): a README, a CONTRIBUTING, a ROADMAP és a `docs/TESTING` angolul és magyarul (`.hu.md`) is létezik, mindegyik változat a nyelvválasztó sorával kezdődik, a két változat fejléceinek szintje, a kódblokkjai és a relatív hivatkozásainak célpontjai azonosak (a `.hu` jelzőt figyelmen kívül hagyva), és a magyar változatok a magyar párokra hivatkoznak; a tesztparancsokat, a futási függőségeket, minden tesztmodult, a minimális ablakméretet, a csak olvasó kézi QEMU-próbát és a verziót mindkét nyelvi változatban ellenőrzi, ahol az angolban is.
- `test_messages.py`: a worker üzenetazonosítói (`docs/MESSAGES.md`): minden `emit()` hívás AST-alapú pásztázása, az `emit()` kimenete az új mezőkkel és nélkülük, a hat writer-futás minden eseményének azonosítói és argumentumai megszakításkor és hibánál is, és hogy a grafikus felület figyelmen kívül hagyja az új mezőket.
- `test_writer_fingerprint.py`, `test_theme.py`, `test_layout.py`, `test_i18n.py`: lásd a következő részt.

A CI-ben az egységteszt-lépés elbukik, ha bármely teszt kimarad (`OK (skipped=…)`), így egy hiányzó program vagy betűtípus nem gyengítheti csendben a GUI-, elrendezési vagy csomagolási ellenőrzéseket. A CI a shell-szkripteket is ellenőrzi:

```bash
shellcheck -S warning install.sh uninstall.sh bootmediakit-worker
```

### Writer-ujjlenyomat, téma-, elrendezés- és pseudo-locale-tesztek (0.4.0)

Mind a szokásos `unittest discover -s tests` futásban, root nélkül futnak.

- **Writer-ujjlenyomatok (`tests/test_writer_fingerprint.py`):** minden befagyasztott writer a `worker.main()`-en át, fájlokra, hamis parancsfuttatóval fut; a normalizált idővonalnak egyeznie kell a `tests/fixtures/writer_fingerprints/` tartalmával. Golden fájl módosítása előtt lásd a `docs/INVARIANTS.md` A6 pontját; a `BMK_UPDATE_WRITER_FINGERPRINTS=1` újraírja őket, és szándékosan elbukik. Bizonyító erő: egység/mock.
- **Téma (`tests/test_theme.py`):** minden színtoken-pár kontrasztja (szövegnél 4,5:1, nagy szövegnél és jelzőknél 3:1) világos, sötét, nagy kontrasztú és asztali környezetekhez hasonló palettákon; a rendszerfelismerés, a sötét tartalék, a gyorsváltó és a `QSettings`-be mentett állapota (ideiglenes fájlban, soha nem a felhasználó beállításaiban); a fix világos paletta egyezik a Fusion világos palettájával, és sötét Qt-színséma mellett is világos marad (KDE-szerű és adw-gtk3-dark-szerű asztalokon); a váltási mátrix (`ThemeSwitchMatrixTests`): minden módpár mindkét irányban, világos, Breeze-szerű sötét és adw-gtk3-dark-szerű rendszeren, DejaVu Sans és Noto Sans betűtípussal ugyanazt az ablakot adja, mint egy friss indítás (képernyőkép, minden widget palettája, stíluslap, tooltip), futás közbeni rendszersémaváltás után is; minden váltáskor minden widget újra-polisholódik; a Qt színséma-felülírása soha nem hívódik; a sötét KDE-szerű asztalon az eredmény változatlan. A rendszerpaletták szimuláltak; a valódi gtk3 és KDE platformtémákat kézzel ellenőriztük offscreen (`QT_QPA_PLATFORMTHEME=gtk3` az adw-gtk3 6.5-tel és elkülönített GNOME-beállításokkal, `QT_QPA_PLATFORMTHEME=kde`), a CI-ben nem.
- **Elrendezés (`tests/test_layout.py`):** offscreen ablakok a minimális méreten, valamint 1024×600, 1280×720 és 1366×700 logikai képponton, 9 és 10 pontos betűvel, minden látható állapotban (`UI_STATES`: RAW, Windows ISO nélkül, Windows UEFI, Windows Legacy, a „Legacy nem elérhető” súgóval és anélkül), a valódi kliensméret ellenőrzésével: nincs görgetősáv a fő felületen, egyetlen látható gomb, címke vagy legördülő lista szövege sem vágódik le (`cut_off_texts`; az elidált címkék kivételek), minden fontos vezérlő látható, a nézetablakon belül van, és nem fed le másikat; a napló belül görget; a minimum alatt (és 14 pontos betűvel a minimumon) a felület görget, és minden vezérlő továbbra is a látható részbe görgethető; egy `QT_SCALE_FACTOR=1.25`-ös futás ugyanazt a logikai eredményt adja.
- **Fordítható szövegek és pseudo-locale (`tests/test_i18n.py`, segédek: `tests/text_scan.py` és `tests/pseudo_locale.py`):** az `app.py`, a `theme.py` és a `ui_helpers.py` AST-alapú pásztázása elbukik minden olyan felhasználónak látható szövegliterálon, amely nincs `tr()`-ben, kivéve a 0.4.0 előtti szövegeket, amelyeket a `tests/fixtures/legacy_untranslated_texts.json` sorol fel (142 szöveg, a lista készítésekor 145; a lista csak rövidülhet, a 0.8.0 alakítja át őket); minden `tr()` argumentumnak egyszerű literálnak kell lennie. A pseudo-locale minden szöveget kb. 40%-kal hosszabbá tesz ékezetes betűkkel, a `tr()` szövegeknél egy `QTranslator`-on át, a régebbi szövegeknél a widgeteken lecserélve, a jelöléseket és a `{helyőrzőket}` megtartva. Ezzel minden UI-állapotban, 9 és 10 pontos betűvel: 1024×600-tól fölfelé nincs görgetősáv a fő felületen, és a teljes elrendezési ellenőrzés sikeres; a 880×550-es minimumon a két oszlop megmarad, nincs vízszintes görgetősáv és nincs átfedés, és minden fontos vezérlő teljesen a látható részbe görgethető (ott a függőleges tartalék görgetés megengedett; jóváhagyott eltérés, lásd `docs/history/0.4.0.md`). A pseudo-locale szándékos túlzás, nem fordítás.
- **A célállapot a worker befejeződése után (`tests/test_target_state.py`):** fail-closed (INVARIANTS B3). A hat writer-futás eseménysorrendje a writer-ujjlenyomat golden fájlokból jön (csak olvasva); a worker minden esemény után (118 ponton) ötféleképpen ér véget (SIGINT, SIGKILL vagy SIGTERM jellel leállítva, 1-es vagy 130-as kilépés záró esemény nélkül): a grafikus felület soha nem mondja, hogy a célmeghajtó nem változott, és mindig az „ismeretlen, részleges lehet” szöveget mutatja (`gui.result.target_unknown`), akkor is, ha a RAW writer a `wipefs` alatt áll le, amelynek eseménye még `target_modified: false`-t mond. Egy záró eseményt (megszakítva vagy hiba) szabályos kilépéssel mindkét irányban elfogad; ha utána összeomlik, nem; egy el sem indult worker „érintetlen”; a siker siker marad. A `docs/MESSAGES.md` GUI-szövegazonosítóinak és a `gui_text()`-nek egyezniük kell. Bizonyító erő: egység (offscreen GUI, események a golden fájlokból, worker-folyamat nélkül).
- **Ctrl+C a terminálban (`tests/test_terminal_interrupt.py`):** a valódi `main()` külön Python-folyamatban fut, a pkexec helyén egy shell-lel: az kiír egy jelszókérést, majd a grafikus felület és a shell együtt kap SIGINT-et, mint egy terminál folyamatcsoportja. A programnak SIGSEGV és `KeyboardInterrupt` traceback nélkül 130-cal kell kilépnie, a `finished` slotnak le kell futnia, a shellnek SIGINT-re le kell állnia, és párbeszédablak nem nyílhat; akkor is, ha az ablakot ugyanabban a pillanatban bezárják, és futó művelet nélkül is. A SIGINT-kezelő csak egy jelzőt állít, és egy időzítő ezt a megerősített bezárás útján dolgozza fel. Művelet közbeni Ctrl+C után egy sor kerül a terminálra (stderr), amely nem mond többet a grafikus felület fail-closed célállapotánál: a jelszókérésnél a worker el sem indult („a célmeghajtóhoz nem nyúltunk”), ha a worker elindult, de záró esemény nem jött: „A célmeghajtó részleges állapotban maradhat.”; művelet nélkül semmi nem íródik ki. Bizonyító erő: offscreen Qt valódi gyerekfolyamattal és valódi jelekkel; nem polkit-ügynök és nem valódi pkexec.
- **Tördelődő jelölőnégyzet (`tests/test_app.py`):** az ellenőrzési lehetőség egy szöveg nélküli `QCheckBox` egy tördelődő társcímkével: a címkére kattintás átváltja és a jelölőnégyzetre teszi a fókuszt, a szóköz a jelölőnégyzeten működik, az akadálymentes név mindkét módban a teljes szöveg, a letiltott jelölőnégyzet a címkét is letiltja (a letiltott szöveg színe a panelhez képest legalább 3:1 a világos és a sötét palettán), és a beállítás továbbra is eljut a worker argumentumáig.

A minimális ablakméretet, a 880×550 logikai képpontot (`MIN_WINDOW_WIDTH`/`MIN_WINDOW_HEIGHT` az `app.py`-ban) offscreen mértük a kétoszlopos elrendezésre 880 px szélességben, az ablak minden látható állapotában: RAW, Windows felismert ISO nélkül, Windows UEFI, Windows Legacy, RAW és Windows a „Legacy nem elérhető” súgóval, mindig a látható veszélyre figyelmeztető szöveggel. A T5-ben szűkített kompakt térközökkel legfeljebb 524 px magasság kell nekik 9 és 10 pontos betűvel (Noto Sans 524 px, DejaVu Sans 514 px); a változtatás előtt 548 px. Az első értéket, a 880×540-et, csak az indítási állapotban mértük; módváltás után ezen a méreten a felület görgetett. Az elrendezési tesztek mindezekben az állapotokban futnak (`UI_STATES` a `tests/test_layout.py`-ban), és az ablak valódi kliensméretét ellenőrzik. A 880×550 elfér egy 1280×800-as kijelzőn 125%-os skálázásnál (1024×640 logikai) egy 44 px-es panellel és egy 40 px-es ablakkerettel (legfeljebb 556 px), így csak 6 px marad; ezért az asztali ellenőrzések KDE Plasma és XFCE alatt mérik. Az offscreen mérések a gép betűtípusaitól függenek: az elrendezési és pseudo-locale-tesztek ezért DejaVu Sans (szélesebb; ezzel a T5 CI-hibája pontosan reprodukálható volt) és Noto Sans betűtípussal futnak; mindkettőnek telepítve kell lennie (Ubuntu: `fonts-dejavu-core`, `fonts-noto-core`, `fontconfig`; Arch: `ttf-dejavu`, `noto-fonts`), és a hiányuk hiba, nem kihagyás; a CI telepíti és ellenőrzi őket. Az asztali ellenőrzések rögzítik a Qt logikai munkaterületét, az asztali környezetet, a Qt/PySide6 verzióját, az X11/Wayland munkamenetet, a témát és a skálázást. Waylandon a Qt nem ismeri a paneleket: a `QScreen.availableGeometry()` a teljes kimenet (a karbantartó GNOME 51.1 alatt, a fejlesztői gépen KDE Plasma alatt mérte). Ilyenkor az ablak `WAYLAND_PANEL_RESERVE` = 60 logikai képpontnyi magasságot szabadon hagy (`ui_helpers.py`). Ez 48 px volt (a KDE Plasma alapértelmezett 44 px-es panelje + 4 px, becslés); 60 px lett, miután a karbantartó KDE-naplója megmutatta, hogy a KWin 58 px-et tart szabadon (`configure_bounds`, lásd lent), a karbantartó jóváhagyásával. A GNOME felső sávját is fedi (a karbantartó naplójában kb. 32 px); más asztali környezetekre és panelméretekre ez továbbra is becslés. Offscreen mérve egy 1020×576 logikai kimeneten (GNOME 133%-on), minden UI-állapotban, DejaVu Sans és Noto Sans betűtípussal, 9 és 10 ponton, a valódi kliensméreten: keret nélkül (kliens 1020×516) a kétoszlopos elrendezés megmarad, és legfeljebb 8 px-et görget (Noto Sans 9 pt; Noto Sans 10 pt-tal 1 px, DejaVu Sans-szal semennyit); a VM 33 px-es keretével (kliens 987×483) legfeljebb 7 px-et görget DejaVu Sans 9 pt-tal, 31 px-et DejaVu Sans 10 pt-tal, 41 px-et Noto Sans 9 pt-tal és 34 px-et Noto Sans 10 pt-tal (48 px-es ráhagyással: semennyit, 19, 29 és 22 px-et). Egyetlen szöveg sem vágódik le, nincs vízszintes görgetősáv. KDE Plasma alatt 1280×720-on (kliens 1280×660) és 120%-on (1067×540) egyik betűtípussal sincs görgetés. A karbantartó elfogadta a többletgörgetést GNOME alatt 133%-on. A tesztek (`WaylandScaleChangeTests`, `UsableWorkAreaTests` a `tests/test_layout.py`-ban) a `QScreen` helyettesítésével szimulálják a képernyőt, és a valódi jeleket küldik; a valódi compositor válaszát a karbantartó ellenőrzi.

### Asztali tesztmátrix (0.4.0)

A grafikus felületnek ugyanúgy kell működnie KDE Plasma, GNOME, XFCE, Cinnamon, MATE, LXQt és más Qt-képes munkamenetek alatt. A writer nem függ az asztali környezettől, ezért egy asztali környezethez nem kell teljes írási regresszió; a `docs/REGRESSION_CHECKLIST.md` kötelező pontjai kiadás előtt a fő gépen futnak. Itt csak a karbantartó által jelentett eredmények szerepelnek; minden más „nem tesztelt”.

Minden ellenőrzésnél rögzítendő: az asztali környezet és verziója, a disztribúció, a Qt és a PySide6 verziója, X11 vagy Wayland, a téma (világos, sötét, nagy kontraszt), a kijelző felbontása és skálázása, a Qt logikai munkaterülete és a rendszer-betűtípus. A logikai munkaterület és a betűtípus root nélkül:

```bash
python3 -c 'from PySide6.QtWidgets import QApplication; a=QApplication([]); s=a.primaryScreen(); print(s.availableGeometry(), s.devicePixelRatio(), a.font().family(), a.font().pointSizeF())'
```

Mit kell ellenőrizni: a színeket és az automatikus világos/sötét követést, a nap/hold váltót és a „Rendszer / Automatikus” visszaállítását, a polkit-ablakot, a fájlválasztót, az ikont az ablakon, a tálcán, a menüben és az ablakváltóban, valamint 1280×800 és 1366×768 felbontáson 100% és 125% skálázással, hogy nincs görgetősáv a fő felületen (150% és 200% skálázással és nagyobb betűmérettel: semmi nem vágódik le és nem takar el mást); a 880×550-es minimumot KDE Plasma és XFCE alatt (1280×800-on 125%-on csak 6 px tartalék); indítás után: az ablak átvitelét kisebb monitorra, a laptop leválasztását a dokkolóról, és a felbontás vagy a skálázás váltását futás közben: az ablak a képernyőn belül marad, az „USB elkészítése” és a „Megszakítás” elérhető marad.

| Asztali környezet | Téma | Munkamenet | Állapot |
|---|---|---|---|
| KDE Plasma (CachyOS, fő gép) | világos és sötét | Wayland | jelentve: élő témaváltás (világos, sötét, automatikus, kézi világos a sötét asztalon), felbontás- és skálaváltás, az ablak átvitele a kisebb monitorra, 1280×800 és 1366×768 100% és 125% skálázással, a 880×550-es minimum 1280×800-on 125%-on (a munkaterület és a keret nincs rögzítve), polkit-ablak, fájlválasztó, ikonok; 150% és 200% nagyobb betűmérettel, a GRUB nélküli állapot (a Legacy tiltva, GRUB-bal újra elérhető) és egy monitor kihúzása futás közben (a karbantartó tesztelési táblázata, 2026-11-27). Rögzítve (2026-11-27, a fő gépen, a karbantartó kérésére): Plasma 6.8.3 (KWin 6.8.3, KDE Frameworks 6.32), Breeze Dark, polkit-ügynök: polkit-kde, rendszer-betűtípus Noto Sans 10 pt, Qt-színséma sötét, két kimenet, 2560×1440 és 1920×1080, amelyek Qt-munkaterülete a teljes kimenet; Plasma X11-munkamenet nincs telepítve. A 880×550-es minimum: a DP-1 monitor 1280×800-at nem kínál, ezért a szigorúbb 1280×720-on 125%-on (1024×576 logikai) ellenőrizve: az ablak elfér, görgetősáv nincs; ehhez a beállításhoz a munkaterület és a keret nincs rögzítve (a karbantartó jelentése, 2026-11-27). A `docs/REGRESSION_CHECKLIST.md` írási tesztjei: jelentve (lásd lent). Függőben: a megmaradó pixelérték |
| GNOME, GTK-téma: `adw-gtk3-dark` | automatikus (`color-scheme` default / prefer-dark / prefer-light), kézi világos és sötét | csak Wayland (a VM-beli GNOME-nak nincs X11-munkamenete) | jelentve: az automatikus mód `color-scheme` default, prefer-dark és prefer-light beállítással a várt módon, a kézi és az automatikus mód közti váltás minden párosításban, a futás közbeni skálaváltás 1360×768-on (100% → 133%); megszakítás a jelszókérés alatt: GNOME-on nem alkalmazható, az ügynök ablaka modális, ezért a Megszakítás és a bezárás a jelszókérés alatt nem nyomható (a karbantartó jóváhagyta, 2026-11-27); a jó jelszavas ágat XFCE-n mértük; a polkit-ablak, a fájlválasztó és az ikon a dokkban és az áttekintőben: jelentve (a karbantartó tesztelési táblázata, 2026-11-27). Rögzítve (2026-11-27, `6f83a86`): GNOME Shell 51.1, GTK-téma a rögzítéskor `adw-gtk3-dark`, `color-scheme` prefer-dark, rendszer-betűtípus Adwaita Sans 11 pt, Qt-munkaterület 1964×1103 (a teljes kimenet), Qt-színséma sötét; az információs szkript nem talált külön polkit-ügynök-folyamatot |
| GNOME, GTK-téma: `Adwaita` | automatikus (`color-scheme` default / prefer-dark / prefer-light), kézi világos és sötét | csak Wayland (a VM-beli GNOME-nak nincs X11-munkamenete) | jelentve: az automatikus mód `color-scheme` default, prefer-dark és prefer-light beállítással a várt módon, a kézi és az automatikus mód közti váltás minden párosításban, a futás közbeni skálaváltás 1360×768-on (100% → 133%); megszakítás a jelszókérés alatt: GNOME-on nem alkalmazható, az ügynök ablaka modális, ezért a Megszakítás és a bezárás a jelszókérés alatt nem nyomható (a karbantartó jóváhagyta, 2026-11-27); a jó jelszavas ágat XFCE-n mértük; a polkit-ablak, a fájlválasztó és az ikon a dokkban és az áttekintőben: jelentve (a karbantartó tesztelési táblázata, 2026-11-27). Rögzítve (2026-11-27, `6f83a86`): GNOME Shell 51.1, GTK-téma a rögzítéskor `adw-gtk3-dark`, `color-scheme` prefer-dark, rendszer-betűtípus Adwaita Sans 11 pt, Qt-munkaterület 1964×1103 (a teljes kimenet), Qt-színséma sötét; az információs szkript nem talált külön polkit-ügynök-folyamatot |
| XFCE 4.20 (xfce4-session 4.20.4), VM | világos és sötét (GTK-téma: `adw-gtk3-dark`) | X11 | jelentve (a karbantartó tesztelési táblázata, 2026-11-27): indítás és polkit-jelszókérés, világos és sötét rendszertéma automatikus módban, kézi világos/sötét és vissza automatikusra, fájlválasztó és ikonok, 1280×800 és 1366×768 100% és 125% skálázással görgetősáv nélkül, a 880×550-es minimum 1024×640 logikai képponton (az 1280×800 125%-on vett logikai mérete; mérve: munkaterület 1024×613, ablak 880×550, keret 890×584, 29 px tartalék, görgetősáv nincs), felbontásváltás futás közben; Megszakítás a jelszókérés alatt a grafikus ügynökkel, majd Mégse, majd a jó jelszó (lásd lent). Rögzítve: polkit-ügynök: polkit-gnome, rendszer-betűtípus Sans 10 pt, Qt-munkaterület 1920×1053 1920×1080-on (y = 27), Qt-színséma sötét |
| Cinnamon 6.8.2, VM | világos és sötét (GTK-téma a rögzítéskor: `Adwaita`) | X11 | jelentve (a karbantartó tesztelési táblázata, 2026-11-27): indítás és polkit-jelszókérés, világos és sötét rendszertéma automatikus módban, kézi világos/sötét és vissza automatikusra, fájlválasztó és ikonok, 1280×800 és 1366×768 100% és 125% skálázással görgetősáv nélkül, felbontásváltás futás közben. Rögzítve: rendszer-betűtípus Adwaita Sans 11 pt, Qt-munkaterület 1964×1063 1964×1103-on, Qt-színséma világos; az információs szkript nem talált külön polkit-ügynök-folyamatot (a jelszókérés megjelent) |
| LXQt | a rendszer alapértelmezése | nincs rögzítve | jelentve (a karbantartó tesztelési táblázata, 2026-11-26): indítás és polkit-jelszókérés, világos és sötét rendszertéma automatikus módban, kézi világos/sötét és vissza automatikusra, fájlválasztó és ikonok, 1280×800 és 1366×768 100% és 125% skálázással görgetősáv nélkül, felbontásváltás futás közben; rögzítve: rendszer-betűtípus DejaVu LGC Sans 12 pt, Qt-munkaterület 1920×1048 |
| MATE 1.28 (mate-session 1.28.2), VM | világos és sötét (GTK-téma a rögzítéskor: `BlackMATE`) | X11 | jelentve (a karbantartó tesztelési táblázata, 2026-11-27): indítás és polkit-jelszókérés, világos és sötét rendszertéma automatikus módban, kézi világos/sötét és vissza automatikusra, fájlválasztó és ikonok, 1280×800 és 1366×768 100% és 125% skálázással görgetősáv nélkül, felbontásváltás futás közben. Rögzítve: polkit-ügynök: polkit-mate, rendszer-betűtípus Sans 10 pt, Qt-munkaterület 1920×1029 1920×1080-on (y = 26), Qt-színséma sötét |
| Openbox, polkit-ügynök nélkül (VM, SDDM-en át) | a rendszer alapértelmezése | X11 | jelentve: érthető hibaablakok, a megszakítás és a bezárás szövegei a jelszókérés alatt, a Ctrl+C összeomlás nélkül kezelve, kilépési kód 130 (mérve 2026-11-27-én; az ablak egyidejű bezárása nem mért); a pkexec szöveges ügynöke a jó jelszóval is elbukik (upstream polkit-hiba, lásd lent) |

A karbantartó jelentése, 2026-11-25, KDE Plasma, Wayland, CachyOS, `dev/0.4.0` a T5 változásai előtt:

- 32"-os 2K monitor 100% és 130% skálázással: az ablak dinamikusan méreteződik, nincs görgetősáv a fő felületen; 130%-on az egyoszlopos elrendezés is elfér.
- 22"-os 1920×1080-as monitor 100%-on: működik; 120%-on az elrendezés két oszlopra vált; 120%-on és 130%-on nincs görgetősáv a fő felületen.
- Hiba: a nap/hold gomb menüjének nyila eltakarta az ikont. Javítva (`f4f898c`); az asztalon még nincs újraellenőrizve.
- Nincs rögzítve: a Plasma, a Qt és a PySide6 verziója, a logikai munkaterület, a rendszer-betűtípus.
- A fő gépen még nem tesztelt: a kézi világos mód a sötét KDE-asztalon (a régi kóddal a Fusion sötét palettáját mutatta, offscreen mérve a KDE platformtémával; javítva: `20a7d98`), utána vissza automatikusra és sötétre, minden irányban.
- Még nem tesztelt: laptopkijelző (1280×800, 1366×768), a 880×550-es minimum KDE Plasma és XFCE alatt, monitor-, dokkoló-, felbontás- vagy skálaváltás futás közben, a többi asztali környezet, polkit-ügynök nélküli munkamenet, az automatikus témakövetés és a rendszermód visszaállítása, valamint az elrendezés a T5 változásai után (szűkebb kompakt térközök, tördelődő módgombok és jelölőnégyzet).

A karbantartó jelentése, 2026-11-25, GNOME 51.1, Wayland, CachyOS VirtualBoxban, `dev/0.4.0` a `55a212d`-n, 1280×800-on (100% és 125%), 1366×768-on (133%) és 1920×1080-on (125%):

- `adw-gtk3-dark` GTK-témával és `prefer-light` `color-scheme`-mel a Qt `ColorScheme.Dark`-ot jelez (a `QT_QPA_PLATFORMTHEME` üres, a platform `wayland`), így az automatikus mód sötét, miközben a GNOME saját beállításai és a libadwaita alkalmazások világosak. `Adwaita` GTK-témával a Qt azonnal `Light`-ot jelez, és az ablak futás közben világosra vált, `adw-gtk3-dark`-kal pedig vissza sötétre; mindkettő helyesnek látszott. A Qt itt a GTK-téma nevét követi, nem a GNOME `color-scheme` beállítását (nyitott A-észrevétel).
- A kézi „Sötét” és a „Rendszer / Automatikus” közti váltás, miközben az automatikus mód is sötét, keveri a színeket: a szövegszínek megváltoznak, az ablak- és panelszínek nem, és a szöveg nehezen olvasható. A többi váltás (automatikus világos ↔ automatikus sötét, kézi világos ↔ sötét) helyes volt (nyitott B-észrevétel).
- 1366×768-on 133%-on a futás közbeni skálaváltás után az ablak alja (a gombsor) a képernyőn kívül marad; újraindítás után elfér. A futás közbeni skálaváltás 1280×800-on (100% / 125%) és 1920×1080-on (125%) helyes volt (nyitott C-észrevétel).
- A javítások után újratesztelendő: mindkét GTK-téma, az automatikus mód `color-scheme` default, prefer-dark és prefer-light beállítással, minden kézi/automatikus váltási pár, és a futás közbeni skálaváltás.
- Az azóta készült, GNOME-on még újra nem tesztelt javítások (a B-észrevétel nyitva marad, amíg a karbantartó nem jelent): a kézi világos mód sötét Qt-színséma mellett is világos (`20a7d98`), és a megjelenés minden váltáskor egyetlen úton és teljesen alkalmazódik, a Qt színséma-felülírása nélkül (`a031391`). Az A-észrevétel dokumentált korlátként marad (README-k). A C-észrevétel: a diagnosztikai napló szerint minden jel megérkezik, de Waylandon a Qt a teljes 1020×576-os kimenetet adja munkaterületnek; a Wayland-ráhagyás javítja (lásd fent), GNOME és KDE alatt még nincs újratesztelve.

A karbantartó jelentése, 2026-11-26, KDE Plasma, Wayland, CachyOS (fő gép), `dev/0.4.0` (a commit nincs rögzítve), 1440p-n, 1080p-n, 1280×960-on és 1280×720-on, mindegyiken 100% és 120% skálázással:

- A rendszertéma váltása Breeze és Breeze Dark között futás közben: automatikus módban az ablak azonnal követi.
- Kézi váltások a programon belül: nincs színkeveredés és rajzolási hiba.
- Kézi módban a rendszertéma váltása csak az ablakkeretet színezi át (ezt az asztali környezet rajzolja); a program kézi módban marad. Ez a várt viselkedés.
- Észrevétel: 1280×720-on 120%-on (kb. 1067×600 logikai) az ablak alja kicsit levágódik; a gombok láthatók és kattinthatók, görgetősáv nem jelent meg. A karbantartó kozmetikainak tartja, mert a gombok használhatók; 1280×800-on helyes. Az elemzés nyitott (`docs/history/0.4.0.md`).
- Külön nem jelentve: az egyes váltási irányok (például kézi „Világos” a sötét asztalon, majd vissza automatikusra és sötétre), a futás közbeni skálaváltás, a Plasma, a Qt és a PySide6 verziója és a rendszer-betűtípus.
- Válasz egy kérdésre, ugyanazon a napon: a kicsit levágott alsó rész rögtön az indítás után látszik 1280×720-on 120%-on; a karbantartót nem zavarja, és nem számít arra, hogy bárki ilyen kis felbontást használna ezzel a skálázással. A felbontás vagy a skálázás futás közbeni váltása után az ablak egyoszlopos elrendezésben marad, és a teljes alja hiányzik.

A karbantartó diagnosztikai naplói, 2026-11-26, ugyanaz a gép (egy repón kívüli diagnosztikai szkript: a program saját átméretezési hívásai a hívóikkal, minden átméretezési esemény a méretével, és `WAYLAND_DEBUG=1`):

- Váltás futás közben, 2560×1440 → 1280×720 (a skálázás 100% marad) és 100% → 120%: a KWin `xdg_toplevel.configure(880, 900)`-t küld, a váltás előtti méretet, ugyanabban a kötegben, mint a kimenet változását (`wl_output.mode`, `scale`), új `configure_bounds` nélkül. A program előbb igazítja az ablakot (`adapt_to_screen`: 880×672, majd 880×552); 1 ms-mal később a Qt alkalmazza a sorban álló configure-t (`ack_configure`, egy spontán átméretezési esemény 672 → 900, 552 → 900). A program közben nem hívott átméretezést, és további jelet sem kap, így az ablak 900 px magas maradt egy 720, illetve 600 px-es kimeneten, a gombok a képernyőn kívül. A 900-at nem a kódunk okozta, hanem a compositor. A méretőr javítja (`COMPOSITOR_RESIZE_GUARD_MS`, `COMPOSITOR_RESIZE_CORRECTIONS` az `app.py`-ban; `CompositorRestoresSizeTests` a `tests/test_layout.py`-ban): Waylandon az ablak megváltozott munkaterülethez igazítása után 2 másodpercig (minden javítás után újraindítva) a nem a programtól jövő, a munkaterületnél nagyobb átméretezést visszacsinálja, váltásonként legfeljebb kétszer; egy kívülről jövő, beleférő átméretezés lezárja a figyelést; a maximalizált és a teljes képernyős ablakot, a felhasználó későbbi átméretezéseit és az X11-et nem érinti. A 2 másodperces korlát kb. 2000-szerese a mért késésnek, és helyet hagy egy lassú vagy terhelt gépnek (VM). Az asztalon még nincs újratesztelve.
- Indítás 1280×720-on 120%-on: a KWin `configure_bounds(1067, 542)`-t küld `configure(0, 0)`-val, és a Qt maga korlátozza az ablakot 960×542-re, a 880×550-es minimum alá. 2560×1440-en indítva a korlát 2560×1382 volt. A KWin tehát ezen a gépen 58 logikai képpontnyi magasságot tart szabadon (a kimenet magassága mínusz a korlát); a program Wayland-ráhagyása (`WAYLAND_PANEL_RESERVE`) 48 px. A KWin a korlátot csak induláskor küldi el, futás közbeni váltás után nem, így ott a ráhagyás becslés marad.
- A javítás után megmaradó különbség (a kódból és a naplózott értékekből számolva, az asztalon nem mérve): induláskor nincs, a Qt követi a KWin korlátját. Futás közbeni váltás után az ablak a 48 px-es ráhagyással a használható területhez igazodott: kliensmagasság 672 1280×720-on és 552 1067×600-on (KDE Waylandon a Qt a szerveroldali dekorációhoz nem jelez keretet), 10 px-szel több a KWin korlátjánál (662 és 542). A 60 px-es ráhagyással (lent) 660 és 540, 2 px-szel kevesebb a KWin korlátjánál (számolva). Az asztalon a karbantartó azt jelentette, hogy 1280×720-on 120%-on az ablak alja teljesen látszik, induláskor és futás közbeni váltás után is; magát a megmaradó pixelértéket KDE alatt nem mérte, és GNOME alatt 1360×768-on 133%-on sem.

A karbantartó újratesztelése 2026-11-26-án a méretőr (`741d0d4`) után: KDE Plasma (Wayland) alatt a felbontás- és skálaváltás futás közben (2560×1440 → 1280×720, majd 100% → 120%) és GNOME (Wayland, 1360×768, 100% → 133% futás közben, majd újraindítás) alatt az ablak helyes; KDE alatt csak a ráhagyásból adódó néhány pixel hiányzik alul. A karbantartó jóváhagyta a ráhagyás 60 px-re emelését, elfogadva egy görgetősávot GNOME alatt 133%-on ablakkerettel.

A karbantartó jelentése 2026-11-26-án, a ráhagyás 60 px-re emelése (`33f7bc5`) után: KDE Plasma (Wayland) alatt 1280×720-on 120%-on az ablak alja minden esetben teljesen látszik, induláskor és futás közbeni váltás után is.

A karbantartó jelentése 2026-11-26-án, GNOME a VM-ben, az egyutas megjelenés-javítás (`a031391`) után: a színmódok váltása egyik esetben sem keveri a színeket; a B-észrevétel lezárva. Külön nem jelentve: mely GTK-témákkal és `color-scheme` beállításokkal.

A karbantartó jelentése 2026-11-26-án, Openbox a VM-ben (polkit-ügynök nélkül; a pkexec saját szöveges ügynöke a terminálban kérdez), a program terminálból indítva:

- Ctrl+C a jelszókérésnél: nincs összeomlás; a terminálsor megjelent. A kilépési kódot nem mérte.
- A Megszakítás gomb és az ablak X-e a jelszókérés alatt: megjelenik a „Megszakítás kérve; a hitelesítés után érvényesül.” státuszsor és a „Megszakítás folyamatban…” gombfelirat; az ablak nyitva marad, amíg a jelszólépés véget nem ér (a jóváhagyott A terv).
- Rossz jelszó függő megszakítás nélkül: megjelenik az „A hitelesítés nem sikerült” ablak (pkexec 127, a célmeghajtó nem változott); a program nem lép ki csendben.
- Az ablak bezárása vagy a Megszakítás a jelszókérés alatt: a megerősítés megjelent; függő megszakítással és rossz jelszóval, valamint függő megszakítással és jó jelszóval a program hibaablakot mutatott, és a pendrive változatlan maradt (`lsblk -f`: az `sdb1` továbbra is a korábbi Linux Mint ISO, `iso9660`). Polkit-ügynök nélküli indításkor érthető hibaablak jelent meg.
- Környezeti észrevétel, nem programhiba: ebben a VM-ben (Openbox SDDM-en át, grafikus polkit-ügynök nélkül, aktív logind munkamenettel) a pkexec saját szöveges ügynöke a jó jelszóval a program nélkül is elbukik: a sima `pkexec true` és a `pkexec true </dev/null` is „==== AUTHENTICATION FAILED ====” üzenettel és 127-es kilépési kóddal végződik, miközben a `sudo` ugyanazt a jelszót elfogadja, és a faillock-tábla üres. A naplóban `polkit-agent-helper-1: error response to PolicyKit daemon: ... No session for cookie` és a polkitd „FAILED to authenticate” üzenete áll; egy valóban rossz jelszónál ehelyett `pam_unix` hitelesítési hiba látszik. A karbantartó ezt a szöveges ügynök ismert upstream polkit-hibájaként azonosította (https://gitlab.freedesktop.org/polkit/polkit/issues/17). A korábbi „megszakítás és jó jelszó” hiba tehát semmit nem mond a megszakítás útjáról; a teljes ellenőrzés (Megszakítás a jelszókérés alatt, majd a jó jelszó: a worker a megszakításra leáll, 130-as kilépés) GNOME alatt, grafikus ügynökkel függőben. A program bezárási és megszakítási útja csak a `cancel` sort írja a pkexec szabványos bemenetére, és lezárja azt (a valódi ablakkal és a pkexec helyén egy shell-lel ellenőrizve: nincs terminate, kill vagy jel); a megszakítási protokoll változatlan.
- Ctrl+C: a 130-as kilépési kódot nem mérte.

A karbantartó jelentése 2026-11-27-én, a `docs/REGRESSION_CHECKLIST.md` írásai a fő gépen eldobható pendrive-okkal, telepített program: `6f83a86` (a programfájlok azóta nem változtak):

- Linux RAW, Linux Mint 22.3 XFCE ISO: a visszaolvasásos ellenőrzés lefutott; a pendrive UEFI és Legacy BIOS módban is elindul.
- Windows UEFI (GPT), Windows 11 26H2 ISO: az ellenőrzés lefutott; a pendrive elindul.
- Windows Legacy (MBR/BIOS), ugyanaz az ISO: az ellenőrzés lefutott; a pendrive Legacy/CSM módban elindul, és a karbantartó gépén UEFI módban is (a 0.3.0 óta ismert és dokumentált: NTFS-t olvasó firmware).
- Egy hibás pendrive-on, Linux RAW módban a Linux Mint ISO-val, az írás sikeres, és a visszaolvasásos ellenőrzés hibát jelez; ez a helyes viselkedés.
- A fő gép a tesztek után rendesen elindul (a saját rendszerbetöltője érintetlen).
- A `grub` csomag nélkül a Legacy érték a súgójával tiltva van, és a `grub` visszatelepítése után újra választható (5. pont).
- Nincs rögzítve: az `sfdisk -d`, a `wipefs` és az `lsblk` kimenete, hogy meddig jutott a Windows Setup, és hogy melyik gépen vagy firmware-en indult az egyes pendrive (a Legacy pendrive UEFI-s indítását kivéve).

A karbantartó jelentése 2026-11-27-én, KDE Plasma (Wayland), fő gép, telepített program: `6f83a86` (a repóval összevetve):

- 150% és 200% skálázás nagyobb betűmérettel: semmi nem vágódik le és nem takar el mást (tesztelési táblázat).
- A `grub` csomag nélkül a Legacy érték a súgójával tiltva van; a `grub` újratelepítése után választható (tesztelési táblázat; a REGRESSION_CHECKLIST 5. pontja, ennél a kiadásnál nem kötelező).
- Egy monitor kihúzása futás közben (a laptop dokkolóról való leválasztása helyett): az ablak egyben átkerült a másik monitorra; minden látszott és kattintható volt.
- A minimális méretet mérő szkript 1024×576 logikai képponton futott 2,0-s eszközpixel-aránnyal, nem 1280×800-on 125%-on (1024×640): Qt-munkaterület 1024×576 (a teljes kimenet), a program használható területe a 60 px-es Wayland-ráhagyással 1024×516, így a minimum ehhez igazodott, 880×516-ra; görgetősáv nincs a fő felületen; a keretet Waylandon a Qt nem ismeri. Az 1280×800-as, 125%-os mérés még hátravan.
- Ugyanaznap később: a DP-1 monitor nem kínál 1280×800-as módot, ezért a 880×550-es minimumot a szigorúbb 1280×720-on 125%-on (1024×576 logikai) ellenőrizte: az ablak elfér, görgetősáv nincs. Ehhez a beállításhoz a Qt-munkaterület és a kerettel mért méret nincs rögzítve; a szkript kimeneti fájlja ekkor újraíródott, de továbbra is 1024×576 logikai képpontot és 2,0-s, nem 1,25-ös eszközpixel-arányt mutat, ezért nem tekintjük ennek a mérésnek.
- Az egység- és offscreen GUI-tesztek (384, OK) és a rootként futó loop-eszközös integrációs tesztek (10, OK, egy sem kihagyva) a karbantartó gépén sikeresek voltak; a commitot nem adta meg, a programfájlok azonosak a `6f83a86`-tal (azóta nincs nem dokumentációs változás).

A karbantartó jelentése 2026-11-27-én, XFCE 4.20 (X11) a VM-ben, telepített program: `6f83a86`, a minimális méret mérése 1024×640 logikai képponton (eszközpixel-arány 1,0): Qt-munkaterület 1024×613 (+0+27, egy 27 px-es panel), az ablak a minimumon 880×550, kerettel 890×584 (bal 5, fent 29, jobb 5, lent 5), 29 px tartalék magasság, a keret a munkaterületen belül, görgetősáv nincs a fő felületen.

A karbantartó jelentése 2026-11-27-én, Openbox a VM-ben (polkit-ügynök nélkül), terminálból indítva, `bootmediakit; echo $status` formában:

- Ctrl+C a szöveges „Password:” jelszókérésnél: nincs összeomlás (korábban SIGSEGV), a kilépési kód 130 (az `echo $status` 130-at írt ki), és megjelent a „BootMediaKit: megszakítva (Ctrl+C). A háttérfolyamat nem indult el, a célmeghajtóhoz nem nyúltunk.” sor.
- Nem mért: az ablak bezárása a Ctrl+C-vel egy időben.
- Indításkor a kimenetben négyszer megjelent a „qt.svg.draw: The requested buffer size is too big, ignoring” üzenet. Ismert, kozmetikai figyelmeztetés, a kiadást nem akadályozza; az okát nem vizsgáltuk (alacsony prioritás, `docs/history/0.4.0.md`).

Az XFCE, a Cinnamon és a MATE sorában közös (a karbantartó tesztelési táblázatában lévő információs szkript, 2026-11-27): CachyOS VM-ben, kernel 7.3.6-1-cachyos, X11 (Qt-platform: `xcb`), PySide6 6.12.0, Qt 6.12.1, Python 3.14.10, eszközpixel-arány 1,0, `dev/0.4.0` a `b2811dc`-n, amikor a szkript futott; az egyes ellenőrzések skálázási és kijelzőértékei a táblázat soraiban vannak, itt nincsenek rögzítve.

A karbantartó jelentése 2026-11-27-én, XFCE 4.20 (X11) a VM-ben grafikus polkit-ügynökkel (polkit-gnome), a commit nincs rögzítve:

- Megszakítás a jelszókérés alatt, majd Mégse a polkit-ablakban: a pkexec 126-tal tér vissza („Request dismissed”); a program ezt írja: „A jelszókérő ablakot bezártad vagy megszakítottad, ezért a művelet nem indul el. A célmeghajtóhoz nem nyúlunk.”, a napló és a státuszsor a megszakítást mutatja, és megjelenik „A célmeghajtót nem módosítottuk.” Nincs összeomlás. Ez a várt viselkedés.
- Megszakítás a jelszókérés alatt, majd a jó jelszó: a lemez nem változott (a karbantartó ellenőrzése). Ez az az ág, amelyet ügynök nélkül a szöveges ügynök ismert polkit-hibája miatt nem lehetett mérni (lásd fent).
- Nem mért: a kilépési kód (130) és a worker pontos záró üzenete.
- **Egyetlen mérés, nem garancia:** a leállás a célmeghajtó módosítása előtt várható, de szigorúan nem garantált, mert a worker a `cancel` sort külön szálon olvassa (halasztva, `docs/history/0.4.0.md`).
- GNOME alatt a grafikus ügynök ablaka a jelszókérés alatt blokkolja a program ablakát (a karbantartó tesztelési táblázata): ott a Megszakítás és a bezárás nem nyomható; a jó jelszó elindítja a műveletet, a jelszókérés elutasítása a hitelesítési hiba ablakát mutatja, és semmi nem íródik ki. A karbantartó jóváhagyta (2026-11-27): a megszakítási próba GNOME-on nem alkalmazható; a jó jelszavas ágat XFCE-n mértük. A program szövegei és kódja nem változnak; a dokumentációs fázis (0.9.3) felhasználói útmutatója leírja (`docs/history/0.4.0.md`, halasztva).

### Loop-eszközös integrációs tesztek

A `tests/integration/` a valódi `worker.write_raw`, `worker.write_windows_uefi` és `worker.write_windows_bios` függvényt futtatja egy lemezképfájlra épülő loop-eszközre. Fizikai meghajtóhoz nem nyúl; minden tesztfájl egy privát tmpfs-en van, amelyet utána lecsatol.

```bash
sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

`BMK_QEMU=1` mellett a Legacy BIOS tesztek a kiírt lemezképet QEMU-ban SeaBIOS-szal el is indítják (ezt futtatja a CI):

```bash
sudo -E env BMK_INTEGRATION=1 BMK_QEMU=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

Kihagyási feltételek: minden integrációs teszt kimarad, hacsak nincs beállítva a `BMK_INTEGRATION=1`, a folyamat nem root, és nem érhető el a `losetup`, az `sfdisk`, a `wipefs`, az `mkfs.ext4`, az `mkfs.ntfs` és a `fatlabel`. Egy szokásos, nem root `unittest discover -s tests` futás nem lép be ebbe a könyvtárba. A CI beállítja a `BMK_INTEGRATION_REQUIRED=1`-et, amely a hiányzó előfeltételt hibává teszi, így a lépés nem lehet sikeres kihagyással.

A Legacy BIOS tesztekhez (`test_loop_windows_bios.py`) ezen felül a `grub-install` és a `/usr/lib/grub/i386-pc` könyvtár kell (Arch: `grub`; Debian/Ubuntu CI: `grub-pc-bin` és `grub2-common`); a writer-tesztekhez a `worker.WINDOWS_BIOS_PROGRAMS` minden programja is. A T0 tesztek ntfs-3g-s változatai kimaradnak, ha az `ntfs-3g` hiányzik. A QEMU-s indítási tesztek kimaradnak, hacsak nincs beállítva a `BMK_QEMU=1`; `BMK_QEMU=1` mellett a hiányzó `qemu-system-x86_64`/`qemu-system-i386` kihagyás, a `BMK_INTEGRATION_REQUIRED=1` alatt hiba.

Magának a workernek ezen felül az `lsblk`, a `blockdev`, a `findmnt`, az `udevadm`, a `partprobe`, a `blkid`, a `7z` és egy működő NTFS-csatolás (kernel `ntfs3` vagy `ntfs-3g`) kell; ha valamelyik hiányzik, az teszthibaként jelenik meg, nem kihagyásként.

Mit csinálnak a tesztek:

- **RAW (`test_loop_raw.py`):** egy 128 MiB-os, régi kétpartíciós GPT-t (az első partíción ext4) tartalmazó képet `losetup --partscan`-nel csatol; egy 40 MiB-os, álvéletlen, MBR-es képet a `write_raw` ír ki visszaolvasásos ellenőrzéssel. A teszt összeveti a kiírt bájtokat a forrással (`cmp`), ellenőrzi, hogy a `wipefs` sem az elsődleges, sem a tartalék GPT-aláírást nem találja (csak a forrás `dos` tábláját), és hogy a kernel eldobta az elavult második partíciót. Egy második teszt az írás alatt kizárólagosan nyitva tart egy elavult partíciót; a `wipefs` ekkor `--force` nélkül elbukik, így a teszt észreveszi, ha ez a kapcsoló kimarad.
- **Windows (`test_loop_windows.py`):** egy, a Windows Setup lényeges fájlneveit tartalmazó könyvtárat egy ISO helyére bind-mountol (a `worker.mount_iso` és a `worker.read_iso_volume_label` helyettesítve), és a `write_windows_uefi` SHA-256 ellenőrzéssel fut egy 384 MiB-os képre. A teszt ellenőrzi a GPT-t (`sfdisk --json`: két Microsoft Basic Data partíció, a második neve `BMK_EFI`, `GUID:63`-mal), az NTFS-címkét, a FAT-címkét és minden másolt fájl SHA-256 értékét. A rögzített UEFI:NTFS képet a `BMK_UEFI_NTFS_IMAGE`-ből, a telepített példányból veszi, vagy a `fetch_uefi_ntfs.py`-jal letölti és ellenőrzi.

- **Windows Legacy BIOS (`test_loop_windows_bios.py`):** mindkét csoport egy teszt-`bootmgr`-t használ: néhány bájtnyi 16 bites valós módú kódot, amely a `BMK-BOOT-OK` szöveget a QEMU debug portjára (`0xE9`) írja, majd megáll. `BMK_QEMU=1` mellett a kép a `qemu-system-x86_64 -machine pc` alatt indul (SeaBIOS, TCG, `snapshot=on`), és a teszt legfeljebb 60 másodpercig vár erre a szövegre; hiba esetén kiírja a GRUB és a QEMU verzióját, a SeaBIOS naplóját, a VGA szöveges képernyőjét és egy `grub>` promptnál csak olvasó GRUB-parancsok kimenetét.
  - A `LoopWindowsBiosFeasibilityTests` (a T0 kapu) maga építi fel a pendrive-ot, a termelési writer nélkül: MBR egyetlen aktív 7-es típusú partícióval, NTFS a termelési geometriával, a kernel `ntfs3` vagy az `ntfs-3g` drivere, `grub-install --target=i386-pc` `--force` nélkül, és egy `grub.cfg`, amely az `ntldr /bootmgr`-t futtatja. Ellenőrzi az `55 AA` aláírást, a nem üres MBR-boot-kódot, a `core.img`-et a partíció előtti résben, a változatlan partíciótáblát, a GRUB-modulokat, és hogy a gazdagép `/boot/grub` könyvtára nem változott. Writertől független referenciaként marad meg, így egy GRUB- vagy disztribúcióváltozás megkülönböztethető egy writer-hibától.
  - A `LoopWindowsBiosWriterTests` a `write_windows_bios`-t futtatja SHA-256 ellenőrzéssel egy 256 MiB-os képre; egy vegyes kis- és nagybetűs Windows Setup fájlneveket tartalmazó könyvtárat (EFI-betöltő nélkül) bind-mountol az ISO helyére. Ellenőrzi az `sfdisk --json`-t (`dos`, egyetlen aktív `7`-es típusú partíció a 2048-as szektortól, a `calculate_mbr_layout` által adott mérettel), az NTFS-címkét, ugyanazokat a statikus MBR-ellenőrzéseket, a `grub/grub.cfg`-t a `worker.BIOS_GRUB_CFG`-hez képest, minden másolt fájl SHA-256 értékét és hogy csak a `/grub` került hozzá, hogy nem marad csatolás vagy `/run/bootmediakit-*` könyvtár, és hogy a gazdagép `/boot/grub` könyvtára nem változott. Egy második teszt előbb a `write_windows_uefi`-vel, majd a `write_windows_bios`-szal írja a képet, és ellenőrzi, hogy sem a `wipefs`, sem a közvetlen olvasás nem talál elsődleges vagy tartalék GPT-fejlécet. Egy harmadik QEMU-ban elindítja a kiírt képet.

A loop-eszköz helyettesítő: a `tests/integration/loop_helpers.py` eléri, hogy a `worker.lsblk_tree` pontosan a teszt loop-eszközét mutassa cserélhető `disk`-ként. A `validate_target` és minden más biztonsági ellenőrzés változatlanul fut. Ez a helyettesítés csak a tesztsegédben létezik.

Ismert korlátok és problémák:

- Ha a kernel vagy az udev 20 másodpercen belül nem hozza létre a partíciócsomópontokat (`/dev/loopNp1`, …), a teszt egy ide mutató üzenettel **elbukik**; nem lesz csendben sikeres. Ez udev nélküli konténerekben és partíciótábla-értelmező nélküli kerneleken fordul elő. A teszteket szokásos gépen vagy VM-ben futtasd, vagy gondoskodj róla, hogy az `udevadm settle` működjön, és a `/dev` devtmpfs legyen.
- Ezek a tesztek nem helyettesítik a fizikai USB-teszteket. Semmit nem bizonyítanak a kernel által ténylegesen *használt* partíciókról (csatolt, swap, LUKS), az USB-specifikus tulajdonságokról (`rm`, `tran=usb`), a firmware-ből való indításról vagy a Windows Setupról. A QEMU-s indítás csak azt mutatja, hogy a SeaBIOS, a GRUB és az `ntldr` láncbetöltés eljut egy teszt-`bootmgr`-ig; a valódi Windows Boot Managerről vagy a Setupról semmit nem mond.

### Egy kész pendrive kézi QEMU-indítási próbája

Egy fizikai gép újraindítása előtt a kész Windows Legacy BIOS pendrive QEMU-ban SeaBIOS-szal elindítható. Az alábbi próba soha nem ír a pendrive-ra: a QEMU a normál felhasználódként fut, **csak olvasási** hozzáféréssel az eszközhöz, és a `snapshot=on` a vendégrendszer írásait egy ideiglenes fájlba irányítja. (A `readonly=on`-t nem használjuk, mert a QEMU elutasítja a csak olvasható IDE-lemezt: „Block node is read-only”.)

1. Dugd be a pendrive-ot, ne csatold fel, és keresd meg az eszköznevét (lent `/dev/sdX`) a mérete, a modellje és a `TRAN` = `usb` alapján:

   ```bash
   lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS
   ```

2. Adj a felhasználódnak csak olvasási hozzáférést ehhez az eszközcsomóponthoz. A bejegyzés a pendrive kihúzásakor eltűnik. Ez csak akkor korlátozza a QEMU-t, ha a felhasználód nincs a `disk` csoportban (ellenőrizd: `id -nG`); a csoport tagjai amúgy is minden lemezre írhatnak, ezért ilyen fiókból ne futtasd a próbát:

   ```bash
   sudo setfacl -m u:"$USER":r /dev/sdX
   ```

3. Indítsd el QEMU-ban (a `-machine pc` SeaBIOS-t, azaz Legacy BIOS-t használ):

   ```bash
   qemu-system-x86_64 -machine pc -accel kvm -cpu host -m 4096 -drive file=/dev/sdX,format=raw,if=ide,snapshot=on -boot c
   ```

   KVM nélkül az `-accel kvm -cpu host` helyett `-accel tcg -cpu max` kell; a Windows Setup ekkor nagyon lassú. Várt eredmény: megjelenik a Windows Setup képernyője. Ott zárd be a QEMU ablakát; ne telepíts. Ne használd a QEMU-monitor `commit` parancsát (vagy a `Ctrl-A s`-t), mert az megpróbálná visszaírni az ideiglenes változásokat.

4. Töröld a hozzáférési bejegyzést (vagy húzd ki a pendrive-ot):

   ```bash
   sudo setfacl -x u:"$USER" /dev/sdX
   ```

Ha a `-machine pc` helyére `-machine q35 -bios /usr/share/edk2/x64/OVMF.4m.fd` kerül (Arch-csomag: `edk2-ovmf`; a firmware útvonala disztribúciónként eltérhet), a pendrive várhatóan **nem** indul, mert az OVMF-nek nincs NTFS-drivere. Ez nem bizonyítja, hogy a pendrive UEFI módban soha nem indul: egy NTFS-t olvasó UEFI firmware elindíthatja az ISO saját `efi/boot/bootx64.efi` fájlját az NTFS partícióról (egy Gigabyte B850 alaplapon kikapcsolt CSM mellett ez történt, lásd [docs/history/0.3.0.md](history/0.3.0.md)). Egyik próba sem helyettesíti a valódi gépen végzett tesztet.

## BootMediaKit 0.1.3 — Korábbi kiadás tesztjegyzőkönyve

### Automatizált ellenőrzések

A 0.1.3-as GitHub Actions munkafolyamat futtatta:

- a grafikus felület, a worker, az ISO-segédek és a UI-segédek Python-fordítását;
- a telepítő, az eltávolító és a privilegizált worker-wrapper shell-szintaxis-ellenőrzését;
- a rögzített UEFI:NTFS segédkép letöltését és hash-ellenőrzését;
- az NTFS-formázás argumentumainak valódi programmal végzett próbafuttatását (dry-run);
- egység- és csomagolási teszteket a lemezazonosításra, a forrás/cél ütközésvizsgálatra, a védett kötetek elutasítására, a megszakítási határokra, a polkit-csomagolásra, a reszponzív felületre, az ISO-címke értelmezésére és a GPT-partíciók elnevezésére.

### A felhasználó által jelentett fizikai ellenőrzés

- **Linux DD/RAW:** egy DD módban kiírt Linux ISO a tesztelt hardveren Legacy BIOS és UEFI módban is sikeresen elindult.
- **Windows UEFI:** a Windows 10 IoT Enterprise LTSC 2021 x64 az elkészült pendrive-ról elindult, és UEFI módban befejezte a telepítést.
- **Megszakítás:** a felhasználó megszakított egy fizikai pendrive-készítést; a worker biztonságosan leállt, és a pendrive egy következő próbához használható maradt.
- **Írási teljesítmény:** különböző USB 2.0-s pendrive-okon sikeres készítést jelentett, az eltelt idő az egyes pendrive-tól függően eltért.
- **Polkit és az alkalmazás telepítése:** a telepített csomagot CachyOS-en használta; a grafikus felület és a privilegizált worker elkészített egy Windows pendrive-ot.

### További ellenőrzést igényel

- Bekapcsolt és kikapcsolt Secure Boot több firmware-megvalósításon.
- A célmeghajtó fizikai kihúzásának/visszadugásának versenyhelyzet-tesztje.
- A célmeghajtón lévő forrás elutasításának fizikai tesztje.
- LUKS/LVM/RAID/swap elutasítása eldobható eszközökön.
- További Windows ISO-családok és nem CachyOS disztribúciók.

Fizikai hardver viselkedését ne állítsd pusztán egységtesztek alapján.
