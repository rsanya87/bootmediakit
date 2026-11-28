[English](CONTRIBUTING.md) | Magyar

# Közreműködés

A BootMediaKit korai szakaszban lévő projekt. A megbízhatóság és az adatbiztonság fontosabb a funkciók számánál.

## Mielőtt a kódhoz nyúlsz

Ezeket olvasd el először (magyarul): a [`docs/INVARIANTS.md`](docs/INVARIANTS.md) sorolja fel azokat a szabályokat, amelyeket egyetlen változtatás sem sérthet meg (a három writer befagyasztott), a [`docs/LESSONS.md`](docs/LESSONS.md) a már megtörtént hibákat, a [`docs/REGRESSION_CHECKLIST.md`](docs/REGRESSION_CHECKLIST.md) pedig azokat a fizikai ellenőrzéseket, amelyeket a karbantartó minden kiadás előtt elvégez. Egy új worker-üzenethez a [`docs/MESSAGES.md`](docs/MESSAGES.md)-ben felsorolt `msg_id` kell.

1. Nézd meg a `ROADMAP.hu.md`-t, a `docs/progress.md`-t és a meglévő hibajegyeket, hátha a probléma már ismert.
2. A grafikus felület maradjon jogosultság nélküli. A privilegizált műveletek maradjanak a szűk hatókörű workerben, és csak kifejezett megerősítés után induljanak.
3. Minden romboló művelet előtt közvetlenül ellenőrizd újra a cél blokkeszközt. A rendszerlemez védelmi ellenőrzéseit soha ne gyengítsd kényelmi okból.
4. Minden hibajavításhoz adj hozzá vagy frissíts automatizált tesztet.
5. Írd le, hogy egy teszt mockolt, egységszintű, hardverszintű, firmware-szintű vagy valódi Windows Setup-teszt.

## Karbantartói dokumentumok

A karbantartói dokumentumok csak egy nyelven léteznek, hogy minden változtatás egyszer készüljön el:

- Magyarul: [docs/INVARIANTS.md](docs/INVARIANTS.md), [docs/LESSONS.md](docs/LESSONS.md), [docs/REGRESSION_CHECKLIST.md](docs/REGRESSION_CHECKLIST.md), [docs/progress.md](docs/progress.md) és a lezárt kiadások naplói a [docs/history/](docs/history/) alatt.
- A [docs/MESSAGES.md](docs/MESSAGES.md) angolul írja le az üzenetazonosítókat; a benne lévő felületi szövegek a program magyar forrásszövegei.
- A [CHANGELOG.md](CHANGELOG.md), a kiadási jegyzetek és a [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) csak angolul léteznek.

A felhasználóknak és a közreműködőknek szóló dokumentumok angolul (eredeti fájlnév) és magyarul (ugyanaz a név `.hu.md` végződéssel) is léteznek: README, CONTRIBUTING, ROADMAP és `docs/TESTING`. Ha valamelyiket módosítod, mindkét nyelvi változatot frissítsd.

## Fejlesztői környezet

A jelenlegi alap Arch-alapú Linuxot céloz. A futási függőségek azok az Arch-csomagok, amelyeket az `install.sh` telepít, és mindkét README felsorol: `pyside6`, `util-linux`, `parted`, `ntfs-3g`, `ntfsprogs`, `dosfstools`, `polkit`, `7zip` és `grub` (csak a `grub-install` és az i386-pc modulok, a Windows Legacy BIOS módhoz). A `wimlib` a 0.1.2 óta nincs használatban (nincs WIM-darabolás). A tesztekhez ezen felül a DejaVu Sans és a Noto Sans betűtípus kell (Arch: `ttf-dejavu`, `noto-fonts`), a `shellcheck`, a `desktop-file-utils`, és az integrációs tesztek QEMU-s indítási próbáihoz a `qemu-system-x86_64` (Arch: `qemu-system-x86`).

## Tesztek

```bash
python3 -m py_compile app.py worker.py iso_utils.py ui_helpers.py theme.py fetch_uefi_ntfs.py version.py
bash -n install.sh uninstall.sh bootmediakit-worker
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

A GUI-tesztekhez `PySide6` kell. A CI ezen felül a `shellcheck -S warning install.sh uninstall.sh bootmediakit-worker` parancsot és rootként a loop-eszközös integrációs teszteket is futtatja:

```bash
sudo -E env BMK_INTEGRATION=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

A Windows Legacy BIOS pendrive QEMU/SeaBIOS-os indítási próbájával együtt, ahogy a CI is futtatja:

```bash
sudo -E env BMK_INTEGRATION=1 BMK_QEMU=1 QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests/integration -v
```

A követelményeiket és a kihagyási feltételeiket, valamint egy kész pendrive csak olvasó kézi QEMU-próbáját lásd a `docs/TESTING.hu.md`-ben. Az alkalmazás verziószáma csak a `version.py`-ban él; csak egy kiadási commit változtathatja meg.

Ne állítsd, hogy egy fizikai eszközzel vagy a Windows Setuppal kapcsolatos hiba javítva van, pusztán egységtesztek alapján. Valódi USB-írási tesztet csak eldobható adathordozón végezz.

## Pull requestek

- Írd le a problémát és a várt viselkedést.
- Add meg a teszteredményeket és a teszt szintjét.
- Csatold a releváns naplókat, a személyes útvonalak, sorozatszámok és nem kapcsolódó azonosítók eltávolítása után.
- Ha indokolt, frissítsd a `CHANGELOG.md`-t és a `docs/progress.md`-t.

## A hozzájárulások licence

A BootMediaKithez beküldött hozzájárulások (pull requestek, javítások) a projekt licence, a GPL-3.0-only alatt kerülnek a projektbe; lásd: [LICENSE](LICENSE). Csak olyan munkát küldj be, amelyet jogosult vagy így licencelni.
