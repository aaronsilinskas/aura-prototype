from effects.effect import Effect
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.steps.flame import flame

# fmt: off
light_palette = bytes([0, 32, 32, 32,
                       255, 255, 255, 255])
# fmt: on


def build_light_renderer(config: RendererConfig) -> EffectRenderer:
    """Tight, rapid white flickers — a bright noisy pulse concentrated in a
    narrow band, like an overdriven flash.

    Level: hotter sparks that also cool faster — brighter peaks with quicker
    turnover and more rapid flickering.
    """
    level = config.level

    heat_rate = config.level_lerp(0.5, 0.75)
    extra_cool_rate = config.level_lerp(0.1, 0.3)

    light_effect = Effect("light").add_steps(
        [
            flame(
                spark_count=level,
                heat_rate=heat_rate,
                extra_cool_rate=extra_cool_rate,
                resolution=config.resolution,
                spread=0.1,
            )
        ]
    )

    return EffectRenderer(light_effect, PaletteLUT256(light_palette))


def _build(name: str, config: RendererConfig) -> EffectRenderer:
    return build_light_renderer(config)


BUILD = _build
