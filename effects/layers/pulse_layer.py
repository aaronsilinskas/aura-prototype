from effects.layers.layer import Layer


class PulseLayer(Layer):
    """Four-phase brightness oscillator: brighten → on → darken → off.

    Returns brightness in ``[0.0, 1.0]`` from ``sample()``, suitable for
    driving a two-stop palette that maps ``0.0`` to a start color and ``1.0``
    to an end color.

    Update model:
      - Call ``update(elapsed)`` once per frame. ``_elapsed`` wraps via
        modulo to prevent float drift on long-running devices.
    Sampling model:
      - ``sample()`` returns the same brightness for every position; both
        ``position`` and ``pixel_count`` are ignored.
    """

    __slots__ = ["_b_darken", "_b_off", "_b_on", "_cycle_total", "_elapsed"]

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

    def update(self, elapsed: float) -> None:
        """Advance phase by ``elapsed`` seconds, wrapping within the cycle."""
        self._elapsed = (self._elapsed + elapsed) % self._cycle_total

    def sample(self, position: float, pixel_count: int) -> float:
        """Return current brightness in ``[0.0, 1.0]``; position is ignored."""
        elapsed = self._elapsed
        if elapsed < self._b_on:
            return elapsed / self._b_on
        if elapsed < self._b_darken:
            return 1.0
        if elapsed < self._b_off:
            return 1.0 - (elapsed - self._b_darken) / (self._b_off - self._b_darken)
        return 0.0
