from effects.effect import Effect, EffectConfig
from effects.layers.flame_layer import FlameLayer
from effects.layers.renderer import LayerRenderer
from effects.level import clamp_level, level_lerp
from effects.palette import PaletteLUT256
from engine.effects.manager import EffectBuilder

# fmt: off
_earth_palette = bytes([0, 96, 48, 8,
                        16, 128, 128, 0,
                        128, 255, 255, 0,
                        192, 128, 64, 0,
                        255, 0, 255, 0])
# fmt: on


class EarthBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """A slow, broad smolder in golds with sprouts of earthy greens.

        Level: more heat sparks with a narrower spread, concentrating the smolder
        into a tighter, more active column.
        """
        level = clamp_level(config.get_option("level", 1))
        return Effect(
            name=name,
            pixels=LayerRenderer(
                layer=FlameLayer(
                    spark_count=level,
                    resolution=config.resolution,
                    heat_rate=0.2,
                    extra_cool_rate=0.0,
                    spread=level_lerp(level, 0.7, 0.4),
                ),
                palette=PaletteLUT256(_earth_palette),
            ),
        )


BUILD = EarthBuilder()
