"""Motion detection utilities for the Red Light Green Light mini-game.

Motion is isolated from gravity *vectorially*: a slowly-tracked gravity estimate
is subtracted from each acceleration sample, so :func:`linear_magnitude` is
equally sensitive to motion in any direction (subtracting the gravity *scalar*
would suppress motion perpendicular to gravity).  :func:`low_pass` is the shared
one-pole filter used both to track gravity and to smooth the motion signal for
spike rejection.  All values are in m/s².
"""

from __future__ import annotations

import math

try:
    from typing import Final
except ImportError:
    pass

from engine.input import AccelerationData

RED_MAX_MOTION_THRESHOLD: Final = 0.35
"""Player must not exceed this magnitude (m/s²) during a Red Light phase."""

GREEN_MIN_MOTION_THRESHOLD: Final = 2.0
"""Player must exceed this magnitude (m/s²) to count as moving on Green Light."""

MOTION_EMA_ALPHA: Final = 0.35
"""Default smoothing factor for the motion signal (0 < alpha ≤ 1).

Lower values average over more samples — stronger spike rejection but slower to
react; 1.0 disables smoothing entirely.  Tunable per scene via the
``rlgl_motion_smoothing`` GameState key.
"""

GRAVITY_LOWPASS_BETA: Final = 0.1
"""Tracking rate for the gravity estimate (0 < beta ≤ 1).

Each axis eases toward the raw reading by this fraction per sample, so gravity
follows slow orientation changes while leaving brief motion in the residual.
Must stay well below ``MOTION_EMA_ALPHA`` or real motion gets absorbed into the
gravity estimate before it registers.  Tunable via ``rlgl_gravity_beta``.
"""


def low_pass(previous: float, sample: float, factor: float) -> float:
    """Ease ``previous`` toward ``sample`` by ``factor`` (a one-pole low-pass / EMA).

    Returns ``factor * sample + (1 - factor) * previous``.  ``factor`` of 1.0
    snaps to ``sample`` (no smoothing); smaller values track more slowly.
    Allocation-free for hot paths.
    """
    return factor * sample + (1.0 - factor) * previous


def linear_magnitude(accel: AccelerationData, gx: float, gy: float, gz: float) -> float:
    """Magnitude (m/s²) of ``accel`` with the gravity vector ``(gx, gy, gz)`` removed.

    Orientation-independent: because gravity is subtracted as a vector before
    taking the magnitude, the same physical motion reads the same whether it is
    aligned with or perpendicular to gravity.  Always non-negative (it is a
    vector magnitude), so no clamping is needed.  Allocation-free for hot paths.
    """
    dx = accel.x - gx
    dy = accel.y - gy
    dz = accel.z - gz
    return math.sqrt(dx * dx + dy * dy + dz * dz)
