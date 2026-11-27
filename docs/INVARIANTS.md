# BootMediaKit – invariánsok

Ezek a szabályok **minden** fejlesztési szakaszra érvényesek (0.4.0-tól 1.0.0-ig és utána is). Ha egy feladat csak egy invariáns megsértésével oldható meg, a munka megáll, és a projektgazda dönt. Az invariánsokat tesztek őrzik; a tesztet nem lehet törölni vagy gyengíteni.

Ez a fájl a repóban él (`docs/INVARIANTS.md`), verziózva. A verziónkénti munkaleírások erre hivatkoznak.

## A. Lemezíró folyamatok (befagyasztva)

A1. **`write_raw()`**: a műveleti sorrend, a parancsok, a paraméterek, az írási és a visszaolvasási logika nem változik. Sorrend: `validate_target` → `ensure_source_not_on_target` → `unmount_disk` → … → `wipefs --all --force` → írás → `sync` → opcionális visszaolvasás → `rereadpt`.

A2. **`write_windows_uefi()`**: a műveleti sorrend, az elrendezés és a másolási/ellenőrzési logika nem változik. Elrendezés: GPT; 1. partíció NTFS az ISO kötetcímkéjével; 2. partíció 1 MiB-os FAT `BMK_EFI`; Microsoft Basic Data típus; `GUID:63` attribútum.

A3. **`write_windows_bios()`**: a műveleti sorrend nem változik. Elrendezés: `label: dos`, egyetlen NTFS partíció 2048-as kezdettel, típus `7`, aktív; GNU GRUB i386-pc láncbetöltő (`grub-install --target=i386-pc --boot-directory=<a cél NTFS csatolási pontja>`), `grub.cfg`-ben `insmod ntldr`, `insmod boot`, `ntldr /bootmgr`.

A4. **`wipefs --all --force`**: a `--force` kötelező. (Lásd LESSONS: `--force` nélkül egy tartott partíción a `wipefs` elhasal.)

A5. **Megszakítás**: kooperatív (`cancel` sor a worker `stdin`-jén), **`fsync` nélkül**, 130-as kilépési kóddal. A megszakítási határok és a takarítás nem változik. A részlegesen írt céleszköz állapotát a `TARGET_MODIFIED` jelzi.

A6. **A három writer változtathatatlan.** Csak reprodukálható hiba esetén, külön döntési kapuval nyúlhatunk hozzá: hibajelenség, minimális reprodukció, bizonyíték, kockázatelemzés, a gazda jóváhagyása, célzott regressziós teszt, majd fizikai teszt. Az `emit()` hívások kiegészítése azonosítóval (0.4.0/D) nem számít a writer viselkedésének módosításának, **de csak** a 0.4.0 T1 *writer-ujjlenyomat* tesztek zöldsége mellett végezhető, és a tesztek változatlanul zöldek maradnak.

## B. Biztonsági modell

B1. **A GUI soha nem fut rootként.** Nincs általános `sudo`/`pkexec` tartalék a GUI-ban.

B2. **A worker csak a rögzített, root tulajdonú wrapperen és a saját polkit-akción (`org.bootmediakit.policy`) át indulhat.** A worker `-I` módban fut, csak szabványos könyvtárral. A telepített útvonalak (`/usr/lib/bootmediakit/worker.py`, `/usr/libexec/bootmediakit/bootmediakit-worker`) ellenőrzése nem lazítható. A csomagolás nem változtathatja meg úgy az útvonalat vagy a jogosultságot, hogy az ellenőrzések megkerülhetők legyenek.

B3. **Fail-closed.** Ha egy biztonsági ellenőrzés nem tud dönteni (bizonytalan forrástároló, olvashatatlan tagállomány-lista, ismeretlen fájlrendszer-típus), a művelet megáll.

B4. **Védett célok.** Rendszerlemez, aktív swap, LUKS, LVM, RAID és összetett kötetek védelme nem lazítható. A forrás és a cél ütközésvizsgálata (halmozott csatolások, autofs/CIFS, Btrfs alkötetek és többeszközös Btrfs) nem lazítható; a célazonosság közvetlenül a romboló művelet előtt újra ellenőrződik.

B5. **`grub-install` csak a validált céleszközre futhat.** Közvetlenül előtte újra lefut a célazonosság-ellenőrzés. A hívás mindig tartalmazza: `--target=i386-pc`, explicit `--boot-directory=<a cél NTFS csatolási pontja>`, és utolsó argumentumként pontosan a validált eszközútvonalat. EFI-célú `grub-install`, `efibootmgr` és a gazdagép `/`, `/boot`, `/efi` könyvtárára mutató `--boot-directory` tilos.

