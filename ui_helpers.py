"""Small presentation helpers that do not depend on Qt."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

# Mirror of worker.GRUB_PC_DIRECTORY / GRUB_PC_REQUIRED_FILES. The GUI cannot
# import the privileged worker; tests/test_app.py keeps the two in sync.
GRUB_PC_DIRECTORY = Path("/usr/lib/grub/i386-pc")
GRUB_PC_REQUIRED_FILES = ("boot.img", "biosdisk.mod", "part_msdos.mod", "ntfs.mod", "ntldr.mod")


def format_elapsed_time(elapsed_milliseconds: int) -> str:
    """Format a monotonic elapsed duration as MM:SS or HH:MM:SS."""
    total_seconds = max(0, int(elapsed_milliseconds) // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def calculate_window_profile(available_width: int, available_height: int) -> tuple[int, int, bool]:
    """Return an outer window size and density mode from Qt logical screen geometry.

    The returned dimensions include a 24 px work-area margin. At show time,
    MainWindow.fit_window_to_screen subtracts the actual native window-frame
    dimensions before calling QWidget.resize().
    """
    width = max(560, min(740, int(available_width) - 24))
    height = max(520, min(900, int(available_height) - 24))
    compact = int(available_height) < 850
    return width, height, compact


def bios_grub_available(
    which: Callable[[str], str | None] = shutil.which,
    directory: Path = GRUB_PC_DIRECTORY,
) -> bool:
    """True when grub-install and the i386-pc files the worker needs exist.

    This only decides whether the GUI offers the Legacy BIOS mode; the worker
    repeats the check before it touches the target.
    """
    if which("grub-install") is None:
        return False
    try:
        if not directory.is_dir():
            return False
        return all((directory / name).is_file() for name in GRUB_PC_REQUIRED_FILES)
    except OSError:
        return False
