from effects.flame_layer import FlameLayer
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.renderer import LayerRenderer
from engine.effects.manager import EffectBuilder

# fmt: off
_earth_palette = bytes([0, 96, 48, 8,
                        16, 128, 128, 0,
                        128, 255, 255, 0,
                        192, 128, 64, 0,
                        255, 0, 255, 0])
# fmt: on


class EarthPrototypeBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """A slow, broad smolder in golds with sprouts of earthy greens.

        Level: more heat sparks with a narrower spread, concentrating the smolder
        into a tighter, more active column.
        """
        return LayerRenderer(
            name=name,
            layer=FlameLayer(
                spark_count=config.level,
                resolution=config.resolution,
                heat_rate=0.2,
                extra_cool_rate=0.0,
                spread=config.level_lerp(0.7, 0.4),
            ),
            palette=PaletteLUT256(_earth_palette),
        )


BUILD = EarthPrototypeBuilder()