B6. **A BootMediaKit nem tartalmaz és nem tölt le bináris boot-kódot** a Legacy módhoz. A UEFI:NTFS segédkép rögzített upstream commitból töltődik le, pontos méret-, Git blob SHA-1- és SHA-256-ellenőrzéssel.

B7. **A GUI és a worker nem hív csomagkezelőt** (`pacman`, `apt`, `dnf`) futás közben. A hiányzó függőségről a felhasználó pontos, cselekvésre alkalmas hibát kap.

B8. **A loop-eszközt USB-nek mutató helyettesítés** csak a `tests/integration/loop_helpers.py`-ban élhet, a termelési kódban nem.

## C. Felhasználói felület és szövegek

C1. A felhasználónak szánt szöveg konkrét: mi történt, és mit tegyen a felhasználó. A magyar szöveg a 0.8.0-ig a mérvadó forrás; a 0.4.0-tól új szöveg `tr()`-rel készül (lásd a 0.4.0 munkaleírást).

C2. A worker JSON-eseményeinek meglévő mezői (`message`, `log`, `error`, `percent`, `target_modified`, `worker_started`, `cancelled`) visszafelé kompatibilisek maradnak; új mezők csak additívak lehetnek.

C3. Soha nem tűnhet el egy fontos vezérlő (forrásfájl, célmeghajtó, írási mód, indítási mód, ellenőrzési beállítás, indítás/megszakítás, veszélyre figyelmeztető szöveg) a kis ablak miatt.

C4. **A megjelenés egyetlen úton alkalmazódik, és mindig teljesen.** Minden mód- (Automatikus/Világos/Sötét) és rendszerséma-váltáskor a `ThemeController.apply()` előbb visszaállítja a rendszer állapotát (natív stílus, rendszerpaletta), és csak abból dönt: kézi módban natív marad, ha a rendszerpaletta már a kért sémát adja, különben Fusion és saját paletta (`DARK_PALETTE`, `LIGHT_PALETTE`). Utána a stíluslap és minden widget újra-polisholása akkor is megtörténik, ha a szöveg vagy a séma nem változott. A Qt színséma-felülírását (`QStyleHints.setColorScheme`/`unsetColorScheme`) nem használjuk: a gtk3 platformtéma állapotot tart a hívások között, a KDE platformtéma figyelmen kívül hagyja őket. A világos palettát nem szabad a Fusion `standardPalette()`-jére építeni, mert az a Qt színsémáját követi. Minden váltás eredménye pixelre egyezik a friss indításéval ugyanabban a módban és rendszersémában (`tests/test_theme.py`, `ThemeSwitchMatrixTests`).

## D. Kiadási fegyelem

D1. **A verziószámot csak a kiadási commit emelheti** (`version.py`). Fejlesztés közben a `version.py` az előző kiadás számát mutatja.

D2. **Meglévő tesztet nem törlünk és nem gyengítünk.** Ha egy teszt a változtatás miatt elavul, az indoklás a commit üzenetbe kerül, és a gazda tud róla.

D3. **A CI nem lehet zöld úgy, hogy a kötelező integrációs tesztek kihagyódtak** (`BMK_INTEGRATION_REQUIRED=1`, `BMK_QEMU=1`: a hiányzó QEMU hiba, nem kihagyás).

D4. **Fizikai tesztet csak a gazda végez** eldobható adathordozón, és csak az ő kifejezett visszajelzése alapján kerül pipa a `docs/progress.md`-be. Ami nincs visszajelezve, az „nem tesztelt".

D5. **Új futási függőség** csak az `install.sh` és mindkét README egyidejű frissítésével kerülhet be; a függőségi dokumentáció (README-k, `CONTRIBUTING.md`, `docs/TESTING.md`, `install.sh`) egyezik.

D6. **Nem állítunk olyat, amit nem ellenőriztünk.** A dokumentáció csak ténylegesen kipróbált ISO-kat, indítási módokat, asztali környezeteket és disztribúciókat ígér. A tesztek bizonyító erejét pontosan címkézzük: egység/mock, loop-integráció, QEMU/OVMF/SeaBIOS, fizikai USB, Windows Setup. Ezek nem helyettesítik egymást.

D7. **A végfelhasználói csomag csak futásidőben szükséges fájlokat tartalmaz** (explicit telepítési manifestből); a teljes tesztinfrastruktúra a forrásrepóban és a CI-ben marad.

D8. **A verziószám csak a `version.py`-ban szerepelhet** a `.py` fájlok közül; kódkommentben, docstringben és kódszövegben nem. A hivatkozás feladatszámra (pl. T3) vagy a `CHANGELOG.md`/`docs/progress.md` megfelelő részére mutat. A `tests/test_packaging.py` verziószám-őre minden `.py` fájl teljes szövegét vizsgálja; az őr nem lazítható.
