import random

from effects.effect import EffectState, EffectStep, EffectTimer
from effects.value import DynamicValue, lerp
from effects.value import ValueGenerator as VG


class DriftNoiseStep(EffectStep):
    """Adds drifting random noise to the output value, creating an organic shimmer.

    A fixed-size noise buffer is initialized once and slowly scrolled each frame
    at ``drift_speed``. Each pixel samples the buffer with linear interpolation,
    so the noise appears to flow rather than flicker.
    """

    def __init__(
        self,
        resolution: int,
        drift_speed: DynamicValue,
        amplitude: DynamicValue,
    ):
        self.buffer_count = max(1, resolution)
        self.drift_speed = VG.resolve(drift_speed)
        self.amplitude = VG.resolve(amplitude)

    class _Data:
        __slots__ = ("noise", "offset")

        def __init__(self, buffer_count: int):
            self.noise = [0.0] * buffer_count
            self.offset = 0.0

            for i in range(buffer_count):
                self.noise[i] = random.random()

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        data = state.get_step_data(self, DriftNoiseStep._Data)
        if data is None:
            data = self._Data(self.buffer_count)
            state.set_step_data(self, data)

        data.offset += self.drift_speed * timer.elapsed * self.buffer_count
        data.offset %= self.buffer_count

        return True

    def adjust_value(self, state: EffectState, position: float, value: float) -> float:
        data = state.get_step_data(self, DriftNoiseStep._Data)
        if data is None:
            return value

        sample_index = (position * self.buffer_count + data.offset) % self.buffer_count

        left_index = int(sample_index)
        right_index = (left_index + 1) % self.buffer_count
        weight = sample_index - left_index

        sample = lerp(data.noise[left_index], data.noise[right_index], weight)
        return value + sample * self.amplitude


def drift_noise(
    resolution: int = 24,
    drift_speed: DynamicValue = 0.04,
    amplitude: DynamicValue = 0.2,
) -> EffectStep:
    """Return a step that overlays drifting noise with the given ``amplitude``."""
    return DriftNoiseStep(
        resolution=resolution,
        drift_speed=drift_speed,
        amplitude=amplitude,
    )
