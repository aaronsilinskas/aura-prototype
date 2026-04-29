from effects.effect import Effect
from effects.palette import PaletteLUT256
from effects.render import AdditiveMergeRenderer, EffectRenderer, RendererConfig
from effects.shape import Shape
from effects.steps.control import call, hide
from effects.steps.duration import duration
from effects.steps.position import set_position
from effects.steps.scale import multiplier
from effects.value import ValueGenerator as VG

# fmt: off
lightning_palette = bytes([0, 0, 0, 0,
                           255, 255, 100, 0])
# fmt: on


def build_lightning_renderer(config: RendererConfig) -> EffectRenderer:
    """Blinding orange flashes that strike at random positions and vanish in an
    instant. Higher levels layer concurrent bolts for a branching storm effect.

    Level: more bolts strike simultaneously and each flash can linger slightly
    longer.
    """
    level = config.level

    hide_max = 1.5 - (1 - 1 / level)
    strike_duration_max = 1.25 - (1 - 1 / level)

    strike_duration_min = 0.5
    branch_count = max(1, level // 2)
    palette = PaletteLUT256(lightning_palette)

    renderers: list[EffectRenderer] = []
    for _ in range(branch_count):
        lightning_effect = Effect(
            "lightning", Shape.padded(0.25, Shape.centered_gradient())
        ).add_steps(
            [
                hide(duration=VG.random(0.1, hide_max)),
                call(lambda _, __: config.notify_listeners("lightning_strike")),
                set_position(position=VG.random()),
                duration(
                    duration=VG.random(strike_duration_min, strike_duration_max),
                    steps=[
                        multiplier(VG.random(1.0, 0.25), 0),
                    ],
                ),
            ]
        )
        renderers.append(EffectRenderer(lightning_effect, palette))

    if branch_count == 1:
        return renderers[0]

    return AdditiveMergeRenderer(renderers)
