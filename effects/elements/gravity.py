from effects.effect import Effect
from effects.level import level_lerp, level_lerp_int
from effects.palette import PaletteLUT256
from effects.render import AdditiveMergeRenderer, EffectRenderer, RendererConfig
from effects.steps.drift_noise import drift_noise
from effects.steps.sparkle import sparkle
from effects.value import ValueGenerator as VG

# fmt: off
grayscale_palette = bytes([0, 0, 0, 0,
                           255, 255, 255, 255])
gravity_palette = bytes([0, 0, 0, 0,
                         128, 28, 18, 64,
                         192, 25, 50, 100,
                         228, 128, 75, 25])
# fmt: on


def build_gravity_renderer(config: RendererConfig) -> EffectRenderer:
    """A slowly drifting deep-space nebula in indigo and navy, scattered
    with white stars that softly twinkle in and out.

    Level: more stars that flash more crisply, the nebula drifts faster, and
    its contrast deepens.
    """
    level = config.level

    nebula_resolution = max(config.resolution, level_lerp_int(level, 18, 36))
    nebula_drift_speed = level_lerp(level, 0.02, 0.038)
    nebula_amplitude = level_lerp(level, 0.22, 0.4)

    spawn_delay_min = level_lerp(level, 0.5, 1.0)
    spawn_delay_max = level_lerp(level, 3.0, 5.0)
    star_fade_in_rate = level_lerp(level, 1.0, 2.0)
    star_fade_out_rate = level_lerp(level, 2.0, 4.0)

    gravity_nebula_effect = Effect("gravity_nebula").add_steps(
        [
            drift_noise(
                resolution=nebula_resolution,
                drift_speed=nebula_drift_speed,
                amplitude=nebula_amplitude,
            ),
        ]
    )
    gravity_nebula_renderer = EffectRenderer(
        gravity_nebula_effect, PaletteLUT256(gravity_palette)
    )

    gravity_stars_effect = Effect("gravity_stars").add_steps(
        [
            sparkle(
                sparkle_count=level,
                spawn_delay_rate=VG.random(spawn_delay_min, spawn_delay_max),
                fade_in_rate=star_fade_in_rate,
                fade_out_rate=star_fade_out_rate,
                pixel_count=config.pixel_count,
            ),
        ]
    )
    gravity_stars_renderer = EffectRenderer(
        gravity_stars_effect, PaletteLUT256(grayscale_palette)
    )

    return AdditiveMergeRenderer([gravity_nebula_renderer, gravity_stars_renderer])
