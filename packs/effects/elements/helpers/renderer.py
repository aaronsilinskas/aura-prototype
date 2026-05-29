from effects.palette import Palette
from effects.render import EffectRenderer, PixelBuffer
from packs.effects.elements.helpers.layer import Layer


class LayerRenderer(EffectRenderer):
    """Composes any simulation layer and a Palette into a renderer.

    ``layer`` is any object exposing ``update(elapsed: float)`` and
    ``sample(position: float, pixel_count: int) -> float`` — for example
    ``FlameLayer``, ``DriftNoiseLayer``, ``SparkleLayer``, or ``ScrollLayer``.

    The ``state`` argument on ``update`` and ``render`` is accepted for
    signature compatibility with ``EffectRenderer`` but is never read.
    """

    __slots__ = ["_layer", "_name", "_palette"]

    def __init__(self, name: str, layer: Layer, palette: Palette) -> None:
        self._name = name
        self._layer = layer
        self._palette = palette

    @property
    def name(self) -> str:
        return self._name

    def update(self, state, timer) -> None:
        """Advance the layer. ``state`` is ignored."""
        self._layer.update(timer.elapsed)

    def render(self, state, output: PixelBuffer) -> None:
        """Write palette-mapped layer colors to ``output``. ``state`` is ignored."""
        count = len(output)
        layer = self._layer
        palette = self._palette
        for i in range(count):
            output[i] = palette.lookup(layer.sample(i / count, count))
