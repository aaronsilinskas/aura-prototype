from effects.effect import EffectState, EffectTimer
from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.effects.manager import EffectBuilder


class SolidRenderer(EffectRenderer):
    def __init__(self, color: int) -> None:
        self._color = color

    @property
    def name(self) -> str:
        """The fully-qualified name of this renderer."""
        return "basic.solid"

    def update(self, state: EffectState, timer: EffectTimer) -> None:
        pass

    def render(self, state: EffectState, output: PixelBuffer) -> None:
        """Write the pre-scaled solid color to every pixel."""
        for i in range(len(output)):
            output[i] = self._color


class SolidBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """Solid color fill scaled by level.

        Level: scales the brightness of the configured color from 10% (level 1)
        to 100% (level 10).
        """
        base_color = config.options.get("color", 0xFFFFFF)
        brightness = config.level / 10.0
        r = int(((base_color >> 16) & 0xFF) * brightness)
        g = int(((base_color >> 8) & 0xFF) * brightness)
        b = int((base_color & 0xFF) * brightness)
        color = (r << 16) | (g << 8) | b
        return SolidRenderer(color)


BUILD = SolidBuilder()
