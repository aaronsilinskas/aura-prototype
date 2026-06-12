from effects.effect import EffectPixels, PixelBuffer
from effects.layers.progress_layer import ProgressLayer


class ProgressFillEffect(EffectPixels):
    """Self-animating fill: advances a :class:`ProgressLayer` over ``duration``.

    Each ``update(elapsed)`` accumulates ``elapsed`` into an internal clock and
    sets the wrapped layer's progress to ``min(1.0, internal_elapsed /
    duration)``, clamping and holding at ``1.0`` once ``duration`` is exceeded.
    Rendering reuses the same per-pixel inline color scaling as
    :class:`~packs.effects.basic.helpers.progress_effect.ProgressEffect` — the
    raw ``color`` channels are extracted once in ``__init__`` and multiplied by
    each pixel's lit fraction, so no ``Palette``/``PaletteLUT256`` is needed.

    Animates on its own clock: it accumulates its own elapsed time and does not
    need to be re-issued every tick.
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
        """Advance the internal clock and update the layer's progress."""
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
