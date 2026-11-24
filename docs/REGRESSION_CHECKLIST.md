# Kiadás előtti fizikai regressziós ellenőrzőlista

Minden kiadás előtt a gazda végzi el, **eldobható pendrive-on**, és a visszajelzése alapján kerül be a `docs/TESTING.md` jegyzőkönyvébe. A Claude Code ezt nem végezheti el és nem pipálhatja; ami nincs visszajelezve, az „nem tesztelt".

Eszközök: egy eldobható pendrive (vagy külső SSD, a LESSONS ellenőrzései után), egy Linux ISO (RAW), egy Windows 10/11 ISO. Az eszköznevet minden alkalommal `lsblk`-val ellenőrizd, mielőtt írsz.

## Kötelező minden kiadáshoz

1. **Linux RAW** (pl. Linux Mint): kiírás visszaolvasással, indítás UEFI-ből (és ha van Legacy gép, onnan is).
2. **Windows UEFI**: kiírás; `sudo sfdisk -d /dev/sdX` (GPT, két partíció, a másodiknak `BMK_EFI` a címkéje); indítás UEFI-ből a Windows Telepítő első/partíciós képernyőjéig.
3. **Windows Legacy**: kiírás ugyanarra a pendrive-ra; `sudo wipefs /dev/sdX` csak `dos` sort mutat; `sudo sfdisk -d /dev/sdX`: `label: dos`, `sector-size: 512`, `start=2048`, `type=7`, `bootable`; indítás Legacy/CSM módban a Windows Telepítő partíciós képernyőjéig.
4. **A gép saját rendszerbetöltője érintetlen**: egy kiírás után a fő gép újraindul a megszokott módon.
5. **GRUB nélküli állapot** (csak ha a kiadás érinti a Legacy képességvizsgálatot): a Legacy érték szürke a megfelelő szöveggel.

## Ha a kiadás GUI-t érint

6. Indítás a tesztmátrix szerinti asztali környezetekben (lásd az adott roadmap-fájlt), polkit-jelszókérés megjelenik; a fő felület használható a támogatott minimális méreten.

## Jegyzőkönyv

A gazda visszajelzésében szerepeljen: mit írt ki, milyen gépen/firmware-en indította, mi történt (a Setup melyik képernyőjéig jutott), és a `sfdisk`/`wipefs` kimenet, ahol kell. A Claude Code ebből készíti a `docs/TESTING.md` új szakaszát, és csak azt rögzíti, amit a gazda ténylegesen megírt.
