from effects.palette import Palette
from effects.render import EffectRenderer, PixelBuffer
from packs.effects.elements.helpers.layer import Layer
from packs.effects.elements.helpers.scroll import Scroll


class LayerRenderer(EffectRenderer):
    """Composes any simulation layer, an optional scroll, and a Palette into a renderer.

    ``layer`` is any object exposing ``update(elapsed: float)`` and
    ``sample(position: float, pixel_count: int) -> float`` — for example
    ``FlameLayer``, ``DriftNoiseLayer``, or ``SparkleLayer``.

    ``scroll`` is any object exposing ``update(elapsed: float)`` and
    ``apply(position: float) -> float``. Pass ``None`` for effects that need no
    position drift.

    The ``state`` argument on ``update`` and ``render`` is accepted for
    signature compatibility with ``EffectRenderer`` but is never read.
    """

    __slots__ = ["_layer", "_name", "_palette", "_scroll"]

    def __init__(
        self, name: str, layer: Layer, palette: Palette, scroll: Scroll | None = None
    ) -> None:
        self._name = name
        self._layer = layer
        self._palette = palette
        self._scroll = scroll

    @property
    def name(self) -> str:
        return self._name

    def update(self, state, timer) -> None:
        """Advance scroll (if any) and layer. ``state`` is ignored."""
        elapsed = timer.elapsed
        if self._scroll is not None:
            self._scroll.update(elapsed)
        self._layer.update(elapsed)

    def render(self, state, output: PixelBuffer) -> None:
        """Write palette-mapped layer colors to ``output``. ``state`` is ignored."""
        count = len(output)
        scroll = self._scroll
        buf = self._layer
        palette = self._palette
        for i in range(count):
            pos = i / count
            if scroll is not None:
                pos = scroll.apply(pos)
            output[i] = palette.lookup(buf.sample(pos, count))
