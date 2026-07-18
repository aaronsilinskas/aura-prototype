from effects.layers.layer import Layer
from effects.layers.scroll import Scroll


class ScrollLayer(Layer):
    """Wraps any ``Layer`` with a ``Scroll``, shifting the sample position each frame.

    Stacking two ``ScrollLayer`` wrappers applies two independent position
    transforms, which is intentional and explicit.
    """

    __slots__ = ["_layer", "_scroll"]

    def __init__(self, layer: Layer, scroll: Scroll) -> None:
        self._layer = layer
        self._scroll = scroll

    def update(self, elapsed: float) -> None:
        """Advance the scroll and the inner layer."""
        self._scroll.update(elapsed)
        self._layer.update(elapsed)

    def sample(self, position: float, pixel_count: int) -> float:
        """Apply scroll to position and delegate to the inner layer."""
        return self._layer.sample(self._scroll.apply(position), pixel_count)
