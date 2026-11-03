"""Small presentation helpers that do not depend on Qt."""

from __future__ import annotations


def format_elapsed_time(elapsed_milliseconds: int) -> str:
    """Format a monotonic elapsed duration as MM:SS or HH:MM:SS."""
    total_seconds = max(0, int(elapsed_milliseconds) // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def calculate_window_profile(available_width: int, available_height: int) -> tuple[int, int, bool]:
    """Return a screen-safe initial window size and compact-layout flag.

    Geometry is expressed in Qt logical pixels (QScreen.availableGeometry),
    so high-DPI scaling remains the responsibility of Qt and font point sizes
    stay unchanged across 2K/4K displays.
    """
    width = max(560, min(740, int(available_width) - 24))
    height = max(520, min(900, int(available_height) - 20))
    compact = int(available_height) < 850
    return width, height, compact
