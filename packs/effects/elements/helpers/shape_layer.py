from effects.shape import EffectShapeFunc
from packs.effects.elements.helpers.layer import Layer
from packs.effects.elements.helpers.scroll import Scroll


class ShapeLayer(Layer):
    """Wraps a shape function and optional scroll into the buffer protocol.

    Exposes ``update(elapsed)`` and ``sample(position, pixel_count)`` to match
    ``FlameBuffer``, ``DriftNoiseBuffer``, and ``SparkleBuffer``, so it can be
    used as a layer in ``AddColorsRenderer`` without special-casing.

    ``scroll`` is any object exposing ``update(elapsed: float)`` and
    ``apply(position: float) -> float``.  Pass ``None`` for a static shape.
    """

    __slots__ = ["_scroll", "_shape"]

    def __init__(self, shape: EffectShapeFunc, scroll: Scroll | None = None) -> None:
        self._shape = shape
        self._scroll = scroll

    def update(self, elapsed: float) -> None:
        """Advance scroll (if any). Shape functions are stateless."""
        if self._scroll is not None:
            self._scroll.update(elapsed)

    def sample(self, position: float, pixel_count: int) -> float:
        """Return the shape value at ``position``, after applying scroll.

        ``pixel_count`` is accepted for interface uniformity but is not used.
        Output is clamped to ``[0.0, 1.0]``.
        """
        pos = self._scroll.apply(position) if self._scroll is not None else position
        v = self._shape(pos)
        return v if v <= 1.0 else 1.0
