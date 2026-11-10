try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

from effects.effect import EffectConfig, EffectPixels, EffectVerb, PixelBuffer
from effects.layers.pulse_layer import PulseLayer
from effects.palette import Palette


class PulseEffect(EffectPixels):
    """Wraps a :class:`PulseLayer`, emitting ``PEAK`` each time the pulse peaks."""

    PEAK: Final = EffectVerb("peak")
    VERBS: tuple[EffectVerb, ...] = (PEAK,)

    __slots__ = ("_config", "_layer", "_palette")

    def __init__(
        self,
        layer: PulseLayer,
        palette: Palette,
        config: EffectConfig,
    ) -> None:
        self._layer = layer
        self._palette = palette
        self._config = config

    def update(self, elapsed: float) -> None:
        """Advance the layer and emit ``PEAK`` if a peak was crossed."""
        self._layer.update(elapsed)
        if self._layer.at_peak:
            self._config.notify_listeners(self.PEAK)

    def render(self, output: PixelBuffer) -> None:
        count = len(output)
        inv_count = 1.0 / count
        layer = self._layer
        palette = self._palette
        for i in range(count):
            output[i] = palette.lookup(layer.sample(i * inv_count, count))
