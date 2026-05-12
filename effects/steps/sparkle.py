import random

from effects.effect import EffectState, EffectStep, EffectTimer
from effects.value import DynamicValue
from effects.value import ValueGenerator as VG


class SparkleStep(EffectStep):
    """Overlays randomly spawning sparkles that fade in and out across the strip.

    Each sparkle is placed at a random normalized position in ``[0.0, 1.0)``
    and blends additively into the output value. In ``adjust_value``, the
    ``pixel_count`` argument is used to compute the distance (in pixels)
    between the sample position and each active sparkle; sparkles contribute
    with linear falloff over one pixel of distance.
    """

    PHASE_IDLE = 0
    PHASE_FADE_IN = 1
    PHASE_FADE_OUT = 2

    def __init__(
        self,
        sparkle_count: DynamicValue,
        spawn_delay_rate: DynamicValue,
        fade_in_rate: DynamicValue,
        fade_out_rate: DynamicValue,
    ):
        self.sparkle_count = max(0, int(VG.resolve(sparkle_count)))
        self.spawn_delay_rate = spawn_delay_rate
        self.fade_in_rate = VG.resolve(fade_in_rate)
        self.fade_out_rate = VG.resolve(fade_out_rate)
        self._sparkle_range = range(self.sparkle_count)

    class _Data:
        __slots__ = ("intensity", "phase", "slot_pos", "spawn_delay")

        def __init__(self, sparkle_count: int):
            self.slot_pos = [0.0] * sparkle_count
            self.intensity = [0.0] * sparkle_count
            self.phase = bytearray(sparkle_count)
            self.spawn_delay = [0.0] * sparkle_count

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        data = state.get_step_data(self, SparkleStep._Data)
        if data is None:
            data = self._Data(self.sparkle_count)
            for i in range(self.sparkle_count):
                data.spawn_delay[i] = VG.resolve(self.spawn_delay_rate)
            state.set_step_data(self, data)

        for i in self._sparkle_range:
            phase = data.phase[i]
            intensity = data.intensity[i]

            if phase == self.PHASE_IDLE:
                remaining_delay = data.spawn_delay[i] - timer.elapsed
                data.spawn_delay[i] = remaining_delay
                if remaining_delay <= 0.0:
                    data.phase[i] = self.PHASE_FADE_IN
                    data.intensity[i] = 0.0
                    data.spawn_delay[i] = 0.0
                    data.slot_pos[i] = random.random()
                continue

            if phase == self.PHASE_FADE_IN:
                intensity += self.fade_in_rate * timer.elapsed
                if intensity >= 1.0:
                    intensity = 1.0
                    phase = self.PHASE_FADE_OUT
            else:
                intensity -= self.fade_out_rate * timer.elapsed
                if intensity <= 0.0:
                    intensity = 0.0
                    phase = self.PHASE_IDLE
                    data.spawn_delay[i] = VG.resolve(self.spawn_delay_rate)

            data.intensity[i] = intensity
            data.phase[i] = phase

        return True

    def adjust_value(
        self, state: EffectState, position: float, pixel_count: int, value: float
    ) -> float:
        data = state.get_step_data(self, SparkleStep._Data)
        if data is not None:
            pixel_pos = position * pixel_count
            for i in self._sparkle_range:
                if data.phase[i] == self.PHASE_IDLE or data.intensity[i] <= 0.0:
                    continue
                dist = abs(pixel_pos - data.slot_pos[i] * pixel_count)
                if dist < 1.0:
                    value += data.intensity[i] * (1.0 - dist)
        return value


def sparkle(
    sparkle_count: DynamicValue = 3,
    spawn_delay_rate: DynamicValue = 2.5,
    fade_in_rate: DynamicValue = 1.0,
    fade_out_rate: DynamicValue = 1.0,
) -> EffectStep:
    """Return a step that overlays fading sparkles onto the effect output."""
    return SparkleStep(
        sparkle_count=sparkle_count,
        spawn_delay_rate=spawn_delay_rate,
        fade_in_rate=fade_in_rate,
        fade_out_rate=fade_out_rate,
    )
