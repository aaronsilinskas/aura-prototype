from effects.effect import EffectPixels, PixelBuffer
from effects.layers.progress_layer import ProgressLayer


class ProgressEffect(EffectPixels):
    """Renders a :class:`ProgressLayer` over a single raw RGB color.

    The raw ``color`` channels are extracted once in ``__init__``. Per pixel,
    the layer's lit fraction ``f`` is multiplied into each channel inline so no
    ``Palette``/``PaletteLUT256`` is needed — ``f = 0.0`` → ``0x000000``,
    ``f = 1.0`` → the full ``color``, and a boundary ``f`` yields a
    proportionally dimmer (anti-aliased) edge pixel.

    Stateless: ``update`` is a no-op, so re-issuing ``set_effect`` every tick
    is cheap and produces no restart artefacts.
    """

    __slots__ = ("_b", "_g", "_layer", "_r")

    def __init__(self, layer: ProgressLayer, color: int) -> None:
        self._layer = layer
        self._r = (color >> 16) & 0xFF
        self._g = (color >> 8) & 0xFF
        self._b = color & 0xFF

    def update(self, elapsed: float) -> None:
        """No-op — the progress bar is stateless."""

    def render(self, output: PixelBuffer) -> None:
        """Scale the color channels by each pixel's lit fraction and write them."""
        count = len(output)
        inv_count = 1.0 / count
        layer = self._layer
        r = self._r
        g = self._g
        b = self._b
        for i in range(count):
            f = layer.sample(i * inv_count, count)
            output[i] = (int(r * f) << 16) | (int(g * f) << 8) | int(b * f)
