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
