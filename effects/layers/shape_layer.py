from effects.layers.layer import Layer
from effects.shape import EffectShapeFunc


class ShapeLayer(Layer):
    """Wraps a shape function into the Layer protocol.

    To add position drift, wrap with ``ScrollLayer``.
    """

    __slots__ = ["_shape"]

    def __init__(self, shape: EffectShapeFunc) -> None:
        self._shape = shape

    def update(self, elapsed: float) -> None:
        """No-op — shape functions are stateless."""

    def sample(self, position: float, pixel_count: int) -> float:
        """Return the shape value at ``position``, capped at ``1.0``."""
        v = self._shape(position)
        return v if v <= 1.0 else 1.0
