"""Duration parsing and formatting helpers."""

from __future__ import annotations

import re

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_DURATION = re.compile(r"^(\d+(?:\.\d+)?)([smhd]?)$")
_SIZE = re.compile(r"^(\d+)([kKmM]?)$")


def parse_duration(text: str) -> float:
    """Parse ``90``, ``90s``, ``15m``, ``6h`` or ``2d`` into seconds.

    Args:
        text: Duration text. A bare number means seconds.

    Returns:
        The duration in seconds.

    Raises:
        ValueError: If *text* is not a positive duration.
    """
    match = _DURATION.match(text.strip().lower())
    if not match:
        raise ValueError(f"invalid duration {text!r}; use e.g. 90s, 15m, 6h, 2d")
    seconds = float(match.group(1)) * _UNITS[match.group(2) or "s"]
    if seconds <= 0:
        raise ValueError(f"duration must be positive, got {text!r}")
    return seconds


def format_duration(seconds: float | None) -> str:
    """Render *seconds* compactly, e.g. ``72s``, ``16m14s``, ``2h05m``."""
    if seconds is None:
        return "-"
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m{total % 60:02d}s"
    return f"{total // 3600}h{(total % 3600) // 60:02d}m"


def parse_size(text: str) -> int:
    """Parse ``2048``, ``64K`` or ``1M`` into bytes.

    Raises:
        ValueError: If *text* is not a positive size.
    """
    match = _SIZE.match(text.strip())
    if not match:
        raise ValueError(f"invalid size {text!r}; use e.g. 2048, 64K, 1M")
    size = (
        int(match.group(1))
        * {"": 1, "k": 1024, "m": 1024 * 1024}[match.group(2).lower()]
    )
    if size <= 0:
        raise ValueError(f"size must be positive, got {text!r}")
    return size
