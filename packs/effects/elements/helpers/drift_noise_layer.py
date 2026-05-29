import random

from effects.value import DynamicValue, lerp
from effects.value import ValueGenerator as VG
from packs.effects.elements.helpers.layer import Layer


class DriftNoiseLayer(Layer):
    """Pure drifting noise simulation — no EffectStep/EffectState overhead.

    A fixed-size noise buffer is initialised once with random values and slowly
    scrolled each frame at ``drift_speed``.  Each call to ``sample`` interpolates
    linearly across the buffer, so the noise flows rather than flickers.

    ``drift_speed`` and ``amplitude`` are resolved once at construction time (if
    callable).  The algorithm is identical to ``DriftNoiseStep``, enabling fair
    visual comparison between the two design approaches.
    """

    __slots__ = ["_amplitude", "_buffer", "_buffer_count", "_drift_speed", "_offset"]

    def __init__(
        self,
        resolution: int,
        drift_speed: DynamicValue,
        amplitude: DynamicValue,
    ) -> None:
        self._buffer_count = max(1, resolution)
        self._drift_speed: float = VG.resolve(drift_speed)
        self._amplitude: float = VG.resolve(amplitude)
        self._offset = 0.0
        self._buffer = [random.random() for _ in range(self._buffer_count)]

    def update(self, elapsed: float) -> None:
        """Advance the scroll offset by ``elapsed`` seconds."""
        self._offset += self._drift_speed * elapsed * self._buffer_count
        self._offset %= self._buffer_count

    def sample(self, position: float, pixel_count: int) -> float:
        """Return drift-noise value at ``position`` in ``[0.0, 1.0]``.

        Returns a value in ``[0.0, amplitude]``.  ``pixel_count`` is accepted for
        interface uniformity with other buffers but is not used.
        """
        buf_count = self._buffer_count
        sample_index = (position * buf_count + self._offset) % buf_count
        left = int(sample_index)
        right = (left + 1) % buf_count
        weight = sample_index - left
        return lerp(self._buffer[left], self._buffer[right], weight) * self._amplitude
