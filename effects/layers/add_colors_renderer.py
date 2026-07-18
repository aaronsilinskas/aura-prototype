from effects.effect import EffectPixels, PixelBuffer
from effects.layers.layer import Layer
from effects.palette import Palette


class AddColorsRenderer(EffectPixels):
    """Composes multiple (buffer, palette) layers by additively blending their colors.

    Each layer is a ``(buffer, palette)`` pair. Per-pixel: each layer maps its
    buffer sample to a color via its own palette, then all colors are combined
    by per-channel addition (clamped to 255).
    """

    __slots__ = ["_layers"]

    def __init__(self, layers: list[tuple[Layer, Palette]]) -> None:
        self._layers = layers

    def update(self, elapsed: float) -> None:
        """Advance all layers by ``elapsed`` seconds."""
        for buf, _ in self._layers:
            buf.update(elapsed)

    def render(self, output: PixelBuffer) -> None:
        """Blend all layers into ``output`` using per-channel additive color mixing."""
        count = len(output)
        inv_count = 1.0 / count
        layers = self._layers

        # First layer renders directly into output
        buf0, pal0 = layers[0]
        for i in range(count):
            v = buf0.sample(i * inv_count, count)
            if v > 1.0:
                v = 1.0
            output[i] = pal0.lookup(v)

        # Subsequent layers: sample and blend additively in a single pass
        for k in range(1, len(layers)):
            buf, pal = layers[k]
            for i in range(count):
                v = buf.sample(i * inv_count, count)
                if v > 1.0:
                    v = 1.0
                c1 = output[i]
                c2 = pal.lookup(v)
                r = min(255, ((c1 >> 16) & 255) + ((c2 >> 16) & 255))
                g = min(255, ((c1 >> 8) & 255) + ((c2 >> 8) & 255))
                b = min(255, (c1 & 255) + (c2 & 255))
                output[i] = (r << 16) | (g << 8) | b
