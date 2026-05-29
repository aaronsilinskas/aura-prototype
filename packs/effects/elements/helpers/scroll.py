import random

from effects.value import lerp


class Scroll:
    """Base interface for position scroll helpers.

    All concrete subclasses must implement ``update`` and ``apply``.

    Uses ``raise NotImplementedError`` rather than ``abc.ABC`` /
    ``@abstractmethod`` for CircuitPython compatibility.
    """

    __slots__ = []

    def update(self, elapsed: float) -> None:
        """Advance scroll state by ``elapsed`` seconds."""
        raise NotImplementedError

    def apply(self, position: float) -> float:
        """Return the scrolled position for a normalised input in ``[0.0, 1.0)``."""
        raise NotImplementedError


class ScrollOffset(Scroll):
    """Constant-speed position scroll.

    Call ``update(elapsed)`` each frame to accumulate the offset, then
    ``apply(position)`` per pixel to shift the sample position.
    """

    __slots__ = ["_offset", "_speed"]

    def __init__(self, speed: float) -> None:
        self._speed = speed
        self._offset = 0.0

    def update(self, elapsed: float) -> None:
        self._offset = (self._offset + self._speed * elapsed) % 1.0

    def apply(self, position: float) -> float:
        return (position + self._offset) % 1.0


class PhaseScroll(Scroll):
    """Position scroll that periodically picks a new random direction.

    Each phase lasts ``min_phase``–``max_phase`` seconds. At the end of each
    phase a new target speed is chosen (``±speed``). The current speed lerps
    smoothly from the previous phase's terminal value to the new target over
    the next phase, matching the ``AccelerateStep`` behaviour in the
    step-based water effect.
    """

    __slots__ = [
        "_current_speed",
        "_max_phase",
        "_min_phase",
        "_offset",
        "_phase_duration",
        "_phase_elapsed",
        "_speed",
        "_start_speed",
        "_target_speed",
    ]

    def __init__(self, speed: float, min_phase: float, max_phase: float) -> None:
        self._speed = speed
        self._min_phase = min_phase
        self._max_phase = max_phase
        self._offset = 0.0
        self._current_speed = 0.0
        self._start_speed = 0.0
        self._target_speed = speed * (1 if random.random() < 0.5 else -1)
        self._phase_elapsed = 0.0
        self._phase_duration = random.uniform(min_phase, max_phase)

    def update(self, elapsed: float) -> None:
        self._phase_elapsed += elapsed
        if self._phase_elapsed >= self._phase_duration:
            self._start_speed = self._current_speed
            self._target_speed = self._speed * (1 if random.random() < 0.5 else -1)
            self._phase_elapsed = 0.0
            self._phase_duration = random.uniform(self._min_phase, self._max_phase)

        progress = self._phase_elapsed / self._phase_duration
        self._current_speed = lerp(self._start_speed, self._target_speed, progress)
        self._offset = (self._offset + self._current_speed * elapsed) % 1.0

    def apply(self, position: float) -> float:
        return (position + self._offset) % 1.0
