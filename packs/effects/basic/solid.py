from effects.effect import Effect, EffectConfig, EffectPixels, PixelBuffer
from engine.effects.manager import EffectBuilder


class Solid(EffectPixels):
    """Renders every pixel at a fixed pre-scaled packed RGB color.

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
    """Builds a :class:`Solid` from an ``EffectConfig``.

    Reads ``config.options.get("color", 0xFFFFFF)`` for the base color and
    scales each RGB channel by ``brightness`` (float, ``[0.0, 1.0]``, default
    ``1.0``). Values outside ``[0.0, 1.0]`` are clamped silently.
    """

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        base_color = config.options.get("color", 0xFFFFFF)
        brightness = max(0.0, min(1.0, float(config.options.get("brightness", 1.0))))
        r = int(((base_color >> 16) & 0xFF) * brightness)
        g = int(((base_color >> 8) & 0xFF) * brightness)
        b = int((base_color & 0xFF) * brightness)
        color = (r << 16) | (g << 8) | b
        return Effect(name=name, pixels=Solid(color))


BUILD = SolidBuilder()
