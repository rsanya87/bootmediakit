#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    exec sudo bash "$0" "$@"
fi
rm -rf /usr/lib/bootmediakit
rm -rf /usr/share/bootmediakit
rm -f /usr/bin/bootmediakit
rm -f /usr/share/applications/bootmediakit.desktop
rm -f /usr/share/icons/hicolor/scalable/apps/bootmediakit.svg
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
echo "A BootMediaKit eltávolítva. A függőségként telepített csomagok érintetlenek maradtak."
