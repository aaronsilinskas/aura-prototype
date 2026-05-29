from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.value import ValueGenerator as VG
from engine.effects.manager import EffectBuilder
from packs.effects.elements.helpers.add_colors_renderer import AddColorsRenderer
from packs.effects.elements.helpers.drift_noise_layer import DriftNoiseLayer
from packs.effects.elements.helpers.sparkle_layer import SparkleLayer

# fmt: off
_GRAYSCALE_PALETTE = bytes([  0,   0,   0,   0,
                             255, 255, 255, 255])
_GRAVITY_PALETTE = bytes([  0,   0,   0,   0,
                           128,  28,  18,  64,
                           192,  25,  50, 100,
                           228, 128,  75,  25])
# fmt: on


class GravityPrototypeBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """A drift-noise nebula prototype with additive star sparkles.

        Bypasses Effect/EffectStep/EffectState machinery entirely — all
        simulation state lives directly on the renderer.
        """
        level = config.level

        nebula_resolution = max(config.resolution, config.level_lerp_int(18, 36))
        nebula_drift_speed = config.level_lerp(0.02, 0.038)
        nebula_amplitude = config.level_lerp(0.22, 0.4)

        spawn_delay_min = config.level_lerp(0.5, 1.0)
        spawn_delay_max = config.level_lerp(3.0, 5.0)
        star_fade_in_rate = config.level_lerp(1.0, 2.0)
        star_fade_out_rate = config.level_lerp(2.0, 4.0)

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
        return AddColorsRenderer(
            name,
            [
                (nebula, PaletteLUT256(_GRAVITY_PALETTE)),
                (sparkles, PaletteLUT256(_GRAYSCALE_PALETTE)),
            ],
        )


BUILD = GravityPrototypeBuilder()
