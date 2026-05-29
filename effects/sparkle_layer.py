import random

try:
    from typing import Final
except ImportError:
    pass

from effects.layer import Layer
from effects.value import DynamicValue
from effects.value import ValueGenerator as VG


class SparkleLayer(Layer):
    """Pure sparkle simulation — no rendering, no palette, no EffectStep overhead.

    Maintains a fixed number of sparkle slots, each cycling through idle →
    fade-in → fade-out phases. Call ``update(elapsed)`` each frame, then
    ``sample(position, pixel_count)`` per pixel to get the additive intensity
    contribution at that position.

    ``spawn_delay_rate`` is a ``DynamicValue`` — a plain float or zero-argument
    callable — re-evaluated each time a slot resets to idle, matching the
    contract used by ``SparkleStep``.

    The algorithm is identical to ``SparkleStep``, enabling fair visual
    comparison between the two design approaches.
    """

    PHASE_IDLE: "Final" = 0
    PHASE_FADE_IN: "Final" = 1
    PHASE_FADE_OUT: "Final" = 2

    __slots__ = [
        "_fade_in_rate",
        "_fade_out_rate",
        "_intensity",
        "_phase",
        "_slot_pos",
        "_sparkle_count",
        "_sparkle_range",
        "_spawn_delay",
        "_spawn_delay_rate",
    ]

    def __init__(
        self,
        sparkle_count: int,
        spawn_delay_rate: DynamicValue,
        fade_in_rate: float,
        fade_out_rate: float,
    ) -> None:
        self._sparkle_count = sparkle_count
        self._sparkle_range = range(sparkle_count)
        self._spawn_delay_rate = spawn_delay_rate
        self._fade_in_rate = fade_in_rate
        self._fade_out_rate = fade_out_rate

        self._slot_pos = [0.0] * sparkle_count
        self._intensity = [0.0] * sparkle_count
        self._phase = bytearray(sparkle_count)
        self._spawn_delay = [self._resolve_delay() for _ in range(sparkle_count)]

    def _resolve_delay(self) -> float:
        return VG.resolve(self._spawn_delay_rate)

    def update(self, elapsed: float) -> None:
        """Advance all sparkle slots by ``elapsed`` seconds."""
        intensity = self._intensity
        phase = self._phase
        slot_pos = self._slot_pos
        spawn_delay = self._spawn_delay
        fade_in_rate = self._fade_in_rate
        fade_out_rate = self._fade_out_rate

        for i in self._sparkle_range:
            p = phase[i]
            v = intensity[i]

            if p == self.PHASE_IDLE:
                remaining = spawn_delay[i] - elapsed
                spawn_delay[i] = remaining
                if remaining <= 0.0:
                    phase[i] = self.PHASE_FADE_IN
                    intensity[i] = 0.0
                    spawn_delay[i] = 0.0
                    slot_pos[i] = random.random()
                continue

            if p == self.PHASE_FADE_IN:
                v += fade_in_rate * elapsed
                if v >= 1.0:
                    v = 1.0
                    p = self.PHASE_FADE_OUT
            else:
                v -= fade_out_rate * elapsed
                if v <= 0.0:
                    v = 0.0
                    p = self.PHASE_IDLE
                    spawn_delay[i] = self._resolve_delay()

            intensity[i] = v
            phase[i] = p

    def sample(self, position: float, pixel_count: int) -> float:
        """Return the additive sparkle contribution at ``position``.

        Uses the same one-pixel linear falloff as ``SparkleStep``.
        """
        result = 0.0
        pixel_pos = position * pixel_count
        intensity = self._intensity
        phase = self._phase
        slot_pos = self._slot_pos

        for i in self._sparkle_range:
            if phase[i] == self.PHASE_IDLE or intensity[i] <= 0.0:
                continue
            dist = abs(pixel_pos - slot_pos[i] * pixel_count)
            if dist < 1.0:
                result += intensity[i] * (1.0 - dist)

        return result
