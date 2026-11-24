# BootMediaKit – megtapasztalt hibák és tanulságok

Minden itt szereplő tétel **valóban megtörtént** a projekt fejlesztése vagy tesztelése közben. A cél: ne kövessük el kétszer. Új tapasztalat esetén ide kerül egy sor (a kiadási commit előtt a Claude Code javasolja, a gazda jóváhagyja). A tételek a `docs/INVARIANTS.md` szabályaira és a tesztekre mutatnak.

## Lemezírás és biztonság

- **`wipefs` `--force` nélkül elhasalt egy tartott partíción.** Ha a céleszköz egyik partíciója még foglalt, a sima `wipefs --all` hibával áll le. Ezt a sima loop-teszt nem fogta meg, ezért új, „tartott partíciós" RAW integrációs teszt készült. Tanulság: a `--force` kötelező (A4), és minden romboló lépéshez kell olyan teszt, amely a hibás, foglalt állapotot is előállítja.
- **Régi GPT-aláírás maradhatott a lemezen.** Legacy (MBR) írás olyan lemezre, amelyen előtte Windows UEFI (GPT) elrendezés volt, nem hagyhat sem elülső, sem hátsó GPT-fejlécet. Külön integrációs teszt őrzi; fizikailag is ellenőrizve (`wipefs` csak `dos` sort mutat).
- **A forrás és a cél ütközése rejtett lehet.** Halmozott csatolások, autofs/CIFS rétegek, Btrfs alkötetek és **többeszközös Btrfs** (a tagokat a `/sys/fs/btrfs/<UUID>/devices/` adja) mind elrejthetik, hogy az ISO a céllemezen van. A `fuseblk` (ntfs-3g) a mögötte lévő blokkeszközre oldódik fel. Ha a tagállomány nem olvasható, a művelet megáll (B3, B4).
- **2 TiB-os határ.** A pontosan 2**32 szektoros (2 TiB) vagy nagyobb lemezt elutasítjuk: az `sfdisk` ott csak figyelmeztet, és csendben levágná a partíciót.
- **Nem 512 bájtos logikai szektor.** Az MBR-elrendezés ellenőrzése `sector-size 512`-t vár. Egyes USB–SATA/NVMe házak 4096 bájtos logikai szektort jeleznek; ilyenkor a Legacy mód elutasít. (Külső SSD-házat tesztelés előtt ellenőrizni: `lsblk -t`, LOG-SEC oszlop.)
- **Külső SSD-ház eltérő `removable` jelzése.** Az USB-s ház a pendrive-tól eltérően gyakran `RM=0`-val jelentkezik; az eszközszűrés viselkedését előre ellenőrizni kell (`lsblk -o NAME,RM,TRAN,SIZE,MODEL`). A védelmet nem kerüljük meg.
- **Megszakításkor nincs `fsync`.** A cancel kooperatív, 130-as kilépési kóddal; a részlegesen írt céleszköz állapotát a `TARGET_MODIFIED` jelzi (A5).
- **Törött GUI–worker pipe.** A GUI csövének megszakadása Windows- vagy RAW-írás közben a következő megszakítási pontban biztonságosan leállítja a workert, takarít, és 130-cal lép ki; regressziós teszt őrzi.
- **Windows ISO Legacy módhoz**: `bootmgr`, `boot/BCD`, `sources/boot.wim` és telepítőkép kell, az EFI-betöltő nem. A Windows XP/2003 típusú (`i386`, `bootmgr` nélkül) ISO nem támogatott. Ha az ISO gyökerében már van `grub` bejegyzés, elutasítjuk.
- **A hivatalos Windows 7 SP1 ISO nem tartalmaz `efi\boot\bootx64.efi` fájlt**, ezért UEFI módban nem támogatott; a Windows 7 csak Legacy módban támogatott. (A Windows 10 formátumra átalakított ISO-kban van `efi` mappa.)

## GRUB és Legacy mód

- **A GRUB 2.14 (Ubuntu CI) nem tölti be automatikusan a parancsmodulokat.** A `grub.cfg` ezért kifejezetten `insmod ntldr` és `insmod boot` sorokat tartalmaz; különben `can't find command` hiba jön. Az Arch GRUB 2.16-on a két sor ártalmatlan.
- **A `grub-install` csomag telepítése nem változtatja meg a gép saját rendszerbetöltőjét.** A CachyOS `grub` csomag telepítője csak kiír egy `grub-install`/`grub-mkconfig` tanácsot, ami a gép saját betöltőjére vonatkozik; a BootMediaKit-hez nem kell lefuttatni. A rendszer Limine-t használ, nem GRUB-ot.
- **`pacman -R grub` megtagadva a `woeusb` miatt.** A `woeusb` függőségként igényli a `grub`-ot; a pacman védelme működik. A BootMediaKit nem használ `woeusb`-ot.
- **Hiányzó GRUB esetén a Legacy érték szürke**, súgószöveggel (`sudo pacman -S grub`); a képesség vizsgálata (`grub-install` és `/usr/lib/grub/i386-pc`) indításkor lefut. Fizikailag ellenőrizve.
- **A Legacy pendrive NEM mindig „csak Legacy".** NTFS-driver nélküli UEFI-ben (OVMF) nem indul, de egy NTFS-t olvasó firmware (Gigabyte B850, CSM kikapcsolva) elindította az ISO saját `efi/boot/bootx64.efi` fájlját az NTFS partícióról (`PEFirmwareType` 0x2). Nem programhiba. A GUI, a worker naplója és a README ezért nem állítja, hogy a pendrive UEFI-ben soha nem indul; UEFI-s géphez az UEFI (GPT) mód való. A bootmenüben látható `UEFI:` előtag önmagában nem bizonyít semmit.
- **`grub-install` kimenet és nyelv.** A gazdagép nyelve magyar: a `pacman` kimenete lokalizált, ezért a kimenet szövegére építő ellenőrzés (`grep`) elhasal. Tesztben és scriptben mindig `LC_ALL=C`, és ahol lehet, géppel olvasható kimenet (`--json`, `--output`).

