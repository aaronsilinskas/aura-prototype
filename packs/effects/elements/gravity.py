from effects.effect import Effect, EffectConfig
from effects.layers.add_colors_renderer import AddColorsRenderer
from effects.layers.drift_noise_layer import DriftNoiseLayer
from effects.layers.sparkle_layer import SparkleLayer
from effects.level import EFFECT_TOP_LEVEL, effect_level
from effects.palette import PaletteLUT256
from effects.value import ValueGenerator as VG
from engine.effects.builder import EffectBuilder
from engine.lerp import level_lerp, level_lerp_int

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
        """A slow, drifting nebula in deep blues, sprinkled with additive white
        star sparkles.

        Level: a denser, wider nebula with more stars winking in and out.
        """
        level = effect_level(config)

        nebula_resolution = max(config.resolution, level_lerp_int(level, 18, 36, EFFECT_TOP_LEVEL))
        nebula_drift_speed = level_lerp(level, 0.02, 0.038, EFFECT_TOP_LEVEL)
        nebula_amplitude = level_lerp(level, 0.22, 0.4, EFFECT_TOP_LEVEL)

        spawn_delay_min = level_lerp(level, 0.5, 1.0, EFFECT_TOP_LEVEL)
        spawn_delay_max = level_lerp(level, 3.0, 5.0, EFFECT_TOP_LEVEL)
        star_fade_in_rate = level_lerp(level, 1.0, 2.0, EFFECT_TOP_LEVEL)
        star_fade_out_rate = level_lerp(level, 2.0, 4.0, EFFECT_TOP_LEVEL)

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
