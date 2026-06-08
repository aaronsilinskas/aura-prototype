"""Motion detection utilities for the Red Light Green Light mini-game.

``motion_magnitude`` computes the non-gravitational acceleration magnitude
from an ``AccelerationData`` snapshot.  ``smooth_motion`` folds successive
magnitudes into an exponential moving average so a single noisy spike cannot
end the game while genuine, sustained motion still registers.  All values are
in m/s².
"""

from __future__ import annotations

import math

try:
    from typing import Final
except ImportError:
    pass

from engine.input import AccelerationData

RED_MAX_MOTION_THRESHOLD: Final = 0.25
"""Player must not exceed this magnitude (m/s²) during a Red Light phase."""

GREEN_MIN_MOTION_THRESHOLD: Final = 1.0
"""Player must exceed this magnitude (m/s²) to count as moving on Green Light."""

MOTION_EMA_ALPHA: Final = 0.35
"""Default smoothing factor for :func:`smooth_motion` (0 < alpha ≤ 1).

Lower values average over more samples — stronger spike rejection but slower to
react; 1.0 disables smoothing entirely.  Tunable per scene via the
``rlgl_motion_smoothing`` GameState key.
"""


def motion_magnitude(accel: AccelerationData) -> float:
    """Return the non-gravitational acceleration magnitude in m/s².

    Computed as ``max(0.0, sqrt(x² + y² + z²) - GRAVITY)``.  The ``max``
    clamp prevents negative results (e.g. sensor dropout during free fall).
    """
    raw = math.sqrt(accel.x * accel.x + accel.y * accel.y + accel.z * accel.z)
    return max(0.0, raw - AccelerationData.GRAVITY)


def smooth_motion(
    previous: float,
    accel: AccelerationData,
    alpha: float = MOTION_EMA_ALPHA,
) -> float:
    """Fold one sample into an exponential moving average of motion magnitude.

    Returns ``alpha * motion_magnitude(accel) + (1 - alpha) * previous``.  A
    lone spike contributes only ``alpha`` of its magnitude, so it cannot cross
    a threshold on its own, while sustained motion accumulates across samples
    and converges toward the true magnitude.  Allocation-free for hot paths.
    """
    return alpha * motion_magnitude(accel) + (1.0 - alpha) * previous
