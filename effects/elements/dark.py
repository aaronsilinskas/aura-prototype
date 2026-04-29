from effects.effect import Effect
from effects.level import level_lerp
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.steps.sparkle import sparkle
from effects.value import ValueGenerator as VG

# fmt: off
dark_sparkle_palette = bytes([0, 0, 0, 0,
                              192, 255, 0, 0,
                              255, 255, 0, 128])
# fmt: on


def build_dark_renderer(config: RendererConfig) -> EffectRenderer:
    """Sparse deep-red sparks that flicker and fade against black, like dying
    embers glowing in the dark.

    Level: more sparks can glow simultaneously, though each spawns more slowly
    — the field grows denser rather than quickening.
    """
    level = config.level

    spawn_delay_min = level_lerp(level, 0.5, 1.0)
    spawn_delay_max = level_lerp(level, 3.0, 5.0)

    dark_sparkle_effect = Effect("dark_sparkles").add_steps(
        [
            sparkle(
                sparkle_count=level,
                spawn_delay_rate=VG.random(spawn_delay_min, spawn_delay_max),
                fade_in_rate=VG.random(0.5, 1),
                fade_out_rate=VG.random(1.0, 2.0),
                pixel_count=config.pixel_count,
            ),
        ]
    )
    dark_sparkle_renderer = EffectRenderer(
        dark_sparkle_effect, PaletteLUT256(dark_sparkle_palette)
    )

    return dark_sparkle_renderer
