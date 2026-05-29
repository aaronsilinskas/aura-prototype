from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.renderer import LayerRenderer
from effects.sparkle_layer import SparkleLayer
from effects.value import ValueGenerator as VG
from engine.effects.manager import EffectBuilder

# fmt: off
_dark_palette = bytes([0, 0, 0, 0,
                       192, 255, 0, 0,
                       255, 255, 0, 128])
# fmt: on


class DarkPrototypeBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """Sparse deep-red sparks that flicker and fade against black, like dying
        embers glowing in the dark.

        Level: more sparks can glow simultaneously, though each spawns more slowly
        — the field grows denser rather than quickening.
        """
        level = config.level
        spawn_delay_min = config.level_lerp(0.5, 1.0)
        spawn_delay_max = config.level_lerp(3.0, 5.0)

        return LayerRenderer(
            name,
            SparkleLayer(
                sparkle_count=level,
                spawn_delay_rate=VG.random(spawn_delay_min, spawn_delay_max),
                fade_in_rate=VG.resolve(VG.random(0.5, 1.0)),
                fade_out_rate=VG.resolve(VG.random(1.0, 2.0)),
            ),
            PaletteLUT256(_dark_palette),
        )


BUILD = DarkPrototypeBuilder()
