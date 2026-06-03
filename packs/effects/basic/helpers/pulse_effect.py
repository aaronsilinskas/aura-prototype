from effects.effect import Effect, EffectConfig, PixelBuffer
from effects.layers.pulse_layer import PulseLayer
from effects.palette import Palette


class PulseEffect(Effect):
    """Wraps a :class:`PulseLayer` with peak-event notification.

    On each ``update()`` call, if the layer's ``at_peak`` flag is set,
    ``config.notify_listeners("peak")`` is called exactly once. Pixel
    rendering delegates to the same per-pixel palette lookup as
    :class:`~effects.layers.renderer.LayerRenderer`.
    """

    __slots__ = ("_config", "_layer", "_name", "_palette")

    def __init__(
        self,
        name: str,
        layer: PulseLayer,
        palette: Palette,
        config: EffectConfig,
    ) -> None:
        self._name = name
        self._layer = layer
        self._palette = palette
        self._config = config

    @property
    def name(self) -> str:
        return self._name

    def update(self, elapsed: float) -> None:
        """Advance the layer and fire a peak event if a peak was crossed."""
        self._layer.update(elapsed)
        if self._layer.at_peak:
            self._config.notify_listeners("peak")

    def render(self, output: PixelBuffer) -> None:
        """Sample the layer at each pixel position and write palette-mapped colors."""
        count = len(output)
        inv_count = 1.0 / count
        layer = self._layer
        palette = self._palette
        for i in range(count):
            output[i] = palette.lookup(layer.sample(i * inv_count, count))
