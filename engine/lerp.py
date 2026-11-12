"""The one level interpolation, shared by Game Levels and Effect Levels."""

from __future__ import annotations

import math


def level_lerp(level: int, first_value: float, top_value: float, top_level: int) -> float:
    """Blend from ``first_value`` at level 1 to ``top_value`` at ``top_level``.

    Levels outside ``[1, top_level]`` yield the nearer end value. A
    ``top_level`` of 1 or less yields ``first_value``.
    """
    fraction = 0.0 if top_level <= 1 else (level - 1) / (top_level - 1)
    if fraction < 0.0:
        fraction = 0.0
    elif fraction > 1.0:
        fraction = 1.0
    return first_value + (top_value - first_value) * fraction


def level_lerp_int(level: int, first_value: int, top_value: int, top_level: int) -> int:
    """``level_lerp`` rounded to the nearest whole number, halves rounding up."""
    return math.floor(level_lerp(level, first_value, top_value, top_level) + 0.5)
