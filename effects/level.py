"""The Effect Level: an effect's build-time intensity in the range [1, 10],
plus helpers to map it to normalized floats and interpolated values."""

from __future__ import annotations

from effects.effect import EffectConfig

EFFECT_TOP_LEVEL = 10


def clamp_level(level: int) -> int:
    """Clamp ``level`` to the valid range ``[1, EFFECT_TOP_LEVEL]``."""
    if level < 1:
        return 1
    if level > EFFECT_TOP_LEVEL:
        return EFFECT_TOP_LEVEL
    return level


def effect_level(config: EffectConfig) -> int:
    """Return the effect's ``level`` option clamped to ``[1, 10]``, or 1 if missing."""
    return clamp_level(config.get_option("level", 1))


def level_progress(level: int) -> float:
    """Return ``level`` as a normalized value in ``[0.0, 1.0]``."""
    clamped = clamp_level(level)
    return (clamped - 1) / 9.0


def level_lerp(level: int, minimum: float, maximum: float) -> float:
    """Interpolate between ``minimum`` and ``maximum`` based on ``level``."""
    progress = level_progress(level)
    return minimum + (maximum - minimum) * progress


def level_lerp_int(level: int, minimum: int, maximum: int) -> int:
    """Interpolate between ``minimum`` and ``maximum`` based on ``level``,
    rounded to the nearest int."""
    value = level_lerp(level, float(minimum), float(maximum))
    return int(value + 0.5)
