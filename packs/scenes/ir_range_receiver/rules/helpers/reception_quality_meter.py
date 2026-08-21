"""``ReceptionQualityMeter`` -- pure, hardware-free IR link-quality classifier.

No ``board``/``pulseio`` import; CircuitPython/MicroPython-safe. Fed
``(sequence, timestamp)`` arrivals via :meth:`record` and a per-tick ``now``
via :meth:`evaluate`, it reports a rolling-window reception rate that is
cadence-independent: ``expected`` is derived from the span between the
lowest and highest sequence seen within the window, never from an assumed
transmit rate.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # Not available on all embedded runtimes

__all__ = [
    "COLOR_GREEN",
    "COLOR_RED",
    "COLOR_YELLOW",
    "STATE_NONE",
    "STATE_PARTIAL",
    "STATE_PERFECT",
    "ReceptionQuality",
    "ReceptionQualityMeter",
]

STATE_PERFECT: Final = "perfect"
STATE_PARTIAL: Final = "partial"
STATE_NONE: Final = "none"

COLOR_GREEN: Final = 0x00FF00
COLOR_YELLOW: Final = 0xFFFF00
COLOR_RED: Final = 0xFF0000

_SEQUENCE_MODULUS: Final = 256


class ReceptionQuality:
    """One :meth:`ReceptionQualityMeter.evaluate` result -- rendered as-is, no further logic.

    ``progress`` is the raw reception rate in ``[0.0, 1.0]`` (``0.0`` when
    ``state`` is ``STATE_NONE``, where there is no meaningful rate).
    ``received``/``dropped`` are the window's raw packet counts, for the
    rule's periodic serial print.
    """

    __slots__ = ("color", "dropped", "progress", "received", "state")

    def __init__(
        self, state: str, progress: float, color: int, received: int, dropped: int
    ) -> None:
        self.state = state
        self.progress = progress
        self.color = color
        self.received = received
        self.dropped = dropped


class ReceptionQualityMeter:
    """Rolling-window IR reception-quality classifier.

    ``record`` is called once per ``NetworkEvents.IRReceived`` arrival;
    ``evaluate`` is called once per tick from the per-tick heartbeat
    (``InputEvents.Sensors``) and both recomputes the meter and applies the
    time-based silence timeout -- the only way "packets stopped" can ever be
    detected, since no more ``IRReceived`` events will ever arrive to signal it.
    """

    __slots__ = (
        "_gaps",
        "_green_threshold",
        "_last_sequence",
        "_last_timestamp",
        "_none_result",
        "_silence_timeout",
        "_timestamps",
        "_total_distance",
        "_window_seconds",
    )

    def __init__(
        self, window_seconds: float, silence_timeout: float, green_threshold: float
    ) -> None:
        self._window_seconds = window_seconds
        self._silence_timeout = silence_timeout
        self._green_threshold = green_threshold
        self._timestamps: list[float] = []
        # _gaps[i] is the modulo-256 sequence gap from the previous recorded
        # arrival into entry i; _gaps[0] is always the "boundary" gap into an
        # arrival from before the current window and is excluded from
        # _total_distance (see _prune).
        self._gaps: list[int] = []
        self._last_sequence: int | None = None
        self._last_timestamp: float | None = None
        self._total_distance: int = 0
        # Cached singleton: the silence/boot path returns this instance
        # directly rather than constructing a fresh one, so it allocates
        # nothing on the (by far most common) no-packet tick.
        self._none_result = ReceptionQuality(STATE_NONE, 0.0, COLOR_RED, 0, 0)

    def record(self, sequence: int, timestamp: float) -> None:
        """Record one IR arrival's sequence number and tick timestamp."""
        if self._last_sequence is None:
            gap = 0
        else:
            gap = (sequence - self._last_sequence) % _SEQUENCE_MODULUS
            self._total_distance += gap
        self._last_sequence = sequence
        self._last_timestamp = timestamp
        self._timestamps.append(timestamp)
        self._gaps.append(gap)

    def evaluate(self, now: float) -> ReceptionQuality:
        """Recompute reception quality as of *now*, applying the silence timeout first."""
        if self._last_timestamp is None or (now - self._last_timestamp) > self._silence_timeout:
            return self._none_result

        self._prune(now)

        received = len(self._timestamps)
        expected = self._total_distance + 1
        dropped = expected - received
        rate = received / expected

        if rate >= self._green_threshold:
            return ReceptionQuality(STATE_PERFECT, rate, COLOR_GREEN, received, dropped)
        return ReceptionQuality(STATE_PARTIAL, rate, COLOR_YELLOW, received, dropped)

    def _prune(self, now: float) -> None:
        """Drop arrivals older than the rolling window, always keeping the latest."""
        cutoff = now - self._window_seconds
        timestamps = self._timestamps
        gaps = self._gaps
        while len(timestamps) > 1 and timestamps[0] < cutoff:
            timestamps.pop(0)
            gaps.pop(0)
            if gaps:
                # The entry that is now the window's first arrival had its gap
                # recorded as an internal transition; with its predecessor
                # gone, that gap becomes the new boundary and must be
                # excluded from the window's distance the same way _gaps[0]
                # already was.
                self._total_distance -= gaps[0]
