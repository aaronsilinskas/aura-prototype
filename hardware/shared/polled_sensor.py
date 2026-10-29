"""PolledSensor — the board-free owner of one 3-axis sensor's reading. No board imports."""

from __future__ import annotations

try:
    from collections.abc import Callable
except ImportError:
    pass

from engine.input import AccelerationData, MagneticData
from engine.log import Logger

__all__ = ["RECOVERY_READS", "PolledSensor"]

# Consecutive good reads that end a failing episode: about 2 s at the prop's frame rate.
RECOVERY_READS = 50


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

    Failures are logged to *logger* on transitions only, labelled with
    *label*: one line carrying the error when a healthy sensor's read fails,
    and one line with the episode's failed and total read counts once
    :data:`RECOVERY_READS` consecutive reads succeed. A good read updates the
    reading at once even while failing; only the recovery line waits.
    ``failed_reads`` counts the current episode's failed reads, zero while
    healthy.
    """

    __slots__ = (
        "_episode_reads",
        "_good_run",
        "_label",
        "_logger",
        "_read",
        "failed_reads",
        "reading",
    )

    def __init__(
        self,
        read: Callable[[], tuple[float, float, float]],
        reading: AccelerationData | MagneticData,
        label: str,
        logger: Logger,
    ) -> None:
        self._read = read
        self.reading = reading
        self._label = label
        self._logger = logger
        self.failed_reads = 0
        self._episode_reads = 0
        self._good_run = 0

    def update(self) -> None:
        try:
            x, y, z = self._read()
        except Exception as error:
            if self.failed_reads == 0:
                self._logger.log(f"{self._label} read failing: {error!r}")
            self.failed_reads += 1
            self._episode_reads += 1
            self._good_run = 0
            return
        reading = self.reading
        reading.x = x
        reading.y = y
        reading.z = z
        if self.failed_reads:
            self._episode_reads += 1
            self._good_run += 1
            if self._good_run == RECOVERY_READS:
                failed, total = self.failed_reads, self._episode_reads
                self._logger.log(f"{self._label} recovered: {failed} of {total} reads failed")
                self.failed_reads = 0
                self._episode_reads = 0
                self._good_run = 0
