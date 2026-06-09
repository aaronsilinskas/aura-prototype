"""General-purpose lerp utilities for game rules."""

from __future__ import annotations


def level_lerp(level: int, max_val: float, min_val: float, max_level: int) -> float:
    """Interpolate between ``max_val`` (level 1, easiest) and ``min_val`` (hardest).

    ``fraction = (level - 1) / (max_level - 1)`` clamped to ``[0.0, 1.0]``.
    When ``max_level <= 1`` the guard returns ``max_val`` (fraction = 0).
    """
    fraction = 0.0 if max_level <= 1 else (level - 1) / (max_level - 1)
    if fraction < 0.0:
        fraction = 0.0
    elif fraction > 1.0:
        fraction = 1.0
    return max_val + (min_val - max_val) * fraction
