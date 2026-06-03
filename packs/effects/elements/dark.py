from effects.effect import Effect, EffectConfig
from effects.layers.renderer import LayerRenderer
from effects.layers.sparkle_layer import SparkleLayer
from effects.level import clamp_level, level_lerp
from effects.palette import PaletteLUT256
from effects.value import ValueGenerator as VG
from engine.effects.manager import EffectBuilder

# fmt: off
_dark_palette = bytes([0, 0, 0, 0,
                       192, 255, 0, 0,
                       255, 255, 0, 128])
# fmt: on


class DarkBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """Sparse deep-red sparks that flicker and fade against black, like dying
        embers glowing in the dark.

        Level: more sparks can glow simultaneously, though each spawns more slowly
        — the field grows denser rather than quickening.
        """
        level = clamp_level(int(config.options.get("level", 1)))
        spawn_delay_min = level_lerp(level, 0.5, 1.0)
        spawn_delay_max = level_lerp(level, 3.0, 5.0)

        return Effect(
            name=name,
            pixels=LayerRenderer(
                SparkleLayer(
                    sparkle_count=level,
                    spawn_delay_rate=VG.random(spawn_delay_min, spawn_delay_max),
                    fade_in_rate=VG.resolve(VG.random(0.5, 1.0)),
                    fade_out_rate=VG.resolve(VG.random(1.0, 2.0)),
                ),
                PaletteLUT256(_dark_palette),
            ),
        )


BUILD = DarkBuilder()
