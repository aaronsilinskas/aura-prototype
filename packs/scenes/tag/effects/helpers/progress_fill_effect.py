from effects.effect import EffectPixels, PixelBuffer
from effects.layers.progress_layer import ProgressLayer


class ProgressFillEffect(EffectPixels):
    """Self-animating progress fill over ``duration``, in a single raw RGB color.

    Advances its own internal clock each ``update``, so it need not be re-issued
    every tick. Renders like
    :class:`~packs.effects.basic.helpers.progress_effect.ProgressEffect`:
    multiplies ``color`` by each pixel's lit fraction inline, allocating no
    ``Palette``/``PaletteLUT256``.
    """

    __slots__ = ("_b", "_duration", "_elapsed", "_g", "_layer", "_r")

    def __init__(self, layer: ProgressLayer, color: int, duration: float) -> None:
        self._layer = layer
        self._duration = duration
        self._elapsed = 0.0
        self._r = (color >> 16) & 0xFF
        self._g = (color >> 8) & 0xFF
        self._b = color & 0xFF

    def update(self, elapsed: float) -> None:
        self._elapsed += elapsed
        duration = self._duration
        if duration <= 0.0:
            progress = 1.0
        else:
            progress = self._elapsed / duration
            if progress > 1.0:
                progress = 1.0
        self._layer.set_progress(progress)

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
