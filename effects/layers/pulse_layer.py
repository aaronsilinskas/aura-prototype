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
      - ``at_peak`` is set to ``True`` on the tick when the cursor crosses the
        ``_b_on`` boundary (via interval-crossing detection).
    Sampling model:
      - ``sample()`` returns the same brightness for every position; both
        ``position`` and ``pixel_count`` are ignored.
    """

    __slots__ = (
        "_b_darken",
        "_b_off",
        "_b_on",
        "_brightness",
        "_cycle_total",
        "_elapsed",
        "at_peak",
    )

    def __init__(
        self,
        b_on: float,
        b_darken: float,
        b_off: float,
        cycle_total: float,
    ) -> None:
        self._b_on = b_on
        self._b_darken = b_darken
        self._b_off = b_off
        self._cycle_total = cycle_total
        self._elapsed = 0.0
        self._brightness = 0.0
        self.at_peak = False

    def update(self, elapsed: float) -> None:
        """Advance phase by ``elapsed`` seconds. ``_elapsed`` is a raw accumulator."""
        prev = self._elapsed
        self._elapsed = prev + elapsed
        cycle_total = self._cycle_total
        b_on = self._b_on
        self.at_peak = floor((self._elapsed - b_on) / cycle_total) > floor(
            (prev - b_on) / cycle_total
        )
        e = self._elapsed % cycle_total
        b_darken = self._b_darken
        b_off = self._b_off
        if e < b_on:
            self._brightness = e / b_on
        elif e < b_darken:
            self._brightness = 1.0
        elif e < b_off:
            self._brightness = 1.0 - (e - b_darken) / (b_off - b_darken)
        else:
            self._brightness = 0.0

    def sample(self, position: float, pixel_count: int) -> float:
        """Return current brightness in ``[0.0, 1.0]``; position is ignored."""
        return self._brightness
