"""User-facing intensity levels in the range [1, 10] and helpers to map them
to normalized floats and interpolated values."""


def clamp_level(level: int) -> int:
    """Clamp ``level`` to the valid range ``[1, 10]``."""
    if level < 1:
        return 1
    if level > 10:
        return 10
    return level


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
