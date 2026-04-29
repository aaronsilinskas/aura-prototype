from effects.effect import Effect
from effects.level import level_lerp
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.steps.flame import flame

# fmt: off
earth_palette = bytes([0, 96, 48, 8,
                       16, 128, 128, 0,
                       128, 255, 255, 0,
                       192, 128, 64, 0,
                       255, 0, 255, 0])
# fmt: on


def build_earth_renderer(config: RendererConfig) -> EffectRenderer:
    """A slow, broad smolder in golds with sprouts of earthy greens.

    Level: more heat sparks with a narrower spread, concentrating the smolder
    into a tighter, more active column.
    """
    level = config.level
    resolution = config.resolution
    spread = level_lerp(level, 0.7, 0.4)

    earth_effect = Effect("earth").add_steps(
        [
            flame(
                spark_count=level,
                heat_rate=0.2,
                extra_cool_rate=0.0,
                resolution=resolution,
                spread=spread,
            ),
        ]
    )

    return EffectRenderer(earth_effect, PaletteLUT256(earth_palette))
