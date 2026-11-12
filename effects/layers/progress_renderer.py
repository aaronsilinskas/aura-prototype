from effects.effect import EffectPixels, PixelBuffer
from effects.layers.progress_layer import ProgressLayer


class ProgressRenderer(EffectPixels):
    """Renders a :class:`ProgressLayer` as a fill in one raw RGB color, no palette.

    Each pixel is ``color`` with every channel scaled by the layer's lit
    fraction, so the boundary pixel is dimmed for an anti-aliased edge.

    ``update`` leaves the progress unchanged, so the fill is static until it is
    re-issued. A self-animating fill subclasses this and overrides only
    ``update``: it keeps its own reference to the layer it passes in and sets
    that layer's progress from ``update``.
    """

    __slots__ = ("_b", "_g", "_layer", "_r")

    def __init__(self, layer: ProgressLayer, color: int) -> None:
        self._layer = layer
        self._r = (color >> 16) & 0xFF
        self._g = (color >> 8) & 0xFF
        self._b = color & 0xFF

    def update(self, elapsed: float) -> None:
        """No-op: the progress changes only when the layer's progress is set."""

    def render(self, output: PixelBuffer) -> None:
        count = len(output)
        inv_count = 1.0 / count
        layer = self._layer
        r = self._r
        g = self._g
        b = self._b
        for i in range(count):
            f = layer.sample(i * inv_count, count)
            output[i] = (int(r * f) << 16) | (int(g * f) << 8) | int(b * f)
