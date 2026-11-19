"""Tag scene "ready" effect — a red laser sweep while the device waits in Ready."""

from __future__ import annotations

from effects.effect import Effect, EffectConfig
from effects.layers.add_colors_renderer import AddColorsRenderer
from effects.layers.scroll import ScrollOffset
from effects.layers.scroll_layer import ScrollLayer
from effects.layers.shape_layer import ShapeLayer
from effects.palette import PaletteLUT256
from effects.shape import Shape
from engine.effects.builder import EffectBuilder

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_RED_PALETTE: Final = bytes([0, 0, 0, 0, 255, 255, 0, 0])

# Revolutions per second of the sweeping laser.
_ROTATE_SPEED: Final = 0.6


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        laser = ScrollLayer(
            ShapeLayer(Shape.padded(0.25, Shape.centered_gradient())),
            ScrollOffset(speed=_ROTATE_SPEED),
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
