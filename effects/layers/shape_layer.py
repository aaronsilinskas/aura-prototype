from effects.layers.layer import Layer
from effects.shape import EffectShapeFunc


class ShapeLayer(Layer):
    """Wraps a shape function into the Layer protocol.

    Exposes ``update(elapsed)`` (no-op — shape functions are stateless) and
    ``sample(position, pixel_count)`` so it can be used as a layer in
    ``AddColorsRenderer``. To add position drift, wrap with ``ScrollLayer``.
    """

    __slots__ = ["_shape"]

    def __init__(self, shape: EffectShapeFunc) -> None:
        self._shape = shape

    def update(self, elapsed: float) -> None:
        """No-op — shape functions are stateless."""

    def sample(self, position: float, pixel_count: int) -> float:
        """Return the shape value at ``position``, clamped to ``[0.0, 1.0]``.

        ``pixel_count`` is accepted for interface uniformity but is not used.
        """
        v = self._shape(position)
        return v if v <= 1.0 else 1.0
