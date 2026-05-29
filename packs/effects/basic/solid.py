from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.effects.manager import EffectBuilder


class SolidRenderer(EffectRenderer):
    """Renders every pixel at a fixed pre-scaled packed RGB color.

    Stateless: ``update`` is a no-op, so calling ``set_effect`` every tick
    produces no visible restart artefacts.
    """

    __slots__ = ["_color", "_name"]

    def __init__(self, color: int) -> None:
        self._color = color
        self._name = "basic.solid"

    @property
    def name(self) -> str:
        return self._name

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: PixelBuffer) -> None:
        for i in range(len(output)):
            output[i] = self._color


class SolidBuilder(EffectBuilder):
    """Builds a :class:`SolidRenderer` from a ``RendererConfig``.

    Reads ``config.options.get("color", 0xFFFFFF)`` for the base color and
    scales each RGB channel by ``config.level / 10.0`` using integer truncation.
    """

    def __call__(self, name: str, config: RendererConfig) -> SolidRenderer:
        base_color = config.options.get("color", 0xFFFFFF)
        brightness = config.level / 10.0
        r = int(((base_color >> 16) & 0xFF) * brightness)
        g = int(((base_color >> 8) & 0xFF) * brightness)
        b = int((base_color & 0xFF) * brightness)
        color = (r << 16) | (g << 8) | b
        return SolidRenderer(color)


BUILD = SolidBuilder()
