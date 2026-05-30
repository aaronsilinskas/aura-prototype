from effects.layers.layer import Layer
from effects.palette import Palette
from effects.render import Effect, PixelBuffer


class AddSamplesRenderer(Effect):
    """Blends multiple layers by summing their sample values and applying a single palette.

    Per-pixel: sums ``layer.sample(pos, count)`` across all layers, clamps the
    total to ``1.0``, then maps through a single shared palette.
    """

    __slots__ = ["_layers", "_name", "_palette"]

    def __init__(self, name: str, layers: list[Layer], palette: Palette) -> None:
        self._name = name
        self._layers = layers
        self._palette = palette

    @property
    def name(self) -> str:
        return self._name

    def update(self, elapsed: float) -> None:
        """Advance all layers by ``elapsed`` seconds."""
        for layer in self._layers:
            layer.update(elapsed)

    def render(self, output: PixelBuffer) -> None:
        """Sum layer samples per pixel, clamp to ``1.0``, and write palette-mapped colors."""
        count = len(output)
        inv_count = 1.0 / count
        palette = self._palette
        layers = self._layers
        for i in range(count):
            pos = i * inv_count
            total = 0.0
            for layer in layers:
                total += layer.sample(pos, count)
            if total > 1.0:
                total = 1.0
            output[i] = palette.lookup(total)
