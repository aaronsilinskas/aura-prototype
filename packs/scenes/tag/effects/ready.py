"""Tag scene "ready" effect — a rotating red laser sweep.

A red shape that rotates around the strip, looking like a laser sweeping
across the screen. Used to indicate the device is idle in the Ready phase,
waiting for a button press to start the game.
"""

from __future__ import annotations

from effects.effect import Effect, EffectConfig
from effects.layers.add_colors_renderer import AddColorsRenderer
from effects.layers.scroll import ScrollOffset
from effects.layers.scroll_layer import ScrollLayer
from effects.layers.shape_layer import ShapeLayer
from effects.palette import PaletteLUT256
from effects.shape import Shape
from engine.effects.manager import EffectBuilder

# Black -> red: the laser body lights up red, the dead zones stay dark.
_RED_PALETTE = bytes([0, 0, 0, 0, 255, 255, 0, 0])

# Revolutions per second of the sweeping laser.
_ROTATE_SPEED = 0.6


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        rotate_speed = config.get_option("rotate_speed", _ROTATE_SPEED)
        laser = ScrollLayer(
            ShapeLayer(Shape.padded(0.25, Shape.centered_gradient())),
            ScrollOffset(speed=rotate_speed),
        )
        return Effect(
            name=name,
            pixels=AddColorsRenderer(
                [
                    (laser, PaletteLUT256(_RED_PALETTE)),
                ],
            ),
        )


BUILD = _Builder()
