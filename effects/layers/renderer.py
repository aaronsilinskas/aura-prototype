from effects.effect import EffectPixels, PixelBuffer
from effects.layers.layer import Layer
from effects.palette import Palette


class LayerRenderer(EffectPixels):
    """Maps a single Layer's sample values to colors via a Palette.

    Per pixel, samples the layer at the normalised position and maps the result
    through the palette to produce a packed RGB color.

    Update model:
      - ``update(elapsed)`` forwards elapsed time to the inner layer.
    Rendering model:
      - ``render(output)`` writes one palette-mapped color per pixel.
    """

    __slots__ = ["_layer", "_palette"]

    def __init__(self, layer: Layer, palette: Palette) -> None:
        self._layer = layer
        self._palette = palette

    def update(self, elapsed: float) -> None:
        """Advance the inner layer by ``elapsed`` seconds."""
        self._layer.update(elapsed)

    def render(self, output: PixelBuffer) -> None:
        """Sample the layer at each pixel position and write palette-mapped colors to ``output``."""
        count = len(output)
        inv_count = 1.0 / count
        layer = self._layer
        palette = self._palette
        for i in range(count):
            output[i] = palette.lookup(layer.sample(i * inv_count, count))
