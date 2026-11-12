"""The Effect Level: an effect's build-time intensity in the range [1, 10].

Builders interpolate across it with ``engine.lerp.level_lerp``, passing
``EFFECT_TOP_LEVEL``."""

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
