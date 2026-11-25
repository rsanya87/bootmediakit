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


# -- Responsive layout (T3, layout work) ---------------------------------------
# All sizes are Qt logical pixels of the window's client area; Qt applies the
# device pixel ratio itself, so nothing here is multiplied by it.

LAYOUT_PROFILES = ("normal", "wide", "narrow")

# Spacing and control heights per density. "normal" is the single-column
# layout on tall screens; "wide" (two columns) and "narrow" (one column, the
# fallback below the minimum size) use the compact density.
DENSITY = {
    "normal": {
        "outer_margin": 12, "spacing": 7, "card_margin": (11, 7), "card_spacing": 5,
        "warning_margin": (10, 7), "line_edit": 32, "combo": 33, "mode_button": 34,
        "boot_combo": 30, "action_button": 38, "log_min": 56,
    },
    "compact": {
        "outer_margin": 8, "spacing": 5, "card_margin": (9, 5), "card_spacing": 3,
        "warning_margin": (8, 5), "line_edit": 29, "combo": 29, "mode_button": 30,
        "boot_combo": 28, "action_button": 34, "log_min": 44,
    },
}


def density_for(profile: str) -> dict[str, object]:
    if profile not in LAYOUT_PROFILES:
        raise ValueError(f"ismeretlen elrendezés: {profile!r}")
    return DENSITY["normal" if profile == "normal" else "compact"]


def choose_layout_profile(
    viewport: tuple[int, int],
    requirements: dict[str, tuple[int, int]],
) -> str:
    """Pick the layout from the measured (width, height) each one needs.

    One column when it fits; otherwise two columns when they fit. If neither
    fits (below the minimum size, e.g. very large fonts) the scroll area is
    the last resort: two columns when they are not too wide, since they need
    less scrolling, else the compact single column.
    """
    width, height = viewport
    for profile in ("normal", "wide"):
        need = requirements.get(profile)
        if need is not None and need[0] <= width and need[1] <= height:
            return profile
    wide = requirements.get("wide")
    if wide is not None and wide[0] <= width:
        return "wide"
    return "narrow"


def initial_window_size(
    available_width: int,
    available_height: int,
    single_column_height: int,
    minimum: tuple[int, int],
) -> tuple[int, int]:
    """First window size (outer frame estimate) inside the work area.

    Tall work areas keep the single-column window of earlier versions
    (calculate_window_profile); short ones get a window wide enough for the
    two-column layout. Never larger than the work area minus a 24 px margin.
    """
    usable_width = max(1, int(available_width) - 24)
    usable_height = max(1, int(available_height) - 24)
    width, height, _ = calculate_window_profile(available_width, available_height)
    if height >= single_column_height:
        return min(width, usable_width), min(height, usable_height)
    return min(max(minimum[0], 960), usable_width), usable_height


def clamp_minimum_size(minimum: tuple[int, int], available: tuple[int, int]) -> tuple[int, int]:
    """The minimum window size never exceeds the screen's available area."""
    return min(int(minimum[0]), int(available[0])), min(int(minimum[1]), int(available[1]))
