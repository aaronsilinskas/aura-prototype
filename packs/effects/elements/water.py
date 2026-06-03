from effects.effect import Effect, EffectConfig
from effects.layers.flame_layer import FlameLayer
from effects.layers.renderer import LayerRenderer
from effects.layers.scroll import PhaseScroll
from effects.layers.scroll_layer import ScrollLayer
from effects.level import level_lerp
from effects.palette import PaletteLUT256
from engine.effects.manager import EffectBuilder

# fmt: off
_water_palette = bytes([0, 0, 0, 64,
                        128, 0, 0, 255,
                        224, 0, 128, 255,
                        255, 0, 255, 255])
# fmt: on


class WaterBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """A flowing deep-blue-to-cyan flame that drifts along the strip and
        occasionally reverses direction, like light rippling under moving water.

        Level: the current accelerates and the flame grows more turbulent,
        producing faster, stronger ripples.
        """
        level = config.options.get("level", 10)
        return LayerRenderer(
            name=name,
            layer=ScrollLayer(
                FlameLayer(
                    spark_count=config.options.get("level", 10),
                    resolution=config.resolution,
                    heat_rate=level_lerp(level, 0.2, 0.29),
                    extra_cool_rate=0.0,
                    spread=0.2,
                ),
                PhaseScroll(
                    speed=level_lerp(level, 0.05, 0.14),
                    min_phase=3.0,
                    max_phase=5.0,
                ),
            ),
            palette=PaletteLUT256(_water_palette),
        )


BUILD = WaterBuilder()
