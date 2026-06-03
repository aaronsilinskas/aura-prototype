from effects.effect import Effect, EffectConfig
from effects.layers.flame_layer import FlameLayer
from effects.layers.renderer import LayerRenderer
from effects.layers.scroll import ScrollOffset
from effects.layers.scroll_layer import ScrollLayer
from effects.palette import PaletteLUT256
from engine.effects.manager import EffectBuilder

# fmt: off
_ice_palette = bytes([0, 0, 64, 8,
                      64, 0, 255, 32,
                      128, 0, 255, 128,
                      255, 255, 255, 255])
# fmt: on


class IceBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """A slow, cold flame that flows and gently scrolls — dark teal at the base
        blooming into bright cyan and white.

        Level: the flame flows faster with a tighter spread, producing a sharper,
        more active column.
        """
        return LayerRenderer(
            name=name,
            layer=ScrollLayer(
                FlameLayer(
                    spark_count=config.level,
                    resolution=config.resolution,
                    heat_rate=0.15,
                    extra_cool_rate=0.0,
                    spread=config.level_lerp(0.75, 0.45),
                ),
                ScrollOffset(speed=config.level_lerp(0.02, 0.05)),
            ),
            palette=PaletteLUT256(_ice_palette),
        )


BUILD = IceBuilder()
