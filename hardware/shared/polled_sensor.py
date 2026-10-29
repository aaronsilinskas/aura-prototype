"""PolledSensor — the board-free owner of one 3-axis sensor's reading. No board imports."""

from __future__ import annotations

try:
    from collections.abc import Callable
except ImportError:
    pass

from engine.input import AccelerationData, MagneticData

__all__ = ["PolledSensor"]


class PolledSensor:
    """Refreshes one 3-axis sensor's reading from its raw read source, once per ``update()``.

    *read* is a :class:`~hardware.shared.device_parts.DeviceParts` raw read
    source: it returns ``(x, y, z)`` and may raise. Any ``Exception`` it
    raises leaves the reading untouched, so a glitch keeps the last good
    reading and never takes down the frame loop.

    ``reading`` is the *reading* buffer passed in, the same object for the
    sensor's whole life, so a sensor event can hold it once and see every
    update. It keeps whatever values it was given until the first successful
    read. It is typed as either buffer because ``typing.Generic`` is
    unavailable on CircuitPython; a caller needing one narrows it once, where
    it builds the sensor event.
    """

    __slots__ = ("_read", "reading")

    def __init__(
        self,
        read: Callable[[], tuple[float, float, float]],
        reading: AccelerationData | MagneticData,
    ) -> None:
        self._read = read
        self.reading = reading

    def update(self) -> None:
        try:
            x, y, z = self._read()
        except Exception:
            return
        reading = self.reading
        reading.x = x
        reading.y = y
        reading.z = z
