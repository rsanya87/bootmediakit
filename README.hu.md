# BootMediaKit

**BootMediaKit** egy natív, magyar nyelvű grafikus USB-készítő Arch-alapú Linux rendszerekhez (jelenleg CachyOS-on tesztelt). A Rufus használati folyamatából merít ötletet, de nem a Rufus Windows-programjának Linuxra fordított vagy teljes funkcionalitású portja.

Verzió: `0.1.1-alpha`

## Mit tud ez a változat?

### 1. Lemezkép közvetlen kiírása

- ISO, IMG, BIN és RAW lemezképfájlok közvetlen írása USB-meghajtóra.
- Külön `dd` parancs nélkül, grafikus felületről.
- A kiírás után opcionális teljes visszaolvasás és bájtról bájtra összehasonlítás.
- A régi partíciós és fájlrendszer-aláírások eltávolítása az írás előtt.
- Folyamatjelző és napló.

**Fontos:** ez a mód nyers lemezképírás. Linux ISO-k esetében a legtöbb hibrid ISO-val használható. Nem alakít át egy tetszőleges, hagyományos ISO-fájlt bootolható lemezzé. Szokványos Windows telepítő ISO-hoz a külön Windows módot használd.

### 2. Windows telepítő USB (UEFI x64)

- Windows ISO csatolása csak olvasható módban.
- GPT partíciós tábla és FAT32 EFI rendszerpartíció létrehozása.
- A Windows telepítőfájlok másolása.
- A 4 GiB-nál nagyobb `install.wim` fájl automatikus darabolása `install.swm`, `install2.swm` stb. részekre a `wimlib` segítségével.
- A 4 GiB-nál nagyobb, nem titkosított `install.esd` átalakítása hagyományos LZX-tömörítésű WIM-mé, majd darabolása `install*.swm` fájlokra.
- A nagy WIM/ESD fájlok előfeldolgozása és a tényleges USB-kapacitás ellenőrzése még a pendrive törlése előtt történik.
- A Microsoft ISO-kban található szabványos x64 UEFI indítófájl ellenőrzése.
- A nagy WIM/ESD fájlból készült SWM-részek méretének ellenőrzése FAT32-kompatibilitáshoz.

A Windows-fájlmásolási mód jelenleg nem végez teljes, USB-ről visszaolvasásos fájlonkénti ellenőrzést; a nyers lemezkép mód külön visszaolvasásos ellenőrzést kínál.

A célmód **UEFI x64**. Legacy BIOS / CSM indítás, UEFI:NTFS, Windows To Go és TPM/Secure Boot követelményeket megkerülő telepítő még nincs támogatva. A 4 GiB feletti, titkosított ESD-ket a wimlib nem tudja feldolgozni. Az ESD átalakításához és darabolásához a `/var/tmp` fájlrendszeren jelentős szabad tárhely szükséges; a program ezt előzetesen ellenőrzi. A Windows ISO-tól és a célgéptől függően Secure Boot kompatibilitást nem garantálok.

## Biztonsági korlátok

- A grafikus felület normál felhasználóként fut.
- A `7zip` segítségével felismeri a szokványos Windows telepítő ISO-kat, és figyelmeztet, ha azokat közvetlen nyers írási módban próbálnád kiírni.
- Csak a tényleges írás előtt kér rendszergazdai engedélyt a `pkexec` segítségével.
- A meghajtólistában alapértelmezésben csak USB-nek jelölt vagy eltávolítható lemezek szerepelnek.
- A háttérfolyamat az írás előtt ismét ellenőrzi, hogy teljes lemez legyen kiválasztva, valóban USB/eltávolítható-e, írható-e, és nem a rendszer (`/`, `/boot`, `/efi`) meghajtója-e.
- Minden célpartíció leválasztásra kerül a művelet előtt.
- A felület külön megerősítést kér, mert a célmeghajtó teljes tartalma törlődik.

A biztonsági ellenőrzések csökkentik a téves meghajtóválasztás kockázatát, de nem helyettesítik a felhasználó ellenőrzését. Mindig ellenőrizd a meghajtó nevét és kapacitását.

## Telepítés Arch-alapú Linux alatt

