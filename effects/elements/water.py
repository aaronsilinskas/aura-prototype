from effects.effect import Effect
from effects.level import level_lerp
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.steps.duration import duration
from effects.steps.flame import flame
from effects.steps.position import accelerate
from effects.value import ValueGenerator as VG

# fmt: off
water_palette = bytes([0, 0, 0, 64,
                       128, 0, 0, 255,
                       224, 0, 128, 255,
                       255, 0, 255, 255])
# fmt: on


def build_water_renderer(config: RendererConfig) -> EffectRenderer:
    """A flowing deep-blue-to-cyan flame that drifts along the strip and
    occasionally reverses direction, like light rippling under moving water.

    Level: the current accelerates and the flame grows more turbulent,
    producing faster, stronger ripples.
    """
    level = config.level
    resolution = config.resolution

    flow_speed = level_lerp(level, 0.05, 0.14)
    heat_rate = level_lerp(level, 0.2, 0.29)

    water_effect = Effect("water").add_steps(
        [
            duration(
                duration=VG.random(3.0, 5.0),
                persist_steps=True,
                steps=[
                    accelerate(end=flow_speed, direction=VG.random_choice([-1, 1])),
                    flame(
                        spark_count=level,
                        heat_rate=heat_rate,
                        extra_cool_rate=0.0,
                        resolution=resolution,
                        spread=0.2,
                    ),
                ],
            ),
        ]
    )

    return EffectRenderer(water_effect, PaletteLUT256(water_palette))
