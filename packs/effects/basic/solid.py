from effects.effect import Effect, EffectConfig, EffectPixels, PixelBuffer
from engine.effects.builder import EffectBuilder


class Solid(EffectPixels):
    """Renders every pixel at a fixed packed RGB color.

    Stateless: ``update`` is a no-op, so calling ``set_effect`` every tick
    produces no visible restart artefacts.
    """

    __slots__ = ["_color"]

    def __init__(self, color: int) -> None:
        self._color = color

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: PixelBuffer) -> None:
        for i in range(len(output)):
            output[i] = self._color


class SolidBuilder(EffectBuilder):
    """Builds a :class:`Solid` from the ``color`` option.

    The ``brightness`` option is ignored: ``MatrixEffectOutput`` applies
    brightness at render time.
    """

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        color = config.get_option("color", 0xFFFFFF)
        return Effect(name=name, pixels=Solid(color))


BUILD = SolidBuilder()
