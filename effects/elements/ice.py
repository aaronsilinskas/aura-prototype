from effects.effect import Effect
from effects.level import level_lerp
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.steps.duration import duration
from effects.steps.flame import flame
from effects.steps.position import rotate
from effects.value import ValueGenerator as VG

# fmt: off
ice_palette = bytes([0, 0, 64, 8,
                     64, 0, 255, 32,
                     128, 0, 255, 128,
                     255, 255, 255, 255])
# fmt: on


def build_ice_renderer(config: RendererConfig) -> EffectRenderer:
    """A slow, cold flame that flows and gently rotates — dark teal at the base
    blooming into bright cyan and white.

    Level: the flame flows and rotates faster with a tighter spread, producing
    a sharper, more active column.
    """
    level = config.level
    resolution = config.resolution

    flow_speed = level_lerp(level, 0.02, 0.05)
    spread = level_lerp(level, 0.75, 0.45)

    ice_effect = Effect("ice").add_steps(
        [
            duration(
                duration=VG.random(5.0, 10.0),
                persist_steps=True,
                steps=[
                    flame(
                        spark_count=level,
                        heat_rate=0.15,
                        extra_cool_rate=0.0,
                        resolution=resolution,
                        spread=spread,
                    ),
                    rotate(flow_speed),
                ],
            ),
        ]
    )

    return EffectRenderer(ice_effect, PaletteLUT256(ice_palette))
