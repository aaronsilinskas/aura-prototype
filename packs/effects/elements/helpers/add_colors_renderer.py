from effects.palette import Palette
from effects.render import EffectRenderer, PixelBuffer
from packs.effects.elements.helpers.layer import Layer


class AddColorsRenderer(EffectRenderer):
    """Composes multiple (buffer, palette) layers by additively blending their colors.

    Each layer is a ``(buffer, palette)`` pair. Per-pixel: each layer maps its
    buffer sample to a color via its own palette, then all colors are combined
    by per-channel addition (clamped to 255).

    Layers are rendered in order: the first writes directly to ``output``; each
    subsequent layer renders to a lazily-allocated temp buffer and is blended
    additively (per-channel sum, clamped to 255).

    The ``state`` argument on ``update`` and ``render`` is accepted for
    signature compatibility with ``EffectRenderer`` but is never read.
    """

    __slots__ = ["_layers", "_name", "_temp"]

    def __init__(self, name: str, layers: list[tuple[Layer, Palette]]) -> None:
        self._name = name
        self._layers = layers
        self._temp: PixelBuffer | None = None

    @property
    def name(self) -> str:
        return self._name

    def update(self, state, timer) -> None:
        """Advance all layer buffers. ``state`` is ignored."""
        elapsed = timer.elapsed
        for buf, _ in self._layers:
            buf.update(elapsed)

    def render(self, state, output: PixelBuffer) -> None:
        """Write additively blended layers to ``output``. ``state`` is ignored."""
        count = len(output)
        layers = self._layers

        # First layer renders directly into output
        buf0, pal0 = layers[0]
        for i in range(count):
            v = buf0.sample(i / count, count)
            if v > 1.0:
                v = 1.0
            output[i] = pal0.lookup(v)

        if len(layers) == 1:
            return

        # Subsequent layers: render to temp then blend additively into output
        if self._temp is None or len(self._temp) != count:
            self._temp = PixelBuffer(count)
        temp = self._temp

        for k in range(1, len(layers)):
            buf, pal = layers[k]
            for i in range(count):
                v = buf.sample(i / count, count)
                if v > 1.0:
                    v = 1.0
                temp[i] = pal.lookup(v)

            for i in range(count):
                c1 = output[i]
                c2 = temp[i]
                r = min(255, ((c1 >> 16) & 255) + ((c2 >> 16) & 255))
                g = min(255, ((c1 >> 8) & 255) + ((c2 >> 8) & 255))
                b = min(255, (c1 & 255) + (c2 & 255))
                output[i] = (r << 16) | (g << 8) | b
