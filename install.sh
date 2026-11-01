#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/usr/lib/bootmediakit"
BIN_PATH="/usr/bin/bootmediakit"
DESKTOP_PATH="/usr/share/applications/bootmediakit.desktop"
ICON_PATH="/usr/share/icons/hicolor/scalable/apps/bootmediakit.svg"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    exec sudo bash "$0" "$@"
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v pacman >/dev/null 2>&1; then
    echo "Ez a telepítő Arch-alapú Linux rendszerekhez készült." >&2
    exit 1
fi

printf '\nA BootMediaKit működéséhez szükséges csomagok telepítése…\n'
pacman -S --needed pyside6 util-linux parted ntfs-3g ntfsprogs polkit 7zip

UEFI_DIR="/usr/share/bootmediakit/uefi"
install -d -m 0755 "$UEFI_DIR"
printf '\nA hivatalos, verzióhoz rögzített UEFI:NTFS indítókép letöltése és ellenőrzése…\n'
/usr/bin/python3 "$SCRIPT_DIR/fetch_uefi_ntfs.py" "$UEFI_DIR/uefi-ntfs.img"

install -d -m 0755 "$APP_DIR"
install -d -m 0755 "$(dirname "$ICON_PATH")" "$(dirname "$DESKTOP_PATH")"
install -m 0755 "$SCRIPT_DIR/app.py" "$APP_DIR/app.py"
install -m 0755 "$SCRIPT_DIR/worker.py" "$APP_DIR/worker.py"
install -m 0644 "$SCRIPT_DIR/iso_utils.py" "$APP_DIR/iso_utils.py"
install -m 0644 "$SCRIPT_DIR/bootmediakit.svg" "$ICON_PATH"
install -m 0644 "$SCRIPT_DIR/bootmediakit.desktop" "$DESKTOP_PATH"

cat > "$BIN_PATH" <<'WRAPPER'
#!/usr/bin/env sh
exec /usr/bin/python3 /usr/lib/bootmediakit/app.py "$@"
WRAPPER
chmod 0755 "$BIN_PATH"

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

printf '\nA BootMediaKit telepítése kész.\n'
printf 'Indítás: bootmediakit\n'
printf 'A program az alkalmazásmenüben is megjelenik.\n\n'
printf 'Megjegyzés: a grafikus KDE munkamenetben aktív polkit hitelesítő ügynök szükséges.\n'
