from effects.effect import Effect, EffectConfig, PixelBuffer
from engine.effects.manager import EffectBuilder


class Solid(Effect):
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
    """Builds a :class:`Solid` from an ``EffectConfig``.

    Reads ``config.options.get("color", 0xFFFFFF)`` for the base color and
    scales each RGB channel by ``config.level / 10.0`` using integer truncation.
    """

    def __call__(self, name: str, config: EffectConfig) -> Solid:
        base_color = config.options.get("color", 0xFFFFFF)
        level = config.options.get("level", 10)
        brightness = level / 10.0
        r = int(((base_color >> 16) & 0xFF) * brightness)
        g = int(((base_color >> 8) & 0xFF) * brightness)
        b = int((base_color & 0xFF) * brightness)
        color = (r << 16) | (g << 8) | b
        return Solid(color)


BUILD = SolidBuilder()
