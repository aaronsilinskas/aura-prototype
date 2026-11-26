from __future__ import annotations

from engine.state import StateSlot
from packs.scenes.red_light_green_light.rules.helpers.motion_detector import (
    linear_magnitude,
    low_pass,
)

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

    from engine.input import AccelerationData

_MOTION_KEY: Final = "rlgl_motion"


class RlglMotion:
    """Mutable gravity/motion-EMA tracking state for the RLGL scene.

    The gravity estimate is tracked per-axis with a slow low-pass filter and
    subtracted as a vector from each sample so motion reads the same in any
    orientation. It is held in three float fields rather than a tuple so
    :meth:`update` advances it without allocating. "Unseeded" gravity is a
    distinct third state (neither zeroed nor an arbitrary orientation):
    :meth:`reset_gravity` clears the seeded flag so the next :meth:`update`
    call seeds gravity directly from that sample instead of carrying over a
    stale orientation.
    """

    __slots__ = (
        "_gravity_x",
        "_gravity_y",
        "_gravity_z",
        "_seeded",
        "ema",
        "last_motion_time",
    )

    def __init__(self) -> None:
        self._gravity_x = 0.0
        self._gravity_y = 0.0
        self._gravity_z = 0.0
        self._seeded = False
        self.ema = 0.0
        self.last_motion_time = 0.0

    def reset_gravity(self) -> None:
        """Clear the seeded flag so the next :meth:`update` re-seeds gravity."""
        self._seeded = False

    def update(
        self, accel: AccelerationData, gravity_beta: float, motion_smoothing: float
    ) -> float:
        """Advance the gravity estimate and motion EMA from ``accel``; return the EMA.

        On the first call after construction or :meth:`reset_gravity`, gravity
        is seeded directly from ``accel`` (never starts at zero). Subsequent
        calls ease each gravity axis toward ``accel`` by ``gravity_beta``.
        Allocation-free: no tuples, lists, dicts, or objects are created.
        """
        if self._seeded:
            self._gravity_x = low_pass(self._gravity_x, accel.x, gravity_beta)
            self._gravity_y = low_pass(self._gravity_y, accel.y, gravity_beta)
            self._gravity_z = low_pass(self._gravity_z, accel.z, gravity_beta)
        else:
            self._gravity_x = accel.x
            self._gravity_y = accel.y
            self._gravity_z = accel.z
            self._seeded = True

        linear = linear_magnitude(accel, self._gravity_x, self._gravity_y, self._gravity_z)
        self.ema = low_pass(self.ema, linear, motion_smoothing)
        return self.ema


rlgl_motion = StateSlot(_MOTION_KEY, lambda s: RlglMotion(), RlglMotion)
