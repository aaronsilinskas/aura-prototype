import random

from effects.effect import EffectState, EffectStep, EffectTimer
from effects.value import DynamicValue, lerp
from effects.value import ValueGenerator as VG


class SparkleStep(EffectStep):
    """Overlays randomly spawning sparkles that fade in and out across the strip.

    Sparkles occupy non-overlapping positions and blend additively into the
    output value.
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
        pixel_count: int,
    ):
        self.sparkle_count = max(0, int(VG.resolve(sparkle_count)))
        self.buffer_count = max(1, max(pixel_count, self.sparkle_count * 2))
        self.spawn_delay_rate = spawn_delay_rate
        self.fade_in_rate = VG.resolve(fade_in_rate)
        self.fade_out_rate = VG.resolve(fade_out_rate)
        self._buffer_range = range(self.buffer_count)
        self._sparkle_range = range(self.sparkle_count)

    class _Data:
        __slots__ = ("buffer", "indices", "intensity", "phase", "slot_index", "spawn_delay")

        def __init__(self, sparkle_count: int, buffer_count: int):
            self.indices: set[int] = set()
            self.slot_index = [0] * sparkle_count
            self.intensity = [0.0] * sparkle_count
            self.phase = bytearray(sparkle_count)
            self.spawn_delay = [0.0] * sparkle_count
            self.buffer = [0.0] * buffer_count

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        data = state.get_step_data(self, SparkleStep._Data)
        if data is None:
            data = self._Data(self.sparkle_count, self.buffer_count)
            for i in range(self.sparkle_count):
                data.spawn_delay[i] = VG.resolve(self.spawn_delay_rate)
            state.set_step_data(self, data)

        for i in self._buffer_range:
            data.buffer[i] = 0.0

        for i in self._sparkle_range:
            phase = data.phase[i]
            intensity = data.intensity[i]

            if phase == self.PHASE_IDLE:
                remaining_delay = data.spawn_delay[i] - timer.elapsed
                data.spawn_delay[i] = remaining_delay
                if remaining_delay <= 0.0:
                    center_index = random.randint(0, self.buffer_count - 1)
                    while center_index in data.indices:
                        center_index = random.randint(0, self.buffer_count - 1)

                    data.phase[i] = self.PHASE_FADE_IN
                    data.intensity[i] = 0.0
                    data.spawn_delay[i] = 0.0
                    data.slot_index[i] = center_index
                    data.indices.add(center_index)
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
                    data.indices.discard(data.slot_index[i])

            data.intensity[i] = intensity
            data.phase[i] = phase

            if phase == self.PHASE_IDLE or intensity <= 0.0:
                continue

            center_index = data.slot_index[i]
            current = data.buffer[center_index]
            if intensity > current:
                data.buffer[center_index] = intensity

        return True

    def adjust_value(self, state: EffectState, position: float, value: float) -> float:
        data = state.get_step_data(self, SparkleStep._Data)
        if data is not None:
            sparkle_offset = position * self.buffer_count
            left_index = int(sparkle_offset) % self.buffer_count
            right_index = (left_index + 1) % self.buffer_count
            index_weight = sparkle_offset % 1.0

            sparkle_value = lerp(
                data.buffer[left_index],
                data.buffer[right_index],
                index_weight,
            )
            value += sparkle_value

        return value


def sparkle(
    sparkle_count: DynamicValue = 3,
    spawn_delay_rate: DynamicValue = 2.5,
    fade_in_rate: DynamicValue = 1.0,
    fade_out_rate: DynamicValue = 1.0,
    pixel_count: int = 16,
) -> EffectStep:
    """Return a step that overlays fading sparkles onto the effect output."""
    return SparkleStep(
        sparkle_count=sparkle_count,
        spawn_delay_rate=spawn_delay_rate,
        fade_in_rate=fade_in_rate,
        fade_out_rate=fade_out_rate,
        pixel_count=pixel_count,
    )
