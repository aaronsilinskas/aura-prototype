from effects.effect import Effect, EffectConfig
from effects.layers.add_colors_renderer import AddColorsRenderer
from effects.layers.drift_noise_layer import DriftNoiseLayer
from effects.layers.sparkle_layer import SparkleLayer
from effects.level import clamp_level, level_lerp, level_lerp_int
from effects.palette import PaletteLUT256
from effects.value import ValueGenerator as VG
from engine.effects.manager import EffectBuilder

# fmt: off
_GRAYSCALE_PALETTE = bytes([  0,   0,   0,   0,
                             255, 255, 255, 255])
_GRAVITY_PALETTE = bytes([  0,   0,   0,   0,
                           128,  28,  18,  64,
                           192,  25,  50, 100,
                           228, 128,  75,  25])
# fmt: on


class GravityBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """A drift-noise nebula prototype with additive star sparkles.

        simulation state lives directly on the effect.
        """
        level = clamp_level(config.get_option("level", 1))

        nebula_resolution = max(config.resolution, level_lerp_int(level, 18, 36))
        nebula_drift_speed = level_lerp(level, 0.02, 0.038)
        nebula_amplitude = level_lerp(level, 0.22, 0.4)

        spawn_delay_min = level_lerp(level, 0.5, 1.0)
        spawn_delay_max = level_lerp(level, 3.0, 5.0)
        star_fade_in_rate = level_lerp(level, 1.0, 2.0)
        star_fade_out_rate = level_lerp(level, 2.0, 4.0)

        nebula = DriftNoiseLayer(
            resolution=nebula_resolution,
            drift_speed=nebula_drift_speed,
            amplitude=nebula_amplitude,
        )
        sparkles = SparkleLayer(
            sparkle_count=level,
            spawn_delay_rate=VG.random(spawn_delay_min, spawn_delay_max),
            fade_in_rate=star_fade_in_rate,
            fade_out_rate=star_fade_out_rate,
        )
        return Effect(
            name=name,
            pixels=AddColorsRenderer(
                [
                    (nebula, PaletteLUT256(_GRAVITY_PALETTE)),
                    (sparkles, PaletteLUT256(_GRAYSCALE_PALETTE)),
                ],
            ),
        )


BUILD = GravityBuilder()
