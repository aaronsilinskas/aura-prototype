from math import floor

from effects.layers.layer import Layer


class PulseLayer(Layer):
    """Four-phase brightness oscillator: brighten → on → darken → off.

    Returns brightness in ``[0.0, 1.0]`` from ``sample()``, suitable for
    driving a two-stop palette that maps ``0.0`` to a start color and ``1.0``
    to an end color.

    Update model:
      - Call ``update(elapsed)`` once per frame. ``_elapsed`` is a raw,
        monotonically increasing accumulator, never reduced modulo the cycle,
        so the interval-crossing detection below stays correct across cycle
        boundaries; ``update`` applies the modulo locally to pick the phase.
      - ``at_peak`` is set to ``True`` on the tick when the cursor reaches the
        end of the brighten phase (via interval-crossing detection).
    Sampling model:
      - ``sample()`` returns the same brightness for every position; both
        ``position`` and ``pixel_count`` are ignored.
    """

    __slots__ = (
        "_brighten_end",
        "_brightness",
        "_cycle_total",
        "_darken_end",
        "_elapsed",
        "_on_end",
        "at_peak",
    )

    def __init__(
        self,
        brighten_duration: float,
        on_duration: float,
        darken_duration: float,
        off_duration: float,
    ) -> None:
        """Build a pulse from its four phase durations, in seconds.

        Raises ``ValueError`` if any duration is negative or all four are zero.
        """
        if brighten_duration < 0 or on_duration < 0 or darken_duration < 0 or off_duration < 0:
            raise ValueError("Pulse durations must be non-negative")
        self._brighten_end = brighten_duration
        self._on_end = brighten_duration + on_duration
        self._darken_end = self._on_end + darken_duration
        self._cycle_total = self._darken_end + off_duration
        if self._cycle_total == 0.0:
            raise ValueError("At least one pulse phase duration must be non-zero")
        self._elapsed = 0.0
        self._brightness = 0.0
        self.at_peak = False

    def update(self, elapsed: float) -> None:
        """Advance phase by ``elapsed`` seconds. ``_elapsed`` is a raw accumulator."""
        prev = self._elapsed
        self._elapsed = prev + elapsed
        cycle_total = self._cycle_total
        brighten_end = self._brighten_end
        self.at_peak = floor((self._elapsed - brighten_end) / cycle_total) > floor(
            (prev - brighten_end) / cycle_total
        )
        e = self._elapsed % cycle_total
        on_end = self._on_end
        darken_end = self._darken_end
        if e < brighten_end:
            self._brightness = e / brighten_end
        elif e < on_end:
            self._brightness = 1.0
        elif e < darken_end:
            self._brightness = 1.0 - (e - on_end) / (darken_end - on_end)
        else:
            self._brightness = 0.0

    def sample(self, position: float, pixel_count: int) -> float:
        """Return current brightness in ``[0.0, 1.0]``; position is ignored."""
        return self._brightness
