from effects.effect import Effect
from effects.level import level_lerp
from effects.palette import PaletteLUT256
from effects.render import AdditiveMergeRenderer, EffectRenderer, RendererConfig
from effects.shape import Shape
from effects.steps.drift_noise import drift_noise
from effects.steps.position import rotate

# fmt: off
grayscale_palette = bytes([0, 0, 0, 0,
                           255, 255, 255, 255])
time_sand_palette = bytes([0, 0, 0, 0,
                           64, 64, 32, 0,
                           128, 128, 128, 16,
                           192, 128, 64, 8,
                           255, 128, 128, 128])
# fmt: on


def build_time_renderer(config: RendererConfig) -> EffectRenderer:
    """A drifting amber-brown noise evoking shifting sand, overlaid with
    rotating gray tick marks like a timer.

    Level: sand drifts faster and the tick marks multiply; everything spins
    more quickly.
    """
    level = config.level

    drift_speed = level_lerp(level, 0.02, 0.065)
    ticker_rotate_speed = level_lerp(level, 0.1, 0.28)

    time_sand_effect = Effect("time_sand").add_steps(
        [drift_noise(drift_speed=drift_speed)]
    )
    time_sand_renderer = EffectRenderer(
        time_sand_effect, PaletteLUT256(time_sand_palette)
    )

    time_ticker_effect = Effect(
        "time_ticker", Shape.checkers(value=0.25, count=level, width=0.05)
    ).add_steps([rotate(ticker_rotate_speed)])
    time_ticker_renderer = EffectRenderer(
        time_ticker_effect, PaletteLUT256(grayscale_palette)
    )

    return AdditiveMergeRenderer([time_sand_renderer, time_ticker_renderer])
