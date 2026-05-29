from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from engine.effects.manager import EffectBuilder
from packs.effects.elements.helpers.flame_layer import FlameLayer
from packs.effects.elements.helpers.renderer import LayerRenderer
from packs.effects.elements.helpers.scroll import PhaseScroll
from packs.effects.elements.helpers.scroll_layer import ScrollLayer

# fmt: off
_water_palette = bytes([0, 0, 0, 64,
                        128, 0, 0, 255,
                        224, 0, 128, 255,
                        255, 0, 255, 255])
# fmt: on


class WaterPrototypeBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """A flowing deep-blue-to-cyan flame that drifts along the strip and
        occasionally reverses direction, like light rippling under moving water.

        Level: the current accelerates and the flame grows more turbulent,
        producing faster, stronger ripples.
        """
        return LayerRenderer(
            name="elements.water_prototype",
            layer=ScrollLayer(
                FlameLayer(
                    spark_count=config.level,
                    resolution=config.resolution,
                    heat_rate=config.level_lerp(0.2, 0.29),
                    extra_cool_rate=0.0,
                    spread=0.2,
                ),
                PhaseScroll(
                    speed=config.level_lerp(0.05, 0.14),
                    min_phase=3.0,
                    max_phase=5.0,
                ),
            ),
            palette=PaletteLUT256(_water_palette),
        )


BUILD = WaterPrototypeBuilder()
