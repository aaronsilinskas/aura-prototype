from effects.effect import Effect, EffectConfig
from effects.layers.flame_layer import FlameLayer
from effects.layers.renderer import LayerRenderer
from effects.level import clamp_level, level_lerp
from effects.palette import PaletteLUT256
from engine.effects.manager import EffectBuilder

# fmt: off
_light_palette = bytes([0, 32, 32, 32,
                        255, 255, 255, 255])
# fmt: on


class LightBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """Tight, rapid white flickers — a bright noisy pulse concentrated in a
        narrow band, like an overdriven flash.

        Level: hotter sparks that also cool faster — brighter peaks with quicker
        turnover and more rapid flickering.
        """
        level = clamp_level(int(config.options.get("level", 1)))
        return Effect(
            name=name,
            pixels=LayerRenderer(
                layer=FlameLayer(
                    spark_count=level,
                    resolution=config.resolution,
                    heat_rate=level_lerp(level, 0.5, 0.75),
                    extra_cool_rate=level_lerp(level, 0.1, 0.3),
                    spread=0.1,
                ),
                palette=PaletteLUT256(_light_palette),
            ),
        )


BUILD = LightBuilder()