1. Töltsd le és csomagold ki a `BootMediaKit` könyvtárat.
2. Nyiss terminált ebben a könyvtárban.
3. Futtasd:

   ```bash
   chmod +x install.sh
   ./install.sh
   ```

A telepítő a következő Arch Linux csomagokat kéri a `pacman` segítségével:

- `pyside6` – grafikus felület
- `parted` – partíciós tábla létrehozása
- `dosfstools` – FAT32 fájlrendszer
- `wimlib` – nagy Windows WIM fájlok darabolása
- `7zip` – Windows ISO-k felismerése, hogy ne kerüljenek véletlenül nyers kiírásra
- `polkit` – jogosultságkezelés

A `lsblk`, `blockdev`, `findmnt`, `mount`, `umount`, `wipefs`, `sync` és `udevadm` az alap Arch Linux rendszer segédprogramjai. KDE alatt egy aktív polkit hitelesítő ügynök szükséges a hitelesítési ablak megjelenítéséhez.

Indítás: alkalmazásmenüből **BootMediaKit**, vagy terminálból:

```bash
bootmediakit
```

## Eltávolítás

A projekt könyvtárából:

```bash
./uninstall.sh
```

A függőségként telepített rendszer-csomagokat az eltávolító nem törli.

## Tesztelés és jelenlegi korlátok

A platformfüggetlen biztonsági és ISO-felismerési tesztek futtatása a forráskönyvtárban:

```bash
python3 -m unittest discover -s tests -v
```

Ez egy alfa kiadás. A tesztek a fájlkezelési, WIM/ESD-előkészítési és biztonsági logikát ellenőrzik; ebben a fejlesztői környezetben nem lehetett valódi pendrive-on tesztelni. Nem állítom, hogy minden ISO-val, USB-vezérlővel, UEFI firmware-rel vagy Windows-kiadással már igazoltan működik.

Első használatkor csak olyan pendrive-val próbáld, amelyen nincs megőrzendő adat. Az elkészült adathordozót a célgépen indítsd el, és ellenőrizd a telepítő működését.

## Tervezett, de még nem megvalósított Rufus-funkciók

- MBR / Legacy BIOS Windows telepítőmód
- NTFS és UEFI:NTFS
- FreeDOS / MS-DOS indító
- Windows To Go
- Linux perzisztens tárhely
- Hibás szektor / hamis kapacitás teszt
- SHA-256 / SHA-1 / MD5 ellenőrzőösszeg
- Tetszőleges USB-formázás több fájlrendszerrel
- Windows ISO letöltő
- Windows 11 telepítő testreszabási lehetőségek
- VHD / VHDX / FFU műveletek

## Licenc

A projekt saját kódja GNU GPL v3 (GPL-3.0-only) licenc alatt kerül kiadásra. Külső rendszereszközöket használ (például `parted`, `wimlib`, `dosfstools`); ezek saját licence és csomagolása változatlan marad.

## Platformtámogatás – fontos

Ez a `0.1.1-alpha` alapverzió jelenleg Arch-alapú rendszerekhez készült telepítőszkriptet tartalmaz; a fejlesztési és első tesztelési célrendszer a CachyOS. Ubuntu, Debian és Fedora támogatás tervben van, de ehhez még külön függőségkezelés, telepítőcsomagolás és disztribúciónkénti tesztelés szükséges. Ezeket a rendszereket ez a kiadás még nem támogatja hivatalosan.

## Kiinduló verzió és tesztállapot

Ez a repository a korábbi belső `CachyUSB 0.1.1-alpha` forrásából indul. A kiinduló változatban a projekt neve, a telepítési útvonalak, az indítóparancs és az alkalmazásmenü-bejegyzés `BootMediaKit` névre változott; a működési logika szándékosan nem változott. A kilenc automatizált egységteszt fejlesztői környezetben sikeresen lefutott. Fizikai USB-eszközös és UEFI/Windows telepítési teszt nincs teljes körűen igazolva.

A jelenleg ismert Windows UEFI telepítési problémát és a `0.1.2` tervezett munkáit a [ROADMAP.md](ROADMAP.md) és a [docs/DEVELOPMENT_LOG.md](docs/DEVELOPMENT_LOG.md) dokumentálja.
