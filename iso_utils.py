"""ISO inspection helpers that do not depend on the GUI toolkit."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def is_windows_install_iso(path: Path) -> bool:
    """Best-effort ISO directory listing; this is a UX guard, not trust."""
    seven_zip = shutil.which("7z")
    if not seven_zip:
        return False
    try:
        result = subprocess.run(
            [seven_zip, "l", "-slt", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        if not line.lower().startswith("path = "):
            continue
        member = line.split("=", 1)[1].strip().replace("\\", "/").lower().lstrip("/")
        if member in {"sources/install.wim", "sources/install.esd"}:
            return True
    return False
