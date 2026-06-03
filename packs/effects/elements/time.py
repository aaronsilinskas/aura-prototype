from effects.effect import Effect, EffectConfig
from effects.layers.add_colors_renderer import AddColorsRenderer
from effects.layers.drift_noise_layer import DriftNoiseLayer
from effects.layers.scroll import ScrollOffset
from effects.layers.scroll_layer import ScrollLayer
from effects.layers.shape_layer import ShapeLayer
from effects.palette import PaletteLUT256
from effects.shape import Shape
from engine.effects.manager import EffectBuilder

# fmt: off
_GRAYSCALE_PALETTE = bytes([  0,   0,   0,   0,
                             255, 255, 255, 255])
_TIME_SAND_PALETTE = bytes([  0,   0,   0,   0,
                              64,  64,  32,   0,
                             128, 128, 128,  16,
                             192, 128,  64,   8,
                             255, 128, 128, 128])
# fmt: on


class TimeBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """A drifting amber-brown sand prototype overlaid with rotating gray tickers.

        simulation state lives directly on the effect.
        """
        level = config.level

        drift_speed = config.level_lerp(0.02, 0.065)
        ticker_rotate_speed = config.level_lerp(0.1, 0.28)

        sand = DriftNoiseLayer(
            resolution=24,
            drift_speed=drift_speed,
            amplitude=0.2,
        )
        ticker = ScrollLayer(
            ShapeLayer(Shape.checkers(value=0.25, count=level, width=0.05)),
            ScrollOffset(speed=ticker_rotate_speed),
        )
        return AddColorsRenderer(
            name,
            [
                (sand, PaletteLUT256(_TIME_SAND_PALETTE)),
                (ticker, PaletteLUT256(_GRAYSCALE_PALETTE)),
            ],
        )


BUILD = TimeBuilder()
