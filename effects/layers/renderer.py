from effects.layers.layer import Layer
from effects.palette import Palette
from effects.render import EffectRenderer, PixelBuffer


class LayerRenderer(EffectRenderer):
    """Composes any simulation layer and a Palette into a renderer.

    ``layer`` is any object exposing ``update(elapsed: float)`` and
    ``sample(position: float, pixel_count: int) -> float`` — for example
    ``FlameLayer``, ``DriftNoiseLayer``, ``SparkleLayer``, or ``ScrollLayer``.
    """

    __slots__ = ["_layer", "_name", "_palette"]

    def __init__(self, name: str, layer: Layer, palette: Palette) -> None:
        self._name = name
        self._layer = layer
        self._palette = palette

    @property
    def name(self) -> str:
        return self._name

    def update(self, timer) -> None:
        self._layer.update(timer.elapsed)

    def render(self, output: PixelBuffer) -> None:
        count = len(output)
        inv_count = 1.0 / count
        layer = self._layer
        palette = self._palette
        for i in range(count):
            output[i] = palette.lookup(layer.sample(i * inv_count, count))