## Tesztelés és CI

- **A `sudo -E` nem adta át a környezeti változókat** az ubuntu-26.04 runneren; ezért `sudo env BMK_INTEGRATION_REQUIRED=1 BMK_QEMU=1 …` a használt forma, és külön CI-lépés ellenőrzi, hogy a root folyamat megkapja őket.
- **Átmeneti csomagtükör-hibák** (DNS-hiba a `security.ubuntu.com`-ra, 404, megakadt letöltés) leállították a CI-t: a csomagtelepítés háromszor próbálkozik (30 s várakozással), a job 30, a telepítési lépés 20 perces időkorlátot kap, a hiba az utolsó próba után is hibaként marad.
- **`QEMU` `readonly=on` IDE-lemezen nem megy** (QEMU 11.1 elutasítja). Kész pendrive kézi QEMU-próbájához: QEMU a normál felhasználóként, olvasási ACL az eszközön (`setfacl`), `-drive …,format=raw,if=ide,snapshot=on`, SeaBIOS (`-machine pc`); az OVMF-es ellenpróba `-machine q35 -bios <OVMF>`. A QEMU alapból VNC-t indít (`vncviewer localhost:5900`), saját ablakhoz `-display gtk` vagy `-display sdl`.
- **A teszt `bootmgr` + QEMU nem bizonyítja a valódi Windows Setup indulását.** A tesztek bizonyító erejét címkézni kell (D6).
- **Root tulajdonú `__pycache__`.** A `sudo`-val futtatott tesztek root tulajdonú `__pycache__` mappákat hagynak, amitől a következő normál futás `Permission denied` hibát kaphat. Javítás: `sudo rm -rf __pycache__ tests/__pycache__ tests/integration/__pycache__`; megelőzés: `PYTHONDONTWRITEBYTECODE=1` a root futtatásnál.
- **Sandbox/konténer udev nélkül** nem hoz létre partíciócsomópontokat: a loop-integrációs tesztek valódi gépen vagy CI-runneren futnak. A `os.stat` hívások tesztbeli kiváltása (`fake_dev_stat`) egyszer már hibát okozott; új tesztben ezt a mintát használjuk.
- **A mockolt egységteszt és a loop-teszt nem bizonyítja a fizikai hardver viselkedését.** Fizikai tesztet csak a gazda végez eldobható adathordozón.

## Windows UEFI

- **Elrendezés:** GPT; NTFS az ISO címkéjével; 1 MiB-os FAT `BMK_EFI`; Basic Data; `GUID:63`. A UEFI:NTFS segédkép rögzített upstream commitból töltődik le, pontos hash-ellenőrzéssel; a címke `BMK_EFI`-re átnevezése a másolaton történik, az eredeti változatlan marad.
- **Windows 11 26H2 Secure Boot** be/ki: a Setup a partícióválasztóig jutott; a teljes telepítést nem vittük végig, ezért nem állítunk általános Secure Boot-kompatibilitást.
- **Linux RAW (Mint) első indításkor létrehoz egy `writable` partíciót** a kép után maradt szabad helyen. Ezt az élő rendszer teszi, nem a BootMediaKit.

## GitHub, Git és munkafolyamat

- **`git push` jelszóval nem működik** (a GitHub nem fogadja el): `gh auth login` (HTTPS, böngésző), majd `gh auth setup-git`.
- **Hiányzó git-azonosító** (`user.name`/`user.email`) miatt a Claude Code nem tudott commitolni: globálisan be kell állítani (a GitHub noreply címmel).
- **A `main` védett** (ruleset: PR kötelező 0 jóváhagyással, kötelező ellenőrzés `Python and shell checks`, törlés és force push tiltva). Közvetlen push nem megy.
- **Ágak törlése API-n/proxyn át 403-at adott**: ágtörlést a gazda a GitHub felületén végez. A `dev/<verzió>` ág a kiadás után törölhető, a tag örök.
- **A Claude Code megtagadta a kiadást**, mert a `CLAUDE.md` szerint a merge/tag/release a gazda dolga volt. Az új folyamat: a Claude Code a PR-ig és a merge-ig, majd a **piszkozat-release**-ig viszi (lásd `CLAUDE.md` „Kiadás"); a Publish gombot a gazda nyomja meg.
- **Téves állítás a szövegben:** a 0.3.0 fejlesztés alatt a szöveg azt állította, hogy a Legacy pendrive UEFI-ben nem indul; a fizikai teszt cáfolta, a szöveg, a GUI és a tesztek javultak. Tanulság: dokumentációban és GUI-szövegben csak ellenőrzött állítás szerepelhet (D6).

## Folyamat

- **Rövid, kis commitok, feladatonként, teszttel együtt.** A 0.2.2 és a 0.3.0 így haladt zökkenők nélkül.
- **A munkaleírás eltéréseit a gazda jóváhagyja és dokumentálja** (lásd a 0.3.0 „Jóváhagyott és dokumentált eltérések" szakaszt a `ROADMAP.md`-ben). Ez a minta marad.
