"""Motion detection utilities for the Red Light Green Light mini-game.

``motion_magnitude`` computes the non-gravitational acceleration magnitude
from an ``AccelerationData`` snapshot.  All values are in m/s².
"""

from __future__ import annotations

import math

try:
    from typing import Final
except ImportError:
    pass

from engine.input import AccelerationData

RED_MAX_MOTION_THRESHOLD: Final = 1.5
"""Player must not exceed this magnitude (m/s²) during a Red Light phase."""

GREEN_MIN_MOTION_THRESHOLD: Final = 1.0
"""Player must exceed this magnitude (m/s²) to count as moving on Green Light."""


def motion_magnitude(accel: AccelerationData) -> float:
    """Return the non-gravitational acceleration magnitude in m/s².

    Computed as ``max(0.0, sqrt(x² + y² + z²) - GRAVITY)``.  The ``max``
    clamp prevents negative results (e.g. sensor dropout during free fall).
    """
    raw = math.sqrt(accel.x**2 + accel.y**2 + accel.z**2)
    return max(0.0, raw - AccelerationData.GRAVITY)
