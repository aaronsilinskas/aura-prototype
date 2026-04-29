from effects.effect import Effect
from effects.level import level_lerp
from effects.palette import PaletteLUT256
from effects.render import AdditiveMergeRenderer, EffectRenderer, RendererConfig
from effects.shape import Shape
from effects.steps.control import hide
from effects.steps.duration import duration
from effects.steps.position import accelerate, set_position
from effects.steps.scale import multiplier
from effects.value import ValueGenerator as VG

# fmt: off
# air_palette = bytes([0, 0, 0, 0,
#                      128, 255, 0, 255,
#                      255, 255, 255, 255])
air_palette = bytes([
    0,   0,   0,   0,
    68,  54,  0,   98,
    138, 176, 70,  224,
    216, 228, 198, 255,
    255, 255, 255, 255
])

# fmt: on


def build_air_renderer(config: RendererConfig) -> EffectRenderer:
    """Soft green-white breezes that sweep across the strip, fading in,
    accelerating, then dissolving. Higher levels add simultaneous
    overlapping breezes.

    Level: breezes last longer, gaps between them shorten, and a second
    concurrent breeze is added at level 5.
    """
    level = config.level

    accelerate_end = VG.random(0.75, 1.2)
    breeze_duration_end = VG.random(2.0, level_lerp(level, 2.5, 5.0))
    breeze_count = 1 + level // 5
    multiplier_end = level_lerp(level, 0.0, 0.5) + 0.50 / breeze_count
    hide_duration = VG.random(0.5, 3.0 - level_lerp(level, 0.0, 2.0))
    palette = PaletteLUT256(air_palette)

    renderers: list[EffectRenderer] = []
    for _ in range(breeze_count):
        air_effect = Effect(
            "air",
            Shape.padded(
                0.3 - level_lerp(level, 0.0, 0.3), Shape.reverse(Shape.gradient())
            ),
        ).add_steps(
            [
                set_position(position=VG.random()),
                duration(
                    duration=breeze_duration_end,
                    steps=[
                        accelerate(
                            start=0.3,
                            end=accelerate_end,
                        ),
                        multiplier(start=0.0, end=multiplier_end),
                    ],
                ),
                duration(
                    duration=VG.random(0.75, 1.25),
                    steps=[
                        multiplier(start=multiplier_end, end=0.0),
                        accelerate(end=0),
                    ],
                ),
                hide(hide_duration),
            ]
        )
        renderers.append(EffectRenderer(air_effect, palette))

    if breeze_count == 1:
        return renderers[0]

    return AdditiveMergeRenderer(renderers)
