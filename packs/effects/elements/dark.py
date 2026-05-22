from effects.effect import Effect
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.steps.sparkle import sparkle
from effects.value import ValueGenerator as VG
from engine.effects.manager import EffectBuilder

# fmt: off
dark_sparkle_palette = bytes([0, 0, 0, 0,
                              192, 255, 0, 0,
                              255, 255, 0, 128])
# fmt: on


class DarkBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """Sparse deep-red sparks that flicker and fade against black, like dying
        embers glowing in the dark.

        Level: more sparks can glow simultaneously, though each spawns more slowly
        — the field grows denser rather than quickening.
        """
        level = config.level

        spawn_delay_min = config.level_lerp(0.5, 1.0)
        spawn_delay_max = config.level_lerp(3.0, 5.0)

        dark_sparkle_effect = Effect("dark_sparkles").add_steps(
            [
                sparkle(
                    sparkle_count=level,
                    spawn_delay_rate=VG.random(spawn_delay_min, spawn_delay_max),
                    fade_in_rate=VG.random(0.5, 1),
                    fade_out_rate=VG.random(1.0, 2.0),
                ),
            ]
        )
        dark_sparkle_renderer = EffectRenderer(
            dark_sparkle_effect, PaletteLUT256(dark_sparkle_palette)
        )

        return dark_sparkle_renderer


BUILD = DarkBuilder()
